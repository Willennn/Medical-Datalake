"""
air.py — le processeur de la source API (qualité de l'air)
-----------------------------------------------------------
Comme ECGProcessor, mais pour les données OpenAQ.

👉 C'EST ICI QUE L'ARCHITECTURE PROUVE SA VALEUR.

Regarde bien : cette classe hérite du MÊME SignalProcessor que l'ECG, et ne
remplit que les 2 mêmes petits "trous" (load_raw et to_features). Pourtant les
données n'ont RIEN à voir :
    - ECG : fichier binaire, signal temporel, 360 points/seconde
    - Air : JSON d'API, mesures géolocalisées, quelques valeurs par capteur

Le stockage, l'enchaînement (run()), l'écriture, l'API : tout est partagé et n'a
PAS eu besoin d'être modifié. C'est exactement la démonstration attendue d'un
data lake bien conçu : il absorbe l'hétérogénéité.
"""

import io
import json

import pandas as pd
from minio.error import S3Error

from src.config import config
from src.storage.minio_client import get_client
from src.processors.base import SignalProcessor


class AirQualityProcessor(SignalProcessor):
    """Processeur pour les instantanés de qualité de l'air (API OpenAQ)."""

    source_type = "air"

    def load_raw(self, record_id: str) -> dict:
        """
        Récupère un instantané JSON depuis la zone raw de MinIO.

        Ici, record_id est le nom du fichier horodaté,
        ex : "2026-07-12T14-30-00Z"
        """
        object_name = f"air/{record_id}.json"
        client = get_client()

        try:
            response = client.get_object(config.BUCKET_RAW, object_name)
            data = response.read()
            response.close()
            response.release_conn()
        except S3Error as err:
            raise RuntimeError(
                f"Instantané introuvable dans raw : {object_name} ({err.code}). "
                "As-tu lancé : python -m src.ingestion.ingest_air ?"
            )

        return json.loads(data.decode("utf-8"))

    def to_features(self, raw: dict) -> pd.DataFrame:
        """
        Transforme le JSON brut (imbriqué, complexe) en un tableau plat.

        Le JSON d'OpenAQ est structuré en poupées russes : chaque "location"
        contient une liste de "sensors", chacun mesurant un polluant.
        On l'APLATIT : une ligne = un capteur d'un polluant à un endroit.

        C'est ça, le travail de la zone staging : rendre exploitable ce qui
        était brut.
        """
        rows = []
        fetched_at = raw.get("fetched_at")

        for location in raw.get("results", []):
            # Certains champs peuvent manquer : on utilise .get() partout pour
            # ne jamais planter sur une donnée incomplète (robustesse).
            coords = location.get("coordinates") or {}

            for sensor in location.get("sensors", []):
                parametre = sensor.get("parameter") or {}

                rows.append({
                    "location_id": location.get("id"),
                    "location_name": location.get("name"),
                    "latitude": coords.get("latitude"),
                    "longitude": coords.get("longitude"),
                    "sensor_id": sensor.get("id"),
                    # Le polluant mesuré : pm25, pm10, no2, o3...
                    "parametre": parametre.get("name"),
                    "unite": parametre.get("units"),
                    "fetched_at": fetched_at,
                })

        df = pd.DataFrame(rows)

        if df.empty:
            print("[air] ⚠️  aucun capteur exploitable dans cet instantané.")
            return df

        # Petit résumé lisible.
        polluants = df["parametre"].dropna().unique()
        print(f"[air] {len(df)} capteurs, {df['location_id'].nunique()} stations, "
              f"polluants : {', '.join(sorted(polluants))}")

        return df
