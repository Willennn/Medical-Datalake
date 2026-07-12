"""
postgres_client.py
------------------
Petit assistant pour parler à la base de données PostgreSQL (la zone CURATED).

Rappel : la zone curated est le "rayon final" du data lake. On y range les
données propres ET le résultat du modèle, prêtes à être servies par l'API.

Ce fichier sait faire 3 choses :
  - se connecter à la base
  - créer la table si elle n'existe pas
  - insérer les résultats d'un enregistrement
"""

import pandas as pd
from sqlalchemy import create_engine, text

from src.config import config

# Nom de la table qui stocke les battements analysés.
TABLE_NAME = "curated_beats"

# La structure de la table.
# Note : elle est volontairement GÉNÉRIQUE (source_type, record_id...) pour
# pouvoir accueillir aussi bien l'ECG que l'EEG plus tard, sans la modifier.
CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id            SERIAL PRIMARY KEY,
    source_type   TEXT    NOT NULL,   -- "ecg" ou "eeg" : d'où vient la donnée
    record_id     TEXT    NOT NULL,   -- quel enregistrement / patient
    beat_index    INTEGER,            -- numéro du battement dans l'enregistrement
    position_sec  DOUBLE PRECISION,   -- instant du battement (en secondes)
    rr_prev       DOUBLE PRECISION,   -- temps depuis le battement précédent
    rr_next       DOUBLE PRECISION,   -- temps jusqu'au battement suivant
    amp_range     DOUBLE PRECISION,   -- amplitude du battement
    symbol        TEXT,               -- étiquette d'origine (cardiologue)
    is_abnormal   INTEGER,            -- vérité terrain : 0 = normal, 1 = anormal
    predicted     INTEGER,            -- ce que le MODÈLE a prédit
    proba         DOUBLE PRECISION,   -- confiance du modèle (entre 0 et 1)
    ingested_at   TIMESTAMP DEFAULT NOW()  -- quand la ligne a été écrite
);
"""

# Colonnes ajoutées pour accueillir l'EEG (fenêtres + bandes de fréquence).
# On utilise ALTER TABLE ... ADD COLUMN IF NOT EXISTS : la table existante n'est
# pas détruite, on l'étend. C'est ce qu'on appelle une MIGRATION de schéma.
#
# 💡 Remarque d'architecture : c'est le SEUL endroit du projet où ajouter un
# domaine touche à l'existant. Tout le reste (stockage, processeurs, API,
# Airflow) est resté strictement inchangé.
ALTER_TABLE_EEG = [
    f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS fenetre_index INTEGER",
    f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS debut_sec DOUBLE PRECISION",
    f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS ratio_delta DOUBLE PRECISION",
    f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS ratio_theta DOUBLE PRECISION",
    f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS ratio_alpha DOUBLE PRECISION",
    f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS ratio_beta DOUBLE PRECISION",
    f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS ratio_gamma DOUBLE PRECISION",
    f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS amplitude_std DOUBLE PRECISION",
    f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS is_seizure INTEGER",
]


def get_engine():
    """Ouvre une connexion à PostgreSQL en utilisant les infos de config.py."""
    return create_engine(config.postgres_url)


def ensure_table() -> None:
    """
    Crée la table curated si elle n'existe pas, puis applique les migrations
    (ajout des colonnes EEG). Les deux opérations sont sans danger : elles ne
    font rien si tout est déjà en place.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(CREATE_TABLE_SQL))
        # Migration : on ajoute les colonnes EEG si elles manquent.
        for sql in ALTER_TABLE_EEG:
            conn.execute(text(sql))
    print(f"[postgres] table '{TABLE_NAME}' : prête.")


def clear_source(source_type: str) -> None:
    """
    Efface les lignes d'une source donnée avant réécriture.

    Pourquoi ? Pour que relancer le pipeline ne crée pas de doublons.
    C'est ce qu'on appelle un pipeline IDEMPOTENT : le relancer redonne le même
    résultat, sans empiler les données.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(f"DELETE FROM {TABLE_NAME} WHERE source_type = :src"),
            {"src": source_type},
        )


def insert_results(df: pd.DataFrame) -> int:
    """
    Insère un tableau de résultats dans la table curated.

    Args:
        df: le tableau contenant les features + les prédictions du modèle.

    Returns:
        Le nombre de lignes insérées.

    ⚠️ POURQUOI PAS `pandas.to_sql()` ? (bug rencontré en vrai)
    On a d'abord utilisé `to_sql()`, qui marchait en local (SQLAlchemy 2.x) mais
    plantait dans Airflow (SQLAlchemy 1.4, version imposée par Airflow) avec :
        AttributeError: 'Engine' object has no attribute 'cursor'
    Le comportement de `to_sql()` dépend trop de la version de SQLAlchemy.

    On écrit donc un INSERT explicite : c'est portable, indépendant de la
    version, et en prime plus rapide (SQLAlchemy groupe les lignes en un seul
    aller-retour vers la base — le même principe que /ingest_fast).
    """
    # On ne garde que les colonnes qui existent dans la table (sécurité).
    # La liste couvre les DEUX domaines : ECG (rr_prev, symbol...) et
    # EEG (ratio_alpha, is_seizure...). Chaque domaine ne remplit que les
    # siennes, les autres restent vides (NULL). C'est un schéma volontairement
    # permissif, adapté à un data lake qui accueille des sources hétérogènes.
    expected = [
        # --- communes ---
        "source_type", "record_id", "predicted", "proba",
        # --- ECG ---
        "beat_index", "position_sec", "rr_prev", "rr_next", "amp_range",
        "symbol", "is_abnormal",
        # --- EEG ---
        "fenetre_index", "debut_sec", "amplitude_std", "is_seizure",
        "ratio_delta", "ratio_theta", "ratio_alpha", "ratio_beta", "ratio_gamma",
    ]
    cols = [c for c in expected if c in df.columns]
    if not cols:
        return 0

    # On transforme le tableau en liste de dictionnaires (une par ligne).
    # NaN -> None, sinon PostgreSQL refuse la valeur.
    rows = df[cols].astype(object).where(pd.notnull(df[cols]), None).to_dict("records")
    if not rows:
        return 0

    # Construction de la requête : INSERT INTO table (col1, col2) VALUES (:col1, :col2)
    colonnes = ", ".join(cols)
    valeurs = ", ".join(f":{c}" for c in cols)
    sql = text(f"INSERT INTO {TABLE_NAME} ({colonnes}) VALUES ({valeurs})")

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sql, rows)   # SQLAlchemy fait un executemany groupé

    return len(rows)


def count_rows() -> int:
    """Compte les lignes présentes dans la table (utile pour /stats)."""
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}"))
        return int(result.scalar())


def fetch_rows(source_type: str | None = None, record_id: str | None = None,
               limit: int = 100, offset: int = 0) -> list[dict]:
    """
    Récupère des lignes de la table curated, avec filtres optionnels.
    Utilisé par l'endpoint GET /curated de l'API.
    """
    clauses, params = [], {"limit": limit, "offset": offset}
    if source_type:
        clauses.append("source_type = :src")
        params["src"] = source_type
    if record_id:
        clauses.append("record_id = :rec")
        params["rec"] = record_id

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    # ⚠️ On sélectionne les colonnes des DEUX domaines : ECG (rr_prev, symbol...)
    # et EEG (debut_sec, ratio_*, is_seizure...). Chaque ligne ne remplit que
    # les siennes, les autres arrivent à NULL — c'est normal dans un schéma de
    # data lake qui accueille des sources hétérogènes.
    sql = f"""
        SELECT source_type, record_id, predicted, proba,
               beat_index, position_sec, rr_prev, rr_next, amp_range,
               symbol, is_abnormal,
               fenetre_index, debut_sec, amplitude_std, is_seizure,
               ratio_delta, ratio_theta, ratio_alpha, ratio_beta, ratio_gamma
        FROM {TABLE_NAME}
        {where}
        ORDER BY record_id, COALESCE(beat_index, fenetre_index)
        LIMIT :limit OFFSET :offset
    """
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        return [dict(row._mapping) for row in result]


def get_stats() -> dict:
    """
    Statistiques sur la zone curated : nombre de lignes, d'anomalies, etc.
    Utilisé par l'endpoint GET /stats.
    """
    engine = get_engine()
    with engine.connect() as conn:
        # Est-ce que la table existe seulement ?
        exists = conn.execute(text(
            "SELECT to_regclass(:t)"), {"t": TABLE_NAME}).scalar()
        if exists is None:
            return {"table_exists": False, "total_rows": 0, "par_source": []}

        total = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}")).scalar()

        # Détail par source (ecg, eeg, air).
        # ⚠️ COALESCE est indispensable : la vérité terrain s'appelle
        # `is_abnormal` pour l'ECG mais `is_seizure` pour l'EEG. Sans ça, la
        # somme portait sur une colonne vide pour l'EEG et renvoyait NULL —
        # le tableau affichait "None". C'était un vrai bug.
        rows = conn.execute(text(f"""
            SELECT source_type,
                   COUNT(*)                                        AS n_rows,
                   COUNT(DISTINCT record_id)                       AS n_records,
                   COALESCE(SUM(COALESCE(is_abnormal, is_seizure)), 0) AS n_abnormal_reel,
                   COALESCE(SUM(predicted), 0)                     AS n_abnormal_predit
            FROM {TABLE_NAME}
            GROUP BY source_type
            ORDER BY source_type
        """))
        par_source = [dict(r._mapping) for r in rows]

    return {
        "table_exists": True,
        "total_rows": int(total),
        "par_source": par_source,
    }


def ping() -> bool:
    """Vérifie que PostgreSQL répond. Utilisé par GET /health."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # Lancer ce fichier directement crée la table. Pratique pour tester.
    print("Connexion à PostgreSQL et création de la table...")
    ensure_table()
    print(f"OK : la base contient actuellement {count_rows()} lignes.")
