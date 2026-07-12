"""
dag_ecg.py — Le DAG du pipeline ECG
------------------------------------
Un DAG (Directed Acyclic Graph) décrit un ENCHAÎNEMENT DE TÂCHES à Airflow.
Traduction : "fais ça, puis ça, puis ça — et si une étape rate, arrête-toi".

Ici on décrit le pipeline ECG complet :

    [1. ingestion]  ->  [2. staging]  ->  [3. curated]
     télécharge          extrait les       entraîne le modèle
     MIT-BIH             features          et remplit la base

Airflow se charge de :
  - lancer les tâches dans le bon ordre
  - réessayer automatiquement en cas d'échec passager
  - afficher tout ça en vert (ou en rouge) dans son interface web

Ce DAG n'a PAS de planification automatique (schedule=None) : on le déclenche
à la main depuis l'interface. C'est logique — le dataset MIT-BIH est statique,
inutile de le retélécharger toutes les heures. (Le DAG de l'air, lui, sera
planifié : voir dag_air.py.)
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


# --- Les fonctions appelées par chaque tâche ---
# On importe DANS les fonctions (et pas en haut du fichier) car Airflow relit
# ce fichier très souvent : on évite ainsi de charger des grosses librairies
# (pandas, sklearn...) à chaque fois. C'est une bonne pratique Airflow.

def tache_ingestion():
    """Étape 1 : télécharge les enregistrements MIT-BIH -> zone raw."""
    from src.ingestion.ingest_ecg import ingest_all
    ingest_all()


def tache_staging():
    """Étape 2 : lit les signaux bruts, extrait les features -> zone staging."""
    from src.pipelines.run_ecg import run
    run()


def tache_curated():
    """Étape 3 : entraîne le modèle et remplit la zone curated."""
    from src.models.train_ecg import train
    train()


# --- Les réglages par défaut appliqués à toutes les tâches ---
default_args = {
    "owner": "datalake",
    # Si une tâche échoue, Airflow la réessaie automatiquement...
    "retries": 2,
    # ...en attendant 1 minute entre chaque essai.
    "retry_delay": timedelta(minutes=1),
}


# --- La définition du DAG lui-même ---
with DAG(
    dag_id="pipeline_ecg",
    description="Pipeline ECG complet : MIT-BIH -> raw -> staging -> curated",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    # schedule=None : pas de déclenchement automatique, on le lance à la main.
    schedule=None,
    # catchup=False : n'essaie PAS de rattraper toutes les exécutions passées
    # depuis start_date (sinon Airflow lancerait des centaines de runs !).
    catchup=False,
    tags=["ecg", "medical", "batch"],
) as dag:

    ingestion = PythonOperator(
        task_id="ingestion_raw",
        python_callable=tache_ingestion,
        doc_md="Télécharge les enregistrements MIT-BIH et les dépose dans MinIO (zone raw).",
    )

    staging = PythonOperator(
        task_id="transformation_staging",
        python_callable=tache_staging,
        doc_md="Extrait les features par battement et les écrit en Parquet (zone staging).",
    )

    curated = PythonOperator(
        task_id="modele_curated",
        python_callable=tache_curated,
        doc_md="Entraîne le modèle de détection d'anomalies et remplit PostgreSQL (zone curated).",
    )

    # ⬇️ LA LIGNE LA PLUS IMPORTANTE : elle définit l'ORDRE des tâches.
    # Le ">>" se lit "puis". Airflow ne lancera 'staging' que si 'ingestion'
    # a réussi, etc.
    ingestion >> staging >> curated
