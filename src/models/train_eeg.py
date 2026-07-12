"""
train_eeg.py — le modèle de détection de crises d'épilepsie
------------------------------------------------------------
Même structure que train_ecg.py, mais un problème BEAUCOUP plus difficile.

⚠️ POURQUOI C'EST DUR (le point central du rapport pour cette partie) :

Sur l'ECG, ~34 % des battements étaient anormaux. Ici, les crises représentent
seulement ~1 à 2 % des fenêtres. Conséquences :

  1. Une baseline qui répondrait "jamais de crise" aurait ~98 % d'ACCURACY.
     L'accuracy devient donc une métrique TROMPEUSE et inutile.

  2. Le modèle a très peu d'exemples positifs pour apprendre à quoi ressemble
     une crise.

  3. En médecine, RATER une crise (faux négatif) est bien plus grave que
     donner une fausse alerte (faux positif). On privilégie donc le RAPPEL.

On sépare les données PAR ENREGISTREMENT (pas au hasard) : le modèle est testé
sur un patient-enregistrement qu'il n'a JAMAIS vu. C'est plus honnête et plus
réaliste : découper au hasard mettrait des fenêtres voisines (donc quasi
identiques) à la fois en entraînement et en test, ce qui gonflerait
artificiellement les scores.

À lancer APRÈS run_eeg :
    python -m src.models.train_eeg
"""

import io
from pathlib import Path

import joblib
import pandas as pd
from minio.error import S3Error
from sklearn.ensemble import RandomForestClassifier
from sklearn.dummy import DummyClassifier
from sklearn.metrics import (
    accuracy_score, recall_score, precision_score,
    f1_score, confusion_matrix, classification_report,
)

from src.config import config
from src.storage.minio_client import get_client
from src.storage import postgres_client as pg
from src.ingestion.ingest_eeg import RECORDS

MODEL_DIR = Path("models")
MODEL_PATH = MODEL_DIR / "eeg_model.joblib"

# Les features : les puissances relatives par bande + l'amplitude.
FEATURE_COLS = [
    "ratio_delta", "ratio_theta", "ratio_alpha", "ratio_beta", "ratio_gamma",
    "amplitude_std",
]
TARGET_COL = "is_seizure"


def load_staging() -> pd.DataFrame:
    """Lit les .parquet EEG depuis la zone staging."""
    client = get_client()
    frames = []

    for record_id in RECORDS:
        object_name = f"eeg/{record_id}.parquet"
        try:
            response = client.get_object(config.BUCKET_STAGING, object_name)
            data = response.read()
            response.close()
            response.release_conn()
        except S3Error as err:
            print(f"[model] ⚠️  introuvable : {object_name} ({err.code})")
            continue

        df = pd.read_parquet(io.BytesIO(data))
        df["record_id"] = record_id
        frames.append(df)
        n_crises = int(df[TARGET_COL].sum())
        print(f"[model] chargé : {object_name} "
              f"({len(df)} fenêtres, {n_crises} en crise)")

    if not frames:
        raise RuntimeError(
            "Aucune donnée EEG en staging. "
            "Lance d'abord : python -m src.pipelines.run_eeg"
        )
    return pd.concat(frames, ignore_index=True)


def evaluate(nom: str, y_true, y_pred) -> None:
    """Affiche les métriques, en insistant sur le rappel."""
    print(f"\n--- {nom} ---")
    print(f"  Accuracy            : {accuracy_score(y_true, y_pred):.1%}  "
          f"(⚠️ trompeuse ici !)")
    print(f"  Rappel (crises)     : "
          f"{recall_score(y_true, y_pred, pos_label=1, zero_division=0):.1%}"
          f"  <- LA métrique qui compte")
    print(f"  Précision (crises)  : "
          f"{precision_score(y_true, y_pred, pos_label=1, zero_division=0):.1%}")
    print(f"  F1 (crises)         : "
          f"{f1_score(y_true, y_pred, pos_label=1, zero_division=0):.1%}")


def train() -> None:
    """Pipeline : staging -> modèle -> curated."""

    print("=" * 62)
    print("ÉTAPE 1/4 : chargement des features EEG")
    print("=" * 62)
    df = load_staging().dropna(subset=FEATURE_COLS).reset_index(drop=True)

    n_total = len(df)
    n_crises = int(df[TARGET_COL].sum())
    pct = n_crises / n_total * 100
    print(f"\n[model] Total : {n_total} fenêtres, dont {n_crises} en crise "
          f"({pct:.2f} %).")
    print("[model] => Déséquilibre EXTRÊME. Une baseline 'jamais de crise'")
    print(f"[model]    obtiendrait déjà {100-pct:.1f} % d'accuracy sans rien détecter.")

    if n_crises < 10:
        print("\n⚠️  Trop peu d'exemples de crise pour entraîner un modèle fiable.")
        print("    Ajoute des enregistrements dans RECORDS (src/ingestion/ingest_eeg.py).")
        return

    # ---------- 2. Séparation PAR ENREGISTREMENT ----------
    print("\n" + "=" * 62)
    print("ÉTAPE 2/4 : séparation entraînement / test (par enregistrement)")
    print("=" * 62)

    records = sorted(df["record_id"].unique())
    if len(records) < 2:
        print("⚠️  Il faut au moins 2 enregistrements pour séparer proprement.")
        return

    # Le DERNIER enregistrement sert de test : le modèle ne l'aura jamais vu.
    records_train = records[:-1]
    record_test = records[-1]

    train_df = df[df["record_id"].isin(records_train)]
    test_df = df[df["record_id"] == record_test]

    print(f"[model] entraînement : {records_train} -> {len(train_df)} fenêtres "
          f"({int(train_df[TARGET_COL].sum())} crises)")
    print(f"[model] test         : {record_test} -> {len(test_df)} fenêtres "
          f"({int(test_df[TARGET_COL].sum())} crises)")
    print("[model] => Le test porte sur un enregistrement JAMAIS vu à l'entraînement.")

    X_train, y_train = train_df[FEATURE_COLS], train_df[TARGET_COL]
    X_test, y_test = test_df[FEATURE_COLS], test_df[TARGET_COL]

    if y_test.sum() == 0:
        print("\n⚠️  L'enregistrement de test ne contient aucune crise : "
              "impossible de mesurer le rappel.")
        return

    # ---------- 3. Entraînement ----------
    print("\n" + "=" * 62)
    print("ÉTAPE 3/4 : entraînement et évaluation")
    print("=" * 62)

    baseline = DummyClassifier(strategy="most_frequent").fit(X_train, y_train)
    evaluate("Baseline naïve (répond toujours 'pas de crise')",
             y_test, baseline.predict(X_test))
    print("  => Accuracy quasi parfaite... mais rappel NUL. Inutile en clinique.")

    model = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",   # indispensable vu le déséquilibre
        random_state=42,
        n_jobs=-1,
    ).fit(X_train, y_train)

    y_pred = model.predict(X_test)
    evaluate("Random Forest (pondéré)", y_test, y_pred)

    cm = confusion_matrix(y_test, y_pred)
    print("\n  Matrice de confusion :")
    print("                     prédit calme | prédit crise")
    print(f"    réel calme     :     {cm[0][0]:7d}  |   {cm[0][1]:7d}")
    if cm.shape[0] > 1:
        print(f"    réel CRISE     :     {cm[1][0]:7d}  |   {cm[1][1]:7d}")
        print("\n  (Les 'réel crise / prédit calme' sont les crises RATÉES.)")

    print("\n  Rapport détaillé :")
    print(classification_report(y_test, y_pred,
                                target_names=["calme", "crise"],
                                zero_division=0))

    print("  Importance des features :")
    for feat, imp in sorted(zip(FEATURE_COLS, model.feature_importances_),
                            key=lambda x: -x[1]):
        print(f"    {feat:16s} : {imp:.1%}")

    # ---------- 4. Sauvegarde + curated ----------
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"\n[model] 💾 modèle sauvegardé : {MODEL_PATH}")

    print("\n" + "=" * 62)
    print("ÉTAPE 4/4 : écriture dans la zone curated")
    print("=" * 62)

    df["predicted"] = model.predict(df[FEATURE_COLS])
    df["proba"] = model.predict_proba(df[FEATURE_COLS])[:, 1]
    df["source_type"] = "eeg"

    pg.ensure_table()
    pg.clear_source("eeg")
    n = pg.insert_results(df)

    print(f"\n[curated] ✅ {n} fenêtres EEG écrites dans PostgreSQL.")
    print(f"[curated] La base contient maintenant {pg.count_rows()} lignes "
          f"(ECG + EEG confondus).")
    print("\n🎉 L'EEG tourne sur la MÊME infrastructure que l'ECG.")


if __name__ == "__main__":
    train()
