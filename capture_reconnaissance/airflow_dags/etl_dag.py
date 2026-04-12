"""Airflow DAG for ETL from capture database to the BI data-mart.

Runs hourly to extract raw traffic events, compute aggregations,
and load results into the star-schema tables used by the BI layer.
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
    "retry_delay": timedelta(minutes=2),
}

_CAPTURE_CONN_ID = "parki_capture_mysql"
_DATAMART_CONN_ID = "parki_datamart_mysql"


# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------


def extract_raw_events(**context) -> None:  # noqa: ANN003
    """Extract raw traffic events from the capture database for the last hour."""
    import logging
    import json

    logger = logging.getLogger(__name__)
    execution_date: datetime = context["execution_date"]
    start_time = execution_date - timedelta(hours=1)
    end_time = execution_date

    hook = MySqlHook(mysql_conn_id=_CAPTURE_CONN_ID)
    conn = hook.get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT camera_id, event_timestamp, vehicle_type, confidence, "
        "speed_estimate, direction "
        "FROM traffic_events "
        "WHERE event_timestamp BETWEEN %s AND %s",
        (start_time, end_time),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # Serialise datetime objects for XCom
    serialisable = []
    for row in rows:
        r = dict(row)
        if isinstance(r.get("event_timestamp"), datetime):
            r["event_timestamp"] = r["event_timestamp"].isoformat()
        serialisable.append(r)

    context["ti"].xcom_push(key="raw_events", value=json.dumps(serialisable))
    logger.info(
        "Extracted %d events for window %s → %s.",
        len(rows),
        start_time.isoformat(),
        end_time.isoformat(),
    )


def transform_aggregations(**context) -> None:  # noqa: ANN003
    """Compute hourly aggregations from raw events.

    Aggregates:
    - Count by vehicle type per camera
    - Average speed per camera
    - Peak hour indicator
    """
    import json
    import logging
    from collections import defaultdict

    logger = logging.getLogger(__name__)
    raw_json = context["ti"].xcom_pull(
        task_ids="extract_raw_events", key="raw_events"
    )
    if not raw_json:
        logger.warning("No raw events to transform.")
        context["ti"].xcom_push(key="aggregations", value="[]")
        return

    events = json.loads(raw_json)
    agg: dict = defaultdict(lambda: {
        "total_count": 0,
        "speed_sum": 0.0,
        "type_counts": defaultdict(int),
    })

    for ev in events:
        key = ev["camera_id"]
        agg[key]["total_count"] += 1
        agg[key]["speed_sum"] += float(ev.get("speed_estimate", 0))
        agg[key]["type_counts"][ev["vehicle_type"]] += 1

    results = []
    execution_date: datetime = context["execution_date"]
    hour_label = (execution_date - timedelta(hours=1)).strftime("%Y-%m-%d %H:00:00")

    for camera_id, data in agg.items():
        total = data["total_count"]
        avg_speed = round(data["speed_sum"] / total, 2) if total else 0.0
        for vtype, count in data["type_counts"].items():
            results.append({
                "hour": hour_label,
                "camera_id": camera_id,
                "vehicle_type": vtype,
                "vehicle_count": count,
                "avg_speed": avg_speed,
                "total_events": total,
            })

    context["ti"].xcom_push(key="aggregations", value=json.dumps(results))
    logger.info("Produced %d aggregation rows.", len(results))


def load_datamart(**context) -> None:  # noqa: ANN003
    """Insert aggregated data into the BI star-schema tables."""
    import json
    import logging

    logger = logging.getLogger(__name__)
    agg_json = context["ti"].xcom_pull(
        task_ids="transform_aggregations", key="aggregations"
    )
    if not agg_json:
        logger.warning("No aggregations to load.")
        return

    rows = json.loads(agg_json)
    if not rows:
        logger.info("Aggregation list is empty — nothing to load.")
        return

    hook = MySqlHook(mysql_conn_id=_DATAMART_CONN_ID)
    conn = hook.get_conn()
    cursor = conn.cursor()

    insert_sql = (
        "INSERT INTO fact_traffic_hourly "
        "(hour, camera_id, vehicle_type, vehicle_count, avg_speed, total_events) "
        "VALUES (%s, %s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE "
        "vehicle_count = VALUES(vehicle_count), "
        "avg_speed = VALUES(avg_speed), "
        "total_events = VALUES(total_events)"
    )

    for row in rows:
        cursor.execute(
            insert_sql,
            (
                row["hour"],
                row["camera_id"],
                row["vehicle_type"],
                row["vehicle_count"],
                row["avg_speed"],
                row["total_events"],
            ),
        )

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Loaded %d rows into the data-mart.", len(rows))


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------

with DAG(
    dag_id="parki_etl_to_datamart",
    default_args=_DEFAULT_ARGS,
    description="Hourly ETL from capture DB to BI data-mart (star schema)",
    schedule_interval="0 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["parki", "etl", "datamart"],
) as dag:

    t_extract = PythonOperator(
        task_id="extract_raw_events",
        python_callable=extract_raw_events,
    )

    t_transform = PythonOperator(
        task_id="transform_aggregations",
        python_callable=transform_aggregations,
    )

    t_load = PythonOperator(
        task_id="load_datamart",
        python_callable=load_datamart,
    )

    t_extract >> t_transform >> t_load
