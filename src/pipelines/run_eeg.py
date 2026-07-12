"""
run_eeg.py — le passage raw -> staging pour l'EEG
--------------------------------------------------
Même structure que run_ecg.py et run_air.py. C'est volontaire : le pipeline est
uniforme quel que soit le domaine.

À lancer APRÈS l'ingestion :
    python -m src.ingestion.ingest_eeg   # raw   (⏳ ~170 Mo à télécharger)
    python -m src.pipelines.run_eeg      # raw -> staging
"""

import tempfile
from pathlib import Path

from src.config import config
from src.storage.minio_client import upload_file
from src.processors.eeg import EEGProcessor
from src.ingestion.ingest_eeg import RECORDS


def run() -> None:
    """Traite chaque enregistrement EEG et écrit ses features en staging."""
    processor = EEGProcessor()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        for record_id in RECORDS:
            print(f"\n{'='*55}")
            try:
                # run() : TOUJOURS la même méthode héritée. Rien de spécifique.
                features = processor.run(record_id)
            except Exception as err:
                print(f"[staging] ❌ échec pour '{record_id}' : {err}")
                continue

            if features.empty:
                print(f"[staging] ⚠️  aucune fenêtre extraite pour '{record_id}'.")
                continue

            local = tmp_dir / f"{record_id}.parquet"
            features.to_parquet(local, index=False)

            object_name = f"eeg/{record_id}.parquet"
            upload_file(config.BUCKET_STAGING, object_name, str(local))
            print(f"[staging] '{record_id}' -> {config.BUCKET_STAGING}/{object_name}")

    print(f"\n[staging] ✅ terminé. Les features EEG sont prêtes.")


if __name__ == "__main__":
    run()
