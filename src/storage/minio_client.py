"""
minio_client.py
---------------
Petit assistant pour parler à l'entrepôt de fichiers MinIO.

Il sait faire 4 choses simples :
  - se connecter à MinIO
  - créer les buckets (raw, staging) s'ils n'existent pas encore
  - déposer un fichier (upload)
  - récupérer un fichier (download)

Le reste du projet utilisera ces fonctions au lieu de réécrire à chaque fois
le code de connexion.
"""

from pathlib import Path

from minio import Minio

from src.config import config


def get_client() -> Minio:
    """Crée et renvoie une connexion à MinIO en utilisant la config."""
    return Minio(
        config.MINIO_ENDPOINT,
        access_key=config.MINIO_ACCESS_KEY,
        secret_key=config.MINIO_SECRET_KEY,
        secure=config.MINIO_SECURE,
    )


def ensure_buckets() -> None:
    """
    Vérifie que les buckets raw et staging existent ; les crée sinon.
    À lancer une fois au démarrage du projet.
    """
    client = get_client()
    for bucket in (config.BUCKET_RAW, config.BUCKET_STAGING):
        if client.bucket_exists(bucket):
            print(f"[MinIO] bucket '{bucket}' : déjà présent.")
        else:
            client.make_bucket(bucket)
            print(f"[MinIO] bucket '{bucket}' : créé.")


def upload_file(bucket: str, object_name: str, local_path: str) -> None:
    """
    Dépose un fichier local dans un bucket.

    Args:
        bucket: nom du bucket de destination (ex: "raw")
        object_name: nom/chemin sous lequel ranger le fichier dans le bucket
        local_path: chemin du fichier sur ton disque
    """
    client = get_client()
    client.fput_object(bucket, object_name, local_path)
    print(f"[MinIO] envoyé : {local_path} -> {bucket}/{object_name}")


def download_file(bucket: str, object_name: str, local_path: str) -> None:
    """Récupère un fichier depuis un bucket et le sauvegarde sur le disque."""
    client = get_client()
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    client.fget_object(bucket, object_name, local_path)
    print(f"[MinIO] récupéré : {bucket}/{object_name} -> {local_path}")


def list_objects(bucket: str, prefix: str = "") -> list[dict]:
    """
    Liste les fichiers présents dans un bucket.
    Utilisé par les endpoints GET /raw et GET /staging.
    """
    client = get_client()
    objects = client.list_objects(bucket, prefix=prefix, recursive=True)
    return [
        {
            "name": obj.object_name,
            "size_bytes": obj.size,
            "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
        }
        for obj in objects
    ]


def bucket_stats(bucket: str) -> dict:
    """
    Statistiques d'un bucket : nombre de fichiers et taille totale.
    Utilisé par GET /stats.
    """
    try:
        objects = list_objects(bucket)
    except Exception as err:
        return {"bucket": bucket, "erreur": str(err)}

    total_size = sum(o["size_bytes"] or 0 for o in objects)
    return {
        "bucket": bucket,
        "n_objets": len(objects),
        "taille_totale_octets": total_size,
        "taille_totale_mo": round(total_size / (1024 * 1024), 2),
    }


def ping() -> bool:
    """Vérifie que MinIO répond. Utilisé par GET /health."""
    try:
        get_client().list_buckets()
        return True
    except Exception:
        return False


# Si on lance ce fichier directement (python -m src.storage.minio_client),
# on en profite pour créer les buckets. Pratique pour tester la connexion.
if __name__ == "__main__":
    print("Connexion à MinIO et vérification des buckets...")
    ensure_buckets()
    print("OK : l'entrepôt est prêt.")
