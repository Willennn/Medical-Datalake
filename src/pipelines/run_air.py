"""
run_air.py — le passage raw -> staging pour la source API
----------------------------------------------------------
Équivalent de run_ecg.py, mais pour les données de qualité de l'air.

Différence notable : comme chaque exécution de l'ingestion crée un instantané
horodaté, on ne connaît pas les noms de fichiers à l'avance. On les DÉCOUVRE
donc en listant le bucket, puis on traite le plus récent (ou tous).

À lancer APRÈS l'ingestion :
    python -m src.ingestion.ingest_air   # raw
    python -m src.pipelines.run_air      # raw -> staging
"""

import tempfile
from pathlib import Path

from src.config import config
from src.storage.minio_client import list_objects, upload_file
from src.processors.air import AirQualityProcessor


def lister_instantanes() -> list[str]:
    """
    Trouve tous les instantanés présents dans raw/air/ et renvoie leurs
    identifiants (le nom du fichier sans le dossier ni l'extension).
    """
    objets = list_objects(config.BUCKET_RAW, prefix="air/")
    ids = [
        Path(o["name"]).stem  # "air/2026-07-12T14-30-00Z.json" -> "2026-07-12T14-30-00Z"
        for o in objets
        if o["name"].endswith(".json")
    ]
    return sorted(ids)


def run(tous: bool = True) -> None:
    """
    Traite les instantanés et écrit les features en zone staging.

    Args:
        tous: si True, traite tous les instantanés ; sinon, seulement le dernier.
    """
    processor = AirQualityProcessor()

    instantanes = lister_instantanes()
    if not instantanes:
        print("[staging] ⚠️  aucun instantané trouvé dans raw/air/.")
        print("           Lance d'abord : python -m src.ingestion.ingest_air")
        return

    a_traiter = instantanes if tous else [instantanes[-1]]
    print(f"[staging] {len(a_traiter)} instantané(s) à traiter.\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        for record_id in a_traiter:
            try:
                # run() est HÉRITÉE de SignalProcessor : exactement la même
                # méthode que pour l'ECG. C'est tout l'intérêt de l'archi.
                features = processor.run(record_id)
            except Exception as err:
                print(f"[staging] ❌ échec pour '{record_id}' : {err}")
                continue

            if features.empty:
                print(f"[staging] ⚠️  aucune feature pour '{record_id}'.")
                continue

            local_parquet = tmp_dir / f"{record_id}.parquet"
            features.to_parquet(local_parquet, index=False)

            object_name = f"air/{record_id}.parquet"
            upload_file(config.BUCKET_STAGING, object_name, str(local_parquet))
            print(f"[staging] '{record_id}' : {len(features)} lignes -> "
                  f"{config.BUCKET_STAGING}/{object_name}\n")

    print("[staging] ✅ terminé.")


if __name__ == "__main__":
    run()
