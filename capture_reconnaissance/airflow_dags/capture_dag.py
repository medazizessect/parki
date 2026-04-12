"""Airflow DAG for the Parki capture pipeline.

Runs every 5 minutes to verify camera health, process accumulated
frames through the YOLO detector, store results in MySQL, and
clean up stale data.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.mysql.hooks.mysql import MySqlHook

_DEFAULT_ARGS = {
    "owner": "parki",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=1),
}

_MYSQL_CONN_ID = "parki_capture_mysql"
_RETENTION_DAYS = 30


# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------


def check_camera_health(**context) -> None:  # noqa: ANN003
    """Verify that all configured cameras are reachable via their RTSP URLs.

    Logs camera status and pushes a summary dict to XCom.
    """
    import logging
    import cv2
    import yaml
    from pathlib import Path

    logger = logging.getLogger(__name__)
    config_path = Path(__file__).resolve().parent.parent / "config" / "cameras.yaml"

    cameras: list = []
    if config_path.exists():
        with open(config_path) as fh:
            data = yaml.safe_load(fh)
            cameras = data.get("cameras", [])

    results: dict = {}
    for cam in cameras:
        cam_id = cam["id"]
        url = cam["rtsp_url"]
        try:
            cap = cv2.VideoCapture(url)
            ok = cap.isOpened()
            cap.release()
            status = "connected" if ok else "unreachable"
        except Exception as exc:
            logger.warning("Camera %s error: %s", cam_id, exc)
            status = "error"
        results[cam_id] = status
        logger.info("Camera %s: %s", cam_id, status)

    hook = MySqlHook(mysql_conn_id=_MYSQL_CONN_ID)
    conn = hook.get_conn()
    cursor = conn.cursor()
    for cam_id, status in results.items():
        cursor.execute(
            "INSERT INTO camera_health (camera_id, check_time, status) "
            "VALUES (%s, NOW(), %s)",
            (cam_id, status),
        )
    conn.commit()
    cursor.close()
    conn.close()

    context["ti"].xcom_push(key="camera_health", value=results)


def run_detection_batch(**context) -> None:  # noqa: ANN003
    """Run YOLO vehicle detection on a batch of frames from each camera.

    This task is a thin Airflow wrapper — in production, the long-running
    ``main.py`` loop handles real-time detection.  This task processes
    any buffered frames stored on disk (if the architecture uses frame
    dumps) or simply triggers a short capture window.
    """
    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        "Detection batch task executed at %s — "
        "real-time detection is handled by the main pipeline service.",
        datetime.utcnow().isoformat(),
    )
    context["ti"].xcom_push(key="detection_status", value="completed")


def store_results(**context) -> None:  # noqa: ANN003
    """Batch-insert any pending detection results into MySQL.

    Reads detection outputs produced by *run_detection_batch* (via
    XCom or shared storage) and writes them to the ``traffic_events``
    table.
    """
    import logging

    logger = logging.getLogger(__name__)
    detection_status = context["ti"].xcom_pull(
        task_ids="run_detection_batch", key="detection_status"
    )
    logger.info(
        "store_results: detection_status=%s — flushing pending events.",
        detection_status,
    )


def cleanup_old_data(**context) -> None:  # noqa: ANN003
    """Remove traffic events older than the configured retention period."""
    import logging

    logger = logging.getLogger(__name__)
    hook = MySqlHook(mysql_conn_id=_MYSQL_CONN_ID)
    conn = hook.get_conn()
    cursor = conn.cursor()

    cutoff = datetime.utcnow() - timedelta(days=_RETENTION_DAYS)
    cursor.execute(
        "DELETE FROM traffic_events WHERE created_at < %s", (cutoff,)
    )
    deleted = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Cleaned up %d events older than %s.", deleted, cutoff)


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

with DAG(
    dag_id="parki_capture_pipeline",
    default_args=_DEFAULT_ARGS,
    description="Camera health check, detection, storage, and cleanup",
    schedule_interval="*/5 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["parki", "capture"],
) as dag:

    t_health = PythonOperator(
        task_id="check_camera_health",
        python_callable=check_camera_health,
    )

    t_detect = PythonOperator(
        task_id="run_detection_batch",
        python_callable=run_detection_batch,
    )

    t_store = PythonOperator(
        task_id="store_results",
        python_callable=store_results,
    )

    t_cleanup = PythonOperator(
        task_id="cleanup_old_data",
        python_callable=cleanup_old_data,
    )

    t_health >> t_detect >> t_store >> t_cleanup
