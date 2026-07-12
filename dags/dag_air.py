"""
dag_air.py — Le DAG de la source API (qualité de l'air)
--------------------------------------------------------
Contrairement au DAG ECG (qu'on lance à la main), celui-ci est PLANIFIÉ : il se
déclenche TOUT SEUL à intervalle régulier pour interroger l'API OpenAQ.

C'est exactement ce que demande le sujet :
  "Si vous utilisez Airflow, pensez à utiliser la fonctionnalité de scheduling
   pour ingérer des données depuis l'API à intervalle régulier."

Chaque exécution crée un nouvel instantané horodaté → on construit un historique
de la qualité de l'air, sans jamais écraser les mesures précédentes.

BONUS — XCom :
Le sujet suggère d'expérimenter avec XCom. XCom (= "cross-communication") permet
à une tâche de PASSER UNE INFORMATION à la tâche suivante. Ici, la tâche
d'ingestion transmet le nom de l'instantané qu'elle vient de créer, et la tâche
de staging le récupère pour savoir quoi traiter. Sans XCom, la 2e tâche devrait
deviner ou re-lister le bucket.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


def tache_ingestion_api(**context):
    """
    Étape 1 : interroge l'API OpenAQ et dépose un instantané JSON en zone raw.

    Renvoie l'identifiant de l'instantané créé. ⚠️ Tout ce qu'une fonction de
    tâche renvoie (`return`) est AUTOMATIQUEMENT poussé dans XCom par Airflow,
    et devient récupérable par les tâches suivantes.
    """
    from src.ingestion.ingest_air import fetch_locations, ensure_buckets, upload_file
    from src.config import config
    from datetime import timezone
    import json, tempfile
    from pathlib import Path

    ensure_buckets()
    results = fetch_locations()

    if not results:
        # Si l'API ne renvoie rien, on lève une erreur : Airflow marquera la
        # tâche en rouge et réessaiera (cf. retries). Mieux vaut échouer
        # bruyamment que d'écrire un fichier vide en silence.
        raise ValueError("L'API OpenAQ n'a retourné aucun résultat.")

    now = datetime.now(timezone.utc)
    record_id = now.strftime("%Y-%m-%dT%H-%M-%SZ")
    object_name = f"air/{record_id}.json"

    payload = {
        "source": "openaq_v3",
        "fetched_at": now.isoformat(),
        "n_results": len(results),
        "results": results,
    }

    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "air.json"
        local.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        upload_file(config.BUCKET_RAW, object_name, str(local))

    print(f"[air] instantané créé : {record_id} ({len(results)} capteurs)")

    # ⬇️ C'EST ICI QUE XCOM ENTRE EN JEU.
    # Cette valeur sera récupérable par la tâche suivante.
    return record_id


def tache_staging_api(**context):
    """
    Étape 2 : transforme l'instantané en features (zone staging).

    Récupère via XCom l'identifiant de l'instantané créé par la tâche
    précédente, au lieu de le deviner.
    """
    from src.processors.air import AirQualityProcessor
    from src.storage.minio_client import upload_file
    from src.config import config
    import tempfile
    from pathlib import Path

    # ⬇️ RÉCUPÉRATION XCOM : on demande à Airflow ce qu'a renvoyé la tâche
    # "ingestion_api".
    ti = context["ti"]  # "ti" = task instance
    record_id = ti.xcom_pull(task_ids="ingestion_api")

    if not record_id:
        raise ValueError("Aucun record_id reçu via XCom depuis la tâche d'ingestion.")

    print(f"[air] XCom a transmis l'instantané à traiter : {record_id}")

    processor = AirQualityProcessor()
    features = processor.run(record_id)

    if features.empty:
        raise ValueError(f"Aucune feature extraite pour l'instantané {record_id}.")

    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / f"{record_id}.parquet"
        features.to_parquet(local, index=False)
        upload_file(config.BUCKET_STAGING, f"air/{record_id}.parquet", str(local))

    print(f"[air] {len(features)} lignes écrites en staging.")
    return len(features)


default_args = {
    "owner": "datalake",
    "retries": 3,   # l'API peut être temporairement indisponible : on insiste
    "retry_delay": timedelta(minutes=2),
}


with DAG(
    dag_id="pipeline_air_quality",
    description="Ingestion planifiée de la qualité de l'air (API OpenAQ) + XCom",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),

    # ⬇️ LE SCHEDULING : ce DAG se déclenche TOUT SEUL, toutes les heures.
    # (Format "cron" : minute heure jour mois jour_semaine.
    #  "0 * * * *" = à la minute 0 de chaque heure.)
    schedule="0 * * * *",

    catchup=False,
    max_active_runs=1,   # une seule exécution à la fois (pas d'embouteillage)
    tags=["air", "api", "streaming"],
) as dag:

    ingestion = PythonOperator(
        task_id="ingestion_api",
        python_callable=tache_ingestion_api,
        doc_md="Interroge l'API OpenAQ et dépose un instantané JSON horodaté (zone raw).",
    )

    staging = PythonOperator(
        task_id="transformation_staging",
        python_callable=tache_staging_api,
        doc_md="Récupère l'instantané via XCom, aplatit le JSON en features (zone staging).",
    )

    ingestion >> staging
