"""
run_ecg.py — ÉTAPE 1 (3/3 pour l'instant) : le passage raw -> staging
---------------------------------------------------------------------
Ce script fait tourner le ECGProcessor sur les enregistrements déposés dans la
zone raw, et écrit le résultat (les features par battement) dans la zone
staging, au format Parquet.

À lancer APRÈS l'ingestion :
    python -m src.ingestion.ingest_ecg   # d'abord : raw
    python -m src.pipelines.run_ecg      # ensuite : raw -> staging

À la fin, tu peux ouvrir la console MinIO (http://localhost:9001) et voir les
fichiers .parquet apparaître dans le bucket 'staging', sous 'ecg/'.
"""

import tempfile
from pathlib import Path

from src.config import config
from src.storage.minio_client import upload_file
from src.processors.ecg import ECGProcessor
from src.ingestion.ingest_ecg import RECORDS  # la même liste d'enregistrements


def run() -> None:
    """Traite chaque enregistrement et envoie ses features en zone staging."""
    processor = ECGProcessor()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        for record_id in RECORDS:
            try:
                # run() est la méthode HÉRITÉE de SignalProcessor : elle appelle
                # load_raw() puis to_features() et ajoute les colonnes communes.
                features = processor.run(record_id)
            except Exception as err:
                print(f"[staging] ❌ échec pour '{record_id}' : {err}")
                continue

            if features.empty:
                print(f"[staging] ⚠️  aucun battement extrait pour '{record_id}'.")
                continue

            # On sauvegarde d'abord le tableau en Parquet localement...
            local_parquet = tmp_dir / f"{record_id}.parquet"
            features.to_parquet(local_parquet, index=False)

            # ...puis on l'envoie dans la zone staging de MinIO.
            object_name = f"ecg/{record_id}.parquet"
            upload_file(config.BUCKET_STAGING, object_name, str(local_parquet))

            # Petit résumé lisible dans le terminal.
            n_total = len(features)
            n_abnormal = int(features["is_abnormal"].sum())
            print(f"[staging] '{record_id}' : {n_total} battements "
                  f"({n_abnormal} anormaux) -> {config.BUCKET_STAGING}/{object_name}\n")

    print("[staging] ✅ terminé. Les features sont prêtes pour l'étape modèle.")


if __name__ == "__main__":
    run()
