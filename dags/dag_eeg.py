"""
dag_eeg.py — Le DAG du pipeline EEG
------------------------------------
Copie conforme (à 3 mots près) du DAG ECG. C'est VOULU, et c'est la preuve que
l'architecture tient : ajouter un domaine ne demande aucune invention.

    [1. ingestion]  ->  [2. staging]  ->  [3. curated]
     CHB-MIT (.edf)     bandes de freq.   modèle de détection de crises

Pas de scheduling (schedule=None) : le dataset est statique, on déclenche à la
main. ⏳ Attention, la tâche d'ingestion télécharge ~170 Mo : elle est lente.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def tache_ingestion():
    """Étape 1 : télécharge les .edf CHB-MIT -> zone raw."""
    from src.ingestion.ingest_eeg import ingest
    ingest()


def tache_staging():
    """Étape 2 : filtrage + fenêtrage + puissances par bande -> zone staging."""
    from src.pipelines.run_eeg import run
    run()


def tache_curated():
    """Étape 3 : entraîne le détecteur de crises et remplit la zone curated."""
    from src.models.train_eeg import train
    train()


default_args = {
    "owner": "datalake",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}


with DAG(
    dag_id="pipeline_eeg",
    description="Pipeline EEG : CHB-MIT -> raw -> staging -> curated (crises d'épilepsie)",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["eeg", "medical", "batch"],
) as dag:

    ingestion = PythonOperator(
        task_id="ingestion_raw",
        python_callable=tache_ingestion,
        doc_md="Télécharge les enregistrements EEG CHB-MIT (~170 Mo) vers MinIO.",
        # Le téléchargement peut être long : on laisse de la marge.
        execution_timeout=timedelta(minutes=30),
    )

    staging = PythonOperator(
        task_id="transformation_staging",
        python_callable=tache_staging,
        doc_md="Filtre le signal (0.5-45 Hz), le découpe en fenêtres de 5 s, "
               "et calcule la puissance dans chaque bande de fréquence.",
        execution_timeout=timedelta(minutes=30),
    )

    curated = PythonOperator(
        task_id="modele_curated",
        python_callable=tache_curated,
        doc_md="Entraîne le détecteur de crises et écrit les résultats en base.",
    )

    ingestion >> staging >> curated
