"""
ingest_ecg.py  — ÉTAPE 1 (1/3) : l'ingestion
--------------------------------------------
Premier maillon du pipeline ECG. Son rôle est SIMPLE et unique :
  1. télécharger quelques enregistrements cardiaques réels du dataset MIT-BIH
     (hébergé sur PhysioNet),
  2. les déposer TELS QUELS dans la zone raw de notre entrepôt MinIO.

⚠️ On ne transforme RIEN ici. La zone raw doit rester une copie fidèle de la
source. Le nettoyage et l'extraction des features viendront à l'étape suivante
(le processeur ECG). C'est la règle d'or du data lake : on ne touche jamais au
brut.

Comment le lancer (une fois MinIO démarré) :
    python -m src.ingestion.ingest_ecg
"""

import tempfile
from pathlib import Path

import wfdb  # librairie officielle pour lire/télécharger les données PhysioNet

from src.config import config
from src.storage.minio_client import ensure_buckets, upload_file

# Le nom du dataset sur PhysioNet. "mitdb" = MIT-BIH Arrhythmia Database.
DATASET = "mitdb"

# On ne prend que quelques enregistrements pour commencer (pas les 48).
# Chaque enregistrement = un patient. On pourra en ajouter plus tard.
RECORDS = ["100", "101", "102"]

# Chaque enregistrement MIT-BIH est composé de 3 fichiers :
#   .dat = le signal lui-même (les valeurs du tracé cardiaque)
#   .hea = l'en-tête (infos : durée, fréquence d'échantillonnage...)
#   .atr = les annotations des cardiologues (où sont les battements, leur type)
EXTENSIONS = [".dat", ".hea", ".atr"]


def download_record(record_id: str, dest_dir: Path) -> list[Path]:
    """
    Télécharge un enregistrement depuis PhysioNet dans un dossier local.

    Args:
        record_id: l'identifiant de l'enregistrement (ex: "100")
        dest_dir: le dossier local où déposer les fichiers téléchargés

    Returns:
        La liste des chemins des fichiers téléchargés.
    """
    print(f"[ingest] téléchargement de l'enregistrement '{record_id}'...")

    # wfdb télécharge les fichiers de l'enregistrement demandé.
    wfdb.dl_files(
        db=DATASET,
        dl_dir=str(dest_dir),
        files=[f"{record_id}{ext}" for ext in EXTENSIONS],
    )

    # On récupère la liste des fichiers effectivement présents sur le disque.
    downloaded = []
    for ext in EXTENSIONS:
        file_path = dest_dir / f"{record_id}{ext}"
        if file_path.exists():
            downloaded.append(file_path)
        else:
            # Certains enregistrements n'ont pas toutes les extensions : on
            # prévient sans planter (gestion de cas, demandée par le sujet).
            print(f"[ingest] ⚠️  fichier absent (ignoré) : {file_path.name}")
    return downloaded


def ingest_all() -> None:
    """
    Point d'entrée : télécharge tous les enregistrements listés et les envoie
    dans la zone raw de MinIO.
    """
    # On s'assure d'abord que les buckets existent (au cas où).
    ensure_buckets()

    # On télécharge dans un dossier temporaire qui s'efface tout seul à la fin :
    # inutile de garder les fichiers en local, ils vivent maintenant dans MinIO.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        total = 0

        for record_id in RECORDS:
            try:
                files = download_record(record_id, tmp_dir)
            except Exception as err:
                # Si le téléchargement échoue (réseau coupé, id inconnu...),
                # on log l'erreur et on continue avec les autres.
                print(f"[ingest] ❌ échec pour '{record_id}' : {err}")
                continue

            # On dépose chaque fichier dans le bucket raw, rangé sous un
            # sous-dossier "ecg/" pour bien séparer les sources.
            for file_path in files:
                object_name = f"ecg/{file_path.name}"
                upload_file(config.BUCKET_RAW, object_name, str(file_path))
                total += 1

        print(f"\n[ingest] ✅ terminé : {total} fichiers déposés dans "
              f"'{config.BUCKET_RAW}/ecg/'.")


if __name__ == "__main__":
    ingest_all()
