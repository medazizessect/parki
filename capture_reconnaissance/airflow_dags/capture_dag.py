"""Circuli - Video Capture Pipeline DAG."""

import json
import logging
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

logger = logging.getLogger("Circuli")

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "youtube_streams.json"

default_args = {
    "owner": "circuli",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
}


def extract_streams(**kwargs):
    """Load YouTube stream URLs from configuration."""
    logger.info("[Circuli] Extracting stream URLs from config")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    streams = [s for s in config.get("streams", []) if s.get("enabled", False)]
    logger.info("[Circuli] Found %d enabled streams", len(streams))
    kwargs["ti"].xcom_push(key="streams", value=streams)
    return streams


def capture_frames(**kwargs):
    """Capture frames from resolved stream URLs."""
    ti = kwargs["ti"]
    streams = ti.xcom_pull(task_ids="extract_streams", key="streams")
    logger.info("[Circuli] Capturing frames from %d streams", len(streams or []))
    # In production this would invoke VideoCapture; here we log the intent.
    captured = []
    for stream in (streams or []):
        logger.info("[Circuli] Capturing from stream %d: %s", stream["id"], stream["url"])
        captured.append({"stream_id": stream["id"], "status": "captured"})
    ti.xcom_push(key="captured", value=captured)
    return captured


def detect_vehicles(**kwargs):
    """Run YOLO vehicle detection on captured frames."""
    ti = kwargs["ti"]
    captured = ti.xcom_pull(task_ids="capture_frames", key="captured")
    logger.info("[Circuli] Running vehicle detection on %d captures", len(captured or []))
    results = []
    for item in (captured or []):
        logger.info("[Circuli] Detecting vehicles for stream %d", item["stream_id"])
        results.append({"stream_id": item["stream_id"], "detections": 0})
    ti.xcom_push(key="detection_results", value=results)
    return results


with DAG(
    dag_id="circuli_capture",
    description="Circuli - Video Capture Pipeline",
    default_args=default_args,
    schedule_interval="@hourly",
    start_date=days_ago(1),
    catchup=False,
    tags=["circuli", "capture"],
) as dag:

    t_extract = PythonOperator(
        task_id="extract_streams",
        python_callable=extract_streams,
    )

    t_capture = PythonOperator(
        task_id="capture_frames",
        python_callable=capture_frames,
    )

    t_detect = PythonOperator(
        task_id="detect_vehicles",
        python_callable=detect_vehicles,
    )

    t_extract >> t_capture >> t_detect
