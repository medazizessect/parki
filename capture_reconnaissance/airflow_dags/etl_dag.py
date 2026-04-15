"""Circuli - ETL Pipeline DAG."""

import logging

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

logger = logging.getLogger("Circuli")

default_args = {
    "owner": "circuli",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
}


def extract_from_capture_db(**kwargs):
    """Extract detection data from the capture database."""
    logger.info("[Circuli] Extracting data from capture database")
    extracted = {"status": "extracted", "records": 0}
    kwargs["ti"].xcom_push(key="extracted", value=extracted)
    return extracted


def transform_data(**kwargs):
    """Transform raw detection data for analytics."""
    ti = kwargs["ti"]
    extracted = ti.xcom_pull(task_ids="extract_from_capture_db", key="extracted")
    logger.info("[Circuli] Transforming data: %s", extracted)
    transformed = {"status": "transformed", "records": 0}
    ti.xcom_push(key="transformed", value=transformed)
    return transformed


def load_to_analytics_db(**kwargs):
    """Load transformed data into the analytics database."""
    ti = kwargs["ti"]
    transformed = ti.xcom_pull(task_ids="transform_data", key="transformed")
    logger.info("[Circuli] Loading data to analytics DB: %s", transformed)
    return {"status": "loaded"}


with DAG(
    dag_id="circuli_etl",
    description="Circuli - ETL Pipeline",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=days_ago(1),
    catchup=False,
    tags=["circuli", "etl"],
) as dag:

    t_extract = PythonOperator(
        task_id="extract_from_capture_db",
        python_callable=extract_from_capture_db,
    )

    t_transform = PythonOperator(
        task_id="transform_data",
        python_callable=transform_data,
    )

    t_load = PythonOperator(
        task_id="load_to_analytics_db",
        python_callable=load_to_analytics_db,
    )

    t_extract >> t_transform >> t_load
