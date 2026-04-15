"""Circuli - Data Processing Pipeline DAG."""

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


def process_detections(**kwargs):
    """Process raw vehicle detection results."""
    logger.info("[Circuli] Processing detection results")
    processed = {"status": "processed", "records": 0}
    kwargs["ti"].xcom_push(key="processed", value=processed)
    return processed


def aggregate_data(**kwargs):
    """Aggregate processed detections into summaries."""
    ti = kwargs["ti"]
    processed = ti.xcom_pull(task_ids="process_detections", key="processed")
    logger.info("[Circuli] Aggregating data: %s", processed)
    aggregated = {"status": "aggregated", "summaries": 0}
    ti.xcom_push(key="aggregated", value=aggregated)
    return aggregated


def export_results(**kwargs):
    """Export aggregated results for downstream consumption."""
    ti = kwargs["ti"]
    aggregated = ti.xcom_pull(task_ids="aggregate_data", key="aggregated")
    logger.info("[Circuli] Exporting results: %s", aggregated)
    return {"status": "exported"}


with DAG(
    dag_id="circuli_processing",
    description="Circuli - Data Processing Pipeline",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=days_ago(1),
    catchup=False,
    tags=["circuli", "processing"],
) as dag:

    t_process = PythonOperator(
        task_id="process_detections",
        python_callable=process_detections,
    )

    t_aggregate = PythonOperator(
        task_id="aggregate_data",
        python_callable=aggregate_data,
    )

    t_export = PythonOperator(
        task_id="export_results",
        python_callable=export_results,
    )

    t_process >> t_aggregate >> t_export
