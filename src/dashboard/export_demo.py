"""
export_demo.py — Figer un instantané des données pour la démo en ligne
======================================================================
POURQUOI CE SCRIPT ?

Notre dashboard interroge l'API, qui interroge MinIO et PostgreSQL — tous trois
tournant sur la machine locale via Docker.

Or, si nous déployons le dashboard sur Streamlit Cloud, le serveur distant ne
peut évidemment pas joindre notre « localhost ». Déployer toute l'infrastructure
dans le cloud (base managée, stockage S3 réel) serait long et coûteux, et n'a
aucun intérêt pédagogique.

NOTRE SOLUTION : un mode démo.
Ce script exporte un instantané des données finales dans le dossier demo_data/.
Le dashboard s'en sert automatiquement lorsque l'API est injoignable — ce qui
permet à n'importe qui d'explorer le projet en ligne, sans rien installer.

L'architecture reste intacte : en local, le dashboard passe toujours par l'API.
L'instantané n'est qu'une roue de secours pour la démonstration publique.

À lancer une fois le pipeline complet exécuté, avec l'API en marche :
    python -m src.dashboard.export_demo
"""

import json
from pathlib import Path

import pandas as pd
import requests

API_URL = "http://localhost:8000"
DOSSIER = Path("demo_data")


def recuperer_tout(source: str) -> pd.DataFrame:
    """Récupère toutes les lignes d'un domaine, page par page."""
    morceaux, offset = [], 0
    while True:
        r = requests.get(f"{API_URL}/curated",
                         params={"source": source, "limit": 1000, "offset": offset},
                         timeout=60)
        r.raise_for_status()
        donnees = r.json().get("donnees", [])
        if not donnees:
            break
        morceaux.append(pd.DataFrame(donnees))
        if len(donnees) < 1000:
            break
        offset += 1000
    return pd.concat(morceaux, ignore_index=True) if morceaux else pd.DataFrame()


def main() -> None:
    # On vérifie d'abord que l'API répond.
    try:
        requests.get(f"{API_URL}/health", timeout=10).raise_for_status()
    except Exception:
        print("❌ L'API ne répond pas. Lancez-la d'abord :")
        print("     uvicorn src.api.main:app")
        return

    DOSSIER.mkdir(exist_ok=True)

    # 1. Les statistiques du lake.
    stats = requests.get(f"{API_URL}/stats", timeout=30).json()
    (DOSSIER / "stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf-8")
    print(f"[export] stats.json  ({stats['curated']['total_rows']} lignes au total)")

    # 2. Les données de chaque domaine.
    for source in ("ecg", "eeg"):
        df = recuperer_tout(source)
        if df.empty:
            print(f"[export] ⚠️  aucune donnée pour '{source}' — ignoré.")
            continue
        # Le Parquet est compact : ~200 Ko pour 9 000 lignes, parfait pour Git.
        chemin = DOSSIER / f"curated_{source}.parquet"
        df.to_parquet(chemin, index=False)
        taille_ko = chemin.stat().st_size / 1024
        print(f"[export] curated_{source}.parquet  "
              f"({len(df)} lignes, {taille_ko:.0f} Ko)")

    print(f"\n✅ Instantané exporté dans '{DOSSIER}/'.")
    print("   Ce dossier DOIT être versionné dans Git : c'est lui qui alimente")
    print("   la démo en ligne quand l'API n'est pas joignable.")


if __name__ == "__main__":
    main()
