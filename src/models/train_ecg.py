"""
train_ecg.py — ÉTAPE 1 (final) : le modèle + la zone CURATED
------------------------------------------------------------
Dernier maillon du pipeline ECG. Il fait 3 choses :
  1. lit les features depuis la zone STAGING (les .parquet)
  2. entraîne un modèle à distinguer battement normal / anormal
  3. écrit les résultats (features + prédiction) dans la zone CURATED (PostgreSQL)

⚠️ LE PIÈGE À COMPRENDRE (important pour ton rapport) :
Sur un ECG, environ 90 % des battements sont NORMAUX. Un modèle paresseux qui
répondrait "tout est normal" aurait donc déjà ~90 % d'accuracy... tout en étant
MÉDICALEMENT INUTILE, puisqu'il raterait 100 % des anomalies !

C'est pour ça qu'on :
  - compare TOUJOURS à une "baseline naïve" (le modèle paresseux),
  - utilise class_weight="balanced" pour forcer le modèle à prendre les
    anomalies au sérieux (sinon il les ignore, elles sont trop rares),
  - regarde le RAPPEL (quelle proportion des vraies anomalies on attrape) et
    pas seulement l'accuracy.

À lancer APRÈS run_ecg :
    python -m src.models.train_ecg
"""

import io
from pathlib import Path

import joblib
import pandas as pd
from minio.error import S3Error
from sklearn.ensemble import RandomForestClassifier
from sklearn.dummy import DummyClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, recall_score, precision_score,
    f1_score, confusion_matrix, classification_report,
)

from src.config import config
from src.storage.minio_client import get_client
from src.storage import postgres_client as pg
from src.ingestion.ingest_ecg import RECORDS

# Où le modèle entraîné est sauvegardé (l'API le rechargera depuis là).
MODEL_DIR = Path("models")
MODEL_PATH = MODEL_DIR / "ecg_model.joblib"

# Les colonnes que le modèle utilise pour décider (nos "features").
FEATURE_COLS = ["rr_prev", "rr_next", "amp_max", "amp_min", "amp_range"]

# La colonne à prédire (la "vérité terrain", annotée par les cardiologues).
TARGET_COL = "is_abnormal"


def load_staging() -> pd.DataFrame:
    """Lit tous les fichiers .parquet de la zone staging et les assemble."""
    client = get_client()
    frames = []

    for record_id in RECORDS:
        object_name = f"ecg/{record_id}.parquet"
        try:
            response = client.get_object(config.BUCKET_STAGING, object_name)
            data = response.read()
            response.close()
            response.release_conn()
        except S3Error as err:
            print(f"[model] ⚠️  fichier introuvable dans staging : "
                  f"{object_name} ({err.code}). As-tu lancé run_ecg ?")
            continue

        df = pd.read_parquet(io.BytesIO(data))
        frames.append(df)
        print(f"[model] chargé : {object_name} ({len(df)} battements)")

    if not frames:
        raise RuntimeError(
            "Aucune donnée trouvée en staging. "
            "Lance d'abord : python -m src.pipelines.run_ecg"
        )

    return pd.concat(frames, ignore_index=True)


def evaluate(name: str, y_true, y_pred) -> dict:
    """Calcule et affiche les métriques d'un modèle."""
    metrics = {
        "modele": name,
        "accuracy": accuracy_score(y_true, y_pred),
        # Rappel = sur toutes les vraies anomalies, combien en attrape-t-on ?
        # C'est LA métrique qui compte en médecine (rater une anomalie est grave).
        "rappel_anomalies": recall_score(y_true, y_pred, pos_label=1, zero_division=0),
        # Précision = quand le modèle crie "anomalie", a-t-il raison ?
        "precision_anomalies": precision_score(y_true, y_pred, pos_label=1, zero_division=0),
        "f1_anomalies": f1_score(y_true, y_pred, pos_label=1, zero_division=0),
    }
    print(f"\n--- {name} ---")
    print(f"  Accuracy            : {metrics['accuracy']:.1%}")
    print(f"  Rappel (anomalies)  : {metrics['rappel_anomalies']:.1%}  <- le plus important")
    print(f"  Précision(anomalies): {metrics['precision_anomalies']:.1%}")
    print(f"  F1 (anomalies)      : {metrics['f1_anomalies']:.1%}")
    return metrics


def train() -> None:
    """Pipeline complet : staging -> modèle -> curated."""

    # ---------- 1. Charger les features ----------
    print("=" * 60)
    print("ÉTAPE 1/4 : chargement des features depuis la zone staging")
    print("=" * 60)
    df = load_staging()

    # On enlève les lignes où il manque des valeurs (1er et dernier battement
    # n'ont pas de rr_prev / rr_next).
    df = df.dropna(subset=FEATURE_COLS).reset_index(drop=True)

    n_total = len(df)
    n_abnormal = int(df[TARGET_COL].sum())
    pct = n_abnormal / n_total * 100
    print(f"\n[model] Total : {n_total} battements, dont {n_abnormal} anormaux "
          f"({pct:.1f} %).")
    print(f"[model] => Les anomalies sont RARES : c'est le déséquilibre de classes.")

    # ---------- 2. Séparer entraînement / test ----------
    print("\n" + "=" * 60)
    print("ÉTAPE 2/4 : séparation entraînement / test")
    print("=" * 60)
    X = df[FEATURE_COLS]
    y = df[TARGET_COL]

    # stratify=y garde la même proportion d'anomalies dans les deux paquets.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42, stratify=y
    )
    print(f"[model] entraînement : {len(X_train)} battements")
    print(f"[model] test         : {len(X_test)} battements (jamais vus par le modèle)")

    # ---------- 3. Entraîner et comparer ----------
    print("\n" + "=" * 60)
    print("ÉTAPE 3/4 : entraînement et évaluation")
    print("=" * 60)

    # (a) LA BASELINE NAÏVE : le "modèle paresseux" qui répond toujours la
    #     classe majoritaire ("tout est normal"). Sert de point de comparaison.
    baseline = DummyClassifier(strategy="most_frequent")
    baseline.fit(X_train, y_train)
    evaluate("Baseline naïve (répond toujours 'normal')", y_test, baseline.predict(X_test))
    print("  => Accuracy élevée mais rappel NUL : elle rate TOUTES les anomalies.")
    print("     C'est exactement le piège à éviter.")

    # (b) LE VRAI MODÈLE : une forêt aléatoire, avec pondération des classes.
    #     class_weight="balanced" dit au modèle : "les anomalies sont rares,
    #     donc chaque erreur sur une anomalie coûte plus cher".
    model = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    evaluate("Random Forest (pondéré)", y_test, y_pred)

    # Matrice de confusion : le détail des erreurs.
    cm = confusion_matrix(y_test, y_pred)
    print("\n  Matrice de confusion :")
    print("                    prédit normal | prédit anormal")
    print(f"    réel normal   :      {cm[0][0]:6d}    |     {cm[0][1]:6d}")
    print(f"    réel anormal  :      {cm[1][0]:6d}    |     {cm[1][1]:6d}")
    print("\n  (Les 'réel anormal / prédit normal' sont les anomalies RATÉES :")
    print("   c'est l'erreur la plus grave en médecine.)")

    print("\n  Rapport détaillé :")
    print(classification_report(y_test, y_pred,
                                target_names=["normal", "anormal"],
                                zero_division=0))

    # Quelles features le modèle juge-t-il importantes ? (interprétabilité)
    print("  Importance des features (ce sur quoi le modèle s'appuie) :")
    for feat, imp in sorted(zip(FEATURE_COLS, model.feature_importances_),
                            key=lambda x: -x[1]):
        print(f"    {feat:12s} : {imp:.1%}")

    # ---------- 4. Sauvegarder le modèle ----------
    # L'API (endpoints /ingest) aura besoin de ce modèle pour prédire sur des
    # nouvelles données. On l'enregistre donc sur le disque.
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"\n[model] 💾 modèle sauvegardé : {MODEL_PATH}")

    # ---------- 5. Écrire en zone curated ----------
    print("\n" + "=" * 60)
    print("ÉTAPE 4/4 : écriture dans la zone curated (PostgreSQL)")
    print("=" * 60)

    # On applique le modèle à TOUTES les données (pas juste le test) pour
    # remplir la base avec la prédiction de chaque battement.
    df["predicted"] = model.predict(X)
    df["proba"] = model.predict_proba(X)[:, 1]  # confiance que c'est anormal

    pg.ensure_table()
    pg.clear_source("ecg")  # évite les doublons si on relance (idempotence)
    n_inserted = pg.insert_results(df)

    print(f"\n[curated] ✅ {n_inserted} lignes écrites dans PostgreSQL.")
    print(f"[curated] La base contient maintenant {pg.count_rows()} lignes au total.")
    print("\n🎉 Pipeline COMPLET : raw -> staging -> curated. Bravo !")


if __name__ == "__main__":
    train()
