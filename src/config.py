"""
config.py
---------
Un seul endroit pour TOUS les paramètres du projet (adresses, identifiants,
noms de buckets...). Le reste du code viendra piocher ici, comme ça si on
change un mot de passe on ne le modifie qu'à un seul endroit.

Les valeurs sont lues depuis le fichier .env (voir .env.example).
"""

import os
from dotenv import load_dotenv

# Charge le contenu du fichier .env dans les variables d'environnement.
load_dotenv()


class Config:
    """Regroupe tous les réglages sous forme d'attributs faciles à utiliser."""

    # --- MinIO (l'entrepôt de fichiers) ---
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
    MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
    MINIO_SECURE = False  # False = pas de HTTPS (on est en local, c'est normal)

    # --- Noms des buckets (les "dossiers" de stockage) ---
    BUCKET_RAW = os.getenv("BUCKET_RAW", "raw")
    BUCKET_STAGING = os.getenv("BUCKET_STAGING", "staging")

    # --- PostgreSQL (la base de données, zone curated) ---
    POSTGRES_USER = os.getenv("POSTGRES_USER", "datalake")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "datalake")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "datalake")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

    # --- Source API : OpenAQ (qualité de l'air) ---
    # Clé gratuite à récupérer sur https://explore.openaq.org/register
    OPENAQ_API_KEY = os.getenv("OPENAQ_API_KEY", "")

    @property
    def postgres_url(self) -> str:
        """Construit l'adresse complète de connexion à PostgreSQL."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


# On crée un objet config unique que tout le projet importera.
config = Config()
