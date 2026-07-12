"""
ingest_air.py — LA DEUXIÈME SOURCE : une API temps réel
--------------------------------------------------------
Le sujet impose DEUX sources de données :
  1. un dataset fichier  -> PhysioNet / MIT-BIH (déjà fait : ingest_ecg.py)
  2. une source API      -> c'est CE fichier.

On utilise OpenAQ (https://openaq.org), une base mondiale et gratuite de mesures
de qualité de l'air en temps réel.

POURQUOI CETTE SOURCE ? (à justifier dans le rapport)
La pollution de l'air est un facteur de risque cardio-respiratoire reconnu. Ça
donne une cohérence thématique au data lake : d'un côté le signal du patient
(ECG), de l'autre son environnement (qualité de l'air). Un data lake sert
justement à rapprocher des données de natures très différentes.

DIFFÉRENCE IMPORTANTE AVEC L'ECG :
  - L'ECG est un fichier BINAIRE, statique, téléchargé une fois.
  - OpenAQ renvoie du JSON, en TEMPS RÉEL, qu'on ré-interroge régulièrement.
C'est exactement pour ça que le sujet demande deux sources : montrer que le lake
gère l'hétérogénéité.

⚠️ IL TE FAUT UNE CLÉ API (gratuite) :
   1. Crée un compte sur https://explore.openaq.org/register
   2. Récupère ta clé dans les paramètres du compte
   3. Colle-la dans ton fichier .env :  OPENAQ_API_KEY=ta_cle_ici

Pour lancer :
    python -m src.ingestion.ingest_air
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.config import config
from src.storage.minio_client import ensure_buckets, upload_file

# L'API OpenAQ, version 3 (les v1 et v2 ont été retirées début 2025).
BASE_URL = "https://api.openaq.org/v3"

# Les villes qu'on surveille. On prend Paris + quelques grandes villes, pour
# avoir des mesures variées. (Tu peux en ajouter.)
# Ce sont des identifiants de "locations" OpenAQ.
COORDS = "48.8566,2.3522"   # Paris (latitude, longitude)
RADIUS_METERS = 25000       # on cherche les capteurs dans un rayon de 25 km
LIMIT = 50                  # nombre max de capteurs à récupérer


def fetch_locations() -> list[dict]:
    """
    Interroge l'API OpenAQ pour récupérer les capteurs autour de Paris,
    avec leurs dernières mesures.

    Renvoie la liste brute des résultats (telle que l'API les donne).
    """
    if not config.OPENAQ_API_KEY:
        raise RuntimeError(
            "Clé API OpenAQ manquante !\n"
            "  1. Crée un compte : https://explore.openaq.org/register\n"
            "  2. Copie ta clé dans le fichier .env :\n"
            "       OPENAQ_API_KEY=ta_cle_ici"
        )

    url = f"{BASE_URL}/locations"
    params = {
        "coordinates": COORDS,
        "radius": RADIUS_METERS,
        "limit": LIMIT,
    }
    # La clé se transmet dans un en-tête HTTP nommé "X-API-Key".
    headers = {"X-API-Key": config.OPENAQ_API_KEY}

    print(f"[air] interrogation de l'API OpenAQ (Paris, rayon {RADIUS_METERS//1000} km)...")

    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
    except requests.RequestException as err:
        # Pas de réseau, DNS en panne, timeout... on renvoie une erreur claire.
        raise RuntimeError(f"Impossible de joindre l'API OpenAQ : {err}")

    # Gestion explicite des cas d'erreur (le sujet insiste là-dessus).
    if response.status_code == 401:
        raise RuntimeError("Clé API refusée (401). Vérifie OPENAQ_API_KEY dans .env.")
    if response.status_code == 429:
        raise RuntimeError("Trop de requêtes (429). Attends un peu avant de réessayer.")
    if response.status_code != 200:
        raise RuntimeError(
            f"L'API a répondu {response.status_code} : {response.text[:200]}"
        )

    payload = response.json()
    results = payload.get("results", [])
    print(f"[air] {len(results)} capteurs récupérés.")
    return results


def ingest() -> None:
    """
    Récupère les données de l'API et les dépose TELLES QUELLES (JSON brut)
    dans la zone raw de MinIO.

    ⚠️ On ne transforme rien ici : c'est la règle de la zone raw.
    Le fichier est horodaté, ce qui permet de garder un HISTORIQUE : chaque
    exécution ajoute un nouveau instantané, sans écraser les précédents.
    C'est ce qui rendra l'ingestion périodique (via Airflow) intéressante.
    """
    ensure_buckets()

    results = fetch_locations()
    if not results:
        print("[air] ⚠️  aucune donnée retournée par l'API. Rien à ingérer.")
        return

    # On horodate le fichier pour construire un historique.
    # Ex : air/2026-07-12T14-30-00Z.json
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    object_name = f"air/{timestamp}.json"

    # On enveloppe les données brutes avec quelques métadonnées utiles
    # (d'où ça vient, quand ça a été récupéré) : c'est une bonne pratique.
    payload = {
        "source": "openaq_v3",
        "fetched_at": now.isoformat(),
        "coordinates": COORDS,
        "radius_meters": RADIUS_METERS,
        "n_results": len(results),
        "results": results,   # <- les données BRUTES, non modifiées
    }

    with tempfile.TemporaryDirectory() as tmp:
        local_path = Path(tmp) / "air.json"
        local_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        upload_file(config.BUCKET_RAW, object_name, str(local_path))

    print(f"\n[air] ✅ instantané déposé dans '{config.BUCKET_RAW}/{object_name}'.")
    print("[air] (Relance la commande plus tard : un NOUVEL instantané sera créé,")
    print("       les anciens sont conservés -> tu construis un historique.)")


if __name__ == "__main__":
    ingest()
