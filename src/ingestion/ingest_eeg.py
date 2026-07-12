"""
ingest_eeg.py — LE TROISIÈME DOMAINE : l'EEG (détection de crises d'épilepsie)
------------------------------------------------------------------------------
On ajoute un 3e type de données au data lake, sans rien casser de l'existant.

LE DATASET : CHB-MIT Scalp EEG Database (PhysioNet)
Des enregistrements EEG d'enfants épileptiques, réalisés au Children's Hospital
de Boston. Chaque fichier .edf contient ~1 heure de signal, sur 23 canaux
(23 électrodes posées sur le crâne), échantillonné à 256 Hz.

⚠️ CE QUI REND CE PROBLÈME DIFFICILE (à dire dans le rapport) :
Les crises sont RARISSIMES : environ 40 à 90 secondes de crise sur 1 HEURE
d'enregistrement, soit ~1 à 2 % du signal. C'est un déséquilibre de classes
bien plus violent que sur l'ECG. On s'attend donc à des résultats plus
difficiles, et c'est normal.

LES FICHIERS :
On prend 4 enregistrements du patient chb01 qui CONTIENNENT des crises.
Chacun pèse ~42 Mo -> ~170 Mo au total. C'est volontairement limité :
le dataset complet fait plusieurs dizaines de Go.

Le fichier chb01-summary.txt donne les horaires exacts des crises : c'est notre
"vérité terrain", l'équivalent des annotations des cardiologues pour l'ECG.

Pour lancer :
    python -m src.ingestion.ingest_eeg
"""

import tempfile
from pathlib import Path

import requests

from src.config import config
from src.storage.minio_client import ensure_buckets, upload_file

# L'adresse des fichiers sur PhysioNet.
BASE_URL = "https://physionet.org/files/chbmit/1.0.0/chb01"

# Le patient qu'on étudie.
PATIENT = "chb01"

# Les enregistrements retenus : tous CONTIENNENT au moins une crise.
# (Prendre des fichiers sans crise n'apporterait que des exemples négatifs,
#  dont on a déjà largement assez.)
RECORDS = [
    "chb01_03",   # 1 crise (40 s)
    "chb01_04",   # 1 crise (27 s)
    "chb01_16",   # 1 crise (51 s)
    "chb01_18",   # 1 crise (90 s)
]

# Le fichier qui décrit les crises (nos étiquettes).
SUMMARY_FILE = f"{PATIENT}-summary.txt"


def _telecharger(url: str, destination: Path) -> None:
    """
    Télécharge un fichier depuis une URL, par morceaux (streaming).

    Pourquoi par morceaux ? Un .edf fait 42 Mo : le charger d'un bloc en mémoire
    serait inutilement lourd. On l'écrit au fur et à mesure sur le disque.
    """
    with requests.get(url, stream=True, timeout=120) as reponse:
        if reponse.status_code != 200:
            raise RuntimeError(
                f"Téléchargement impossible ({reponse.status_code}) : {url}"
            )
        with open(destination, "wb") as f:
            for morceau in reponse.iter_content(chunk_size=1024 * 256):
                f.write(morceau)


def ingest() -> None:
    """
    Télécharge les enregistrements EEG + le fichier d'annotations, et les dépose
    TELS QUELS dans la zone raw de MinIO (sous eeg/).
    """
    ensure_buckets()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # --- 1. Le fichier d'annotations (les horaires de crises) ---
        print(f"[eeg] téléchargement des annotations ({SUMMARY_FILE})...")
        summary_local = tmp_dir / SUMMARY_FILE
        try:
            _telecharger(f"{BASE_URL}/{SUMMARY_FILE}", summary_local)
            upload_file(config.BUCKET_RAW, f"eeg/{SUMMARY_FILE}", str(summary_local))
        except Exception as err:
            raise RuntimeError(
                f"Impossible de récupérer les annotations : {err}\n"
                "Sans elles, on ne peut pas savoir où sont les crises."
            )

        # --- 2. Les enregistrements EEG ---
        total = 0
        for record_id in RECORDS:
            fichier = f"{record_id}.edf"
            print(f"[eeg] téléchargement de {fichier} (~42 Mo, patience)...")

            local = tmp_dir / fichier
            try:
                _telecharger(f"{BASE_URL}/{fichier}", local)
            except Exception as err:
                # On loggue et on continue : un fichier manquant ne doit pas
                # faire échouer toute l'ingestion.
                print(f"[eeg] ❌ échec pour {fichier} : {err}")
                continue

            taille_mo = local.stat().st_size / (1024 * 1024)
            upload_file(config.BUCKET_RAW, f"eeg/{fichier}", str(local))
            print(f"[eeg]    -> déposé ({taille_mo:.1f} Mo)\n")
            total += 1

    print(f"[eeg] ✅ terminé : {total} enregistrements + les annotations "
          f"dans '{config.BUCKET_RAW}/eeg/'.")


if __name__ == "__main__":
    ingest()
