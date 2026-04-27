"""
Star Schema Management for the BI Datamart.

Creates and populates dimension / fact tables and provides
aggregation helpers used by the analytics layer.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from .database import DatamartConnection

logger = logging.getLogger(__name__)


class DatamartManager:
    """Manages the star-schema lifecycle: DDL, dimension population, and aggregations."""

    def __init__(self, db: Optional[DatamartConnection] = None) -> None:
        self._db = db or DatamartConnection()

    # ------------------------------------------------------------------
    # DDL helpers
    # ------------------------------------------------------------------
    def create_dimension_tables(self) -> None:
        """Create all dimension tables if they do not exist."""
        ddl_statements = [
            # dim_time
            """
            CREATE TABLE IF NOT EXISTS dim_time (
                time_id      INT AUTO_INCREMENT PRIMARY KEY,
                hour         TINYINT  NOT NULL,
                day          TINYINT  NOT NULL,
                day_of_week  TINYINT  NOT NULL,
                week         TINYINT  NOT NULL,
                month        TINYINT  NOT NULL,
                quarter      TINYINT  NOT NULL,
                year         SMALLINT NOT NULL,
                is_weekend   BOOLEAN  NOT NULL DEFAULT FALSE,
                is_peak_hour BOOLEAN  NOT NULL DEFAULT FALSE,
                UNIQUE KEY uq_time (year, month, day, hour)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # dim_vehicle_type
            """
            CREATE TABLE IF NOT EXISTS dim_vehicle_type (
                vehicle_type_id INT AUTO_INCREMENT PRIMARY KEY,
                type_name       VARCHAR(50)  NOT NULL UNIQUE,
                category        VARCHAR(50)  NOT NULL,
                description     VARCHAR(255) NOT NULL DEFAULT ''
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # dim_camera
            """
            CREATE TABLE IF NOT EXISTS dim_camera (
                camera_id         INT AUTO_INCREMENT PRIMARY KEY,
                camera_name       VARCHAR(100) NOT NULL,
                status            VARCHAR(20)  NOT NULL DEFAULT 'active',
                installation_date DATE         NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            # dim_location
            """
            CREATE TABLE IF NOT EXISTS dim_location (
                location_id INT AUTO_INCREMENT PRIMARY KEY,
                latitude    DECIMAL(10, 7) NOT NULL,
                longitude   DECIMAL(10, 7) NOT NULL,
                zone_name   VARCHAR(100)   NOT NULL DEFAULT '',
                road_name   VARCHAR(150)   NOT NULL DEFAULT '',
                road_type   VARCHAR(50)    NOT NULL DEFAULT '',
                city        VARCHAR(100)   NOT NULL DEFAULT '',
                district    VARCHAR(100)   NOT NULL DEFAULT ''
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
        ]
        for stmt in ddl_statements:
            self._db.execute(stmt, fetch=False)
        logger.info("Dimension tables created/verified.")

    def create_fact_table(self) -> None:
        """Create the fact table if it does not exist."""
        stmt = """
            CREATE TABLE IF NOT EXISTS fact_traffic_events (
                event_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
                time_id          INT NOT NULL,
                vehicle_type_id  INT NOT NULL,
                camera_id        INT NOT NULL,
                location_id      INT NOT NULL,
                vehicle_count    INT NOT NULL DEFAULT 0,
                avg_speed        DECIMAL(6, 2) DEFAULT NULL,
                max_speed        DECIMAL(6, 2) DEFAULT NULL,
                min_speed        DECIMAL(6, 2) DEFAULT NULL,
                total_events     INT NOT NULL DEFAULT 0,
                congestion_level DECIMAL(4, 2) DEFAULT 0.00,
                FOREIGN KEY (time_id)         REFERENCES dim_time(time_id),
                FOREIGN KEY (vehicle_type_id) REFERENCES dim_vehicle_type(vehicle_type_id),
                FOREIGN KEY (camera_id)       REFERENCES dim_camera(camera_id),
                FOREIGN KEY (location_id)     REFERENCES dim_location(location_id),
                INDEX idx_fact_time     (time_id),
                INDEX idx_fact_camera   (camera_id),
                INDEX idx_fact_vehicle  (vehicle_type_id),
                INDEX idx_fact_location (location_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        self._db.execute(stmt, fetch=False)
        logger.info("Fact table created/verified.")

    def create_all_tables(self) -> None:
        """Create every table in the correct order."""
        self.create_dimension_tables()
        self.create_fact_table()
        logger.info("All star-schema tables ready.")

    # ------------------------------------------------------------------
    # Dimension population
    # ------------------------------------------------------------------
    def populate_time_dimension(
        self,
        start_date: date = date(2024, 1, 1),
        end_date: date = date(2026, 12, 31),
    ) -> int:
        """Populate dim_time for every hour in [start_date, end_date].

        Peak hours are defined as 07-09 and 17-19.
        """
        peak_hours = set(range(7, 10)) | set(range(17, 20))
        rows: list[tuple] = []
        current = start_date
        while current <= end_date:
            iso = current.isocalendar()
            for hour in range(24):
                rows.append((
                    hour,
                    current.day,
                    current.isoweekday(),         # 1=Mon … 7=Sun
                    iso[1],                        # ISO week
                    current.month,
                    (current.month - 1) // 3 + 1, # quarter
                    current.year,
                    current.isoweekday() >= 6,     # is_weekend
                    hour in peak_hours,            # is_peak_hour
                ))
            current += timedelta(days=1)

        query = """
            INSERT IGNORE INTO dim_time
                (hour, day, day_of_week, week, month, quarter, year, is_weekend, is_peak_hour)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        count = self._db.execute_many(query, rows)
        logger.info("Inserted %d rows into dim_time.", count)
        return count

    def populate_vehicle_types(self) -> int:
        """Seed dim_vehicle_type with standard vehicle categories."""
        types = [
            ("car", "light", "Passenger car"),
            ("motorcycle", "light", "Motorcycle / scooter"),
            ("pickup_truck", "light", "Pickup truck"),
            ("suv", "light", "Sport utility vehicle"),
            ("van", "light", "Van / minivan"),
            ("bus", "heavy", "City or intercity bus"),
            ("truck", "heavy", "Heavy goods truck"),
            ("semi_trailer", "heavy", "Semi-trailer / articulated truck"),
            ("bicycle", "non_motorized", "Bicycle"),
            ("pedestrian", "non_motorized", "Pedestrian (detected)"),
        ]
        query = """
            INSERT IGNORE INTO dim_vehicle_type (type_name, category, description)
            VALUES (%s, %s, %s)
        """
        count = self._db.execute_many(query, types)
        logger.info("Inserted %d rows into dim_vehicle_type.", count)
        return count

    def populate_all_dimensions(self) -> None:
        """Populate every dimension table with initial seed data."""
        self.populate_time_dimension()
        self.populate_vehicle_types()
        logger.info("All dimension tables populated.")

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------
    def aggregate_hourly_stats(self) -> list[dict[str, Any]]:
        """Return hourly aggregated statistics across all cameras."""
        query = """
            SELECT
                dt.hour,
                SUM(f.vehicle_count)    AS total_vehicles,
                AVG(f.avg_speed)        AS avg_speed,
                AVG(f.congestion_level) AS avg_congestion
            FROM fact_traffic_events f
            JOIN dim_time dt ON f.time_id = dt.time_id
            GROUP BY dt.hour
            ORDER BY dt.hour;
        """
        return self._db.execute(query)

    def aggregate_daily_stats(self) -> list[dict[str, Any]]:
        """Return daily aggregated statistics across all cameras."""
        query = """
            SELECT
                dt.year,
                dt.month,
                dt.day,
                SUM(f.vehicle_count)    AS total_vehicles,
                AVG(f.avg_speed)        AS avg_speed,
                AVG(f.congestion_level) AS avg_congestion
            FROM fact_traffic_events f
            JOIN dim_time dt ON f.time_id = dt.time_id
            GROUP BY dt.year, dt.month, dt.day
            ORDER BY dt.year, dt.month, dt.day;
        """
        return self._db.execute(query)

    def aggregate_by_vehicle_type(self) -> list[dict[str, Any]]:
        """Return aggregated statistics grouped by vehicle type."""
        query = """
            SELECT
                vt.type_name,
                vt.category,
                SUM(f.vehicle_count) AS total_vehicles,
                AVG(f.avg_speed)     AS avg_speed
            FROM fact_traffic_events f
            JOIN dim_vehicle_type vt ON f.vehicle_type_id = vt.vehicle_type_id
            GROUP BY vt.type_name, vt.category
            ORDER BY total_vehicles DESC;
        """
        return self._db.execute(query)

    def refresh_aggregation_tables(self) -> None:
        """Create or replace summary / materialised-view tables.

        MySQL does not support true materialised views, so we emulate them
        with CREATE TABLE … AS SELECT.
        """
        agg_specs = {
            "agg_hourly_traffic": """
                SELECT
                    dt.hour,
                    dc.camera_id,
                    dc.camera_name,
                    SUM(f.vehicle_count)    AS total_vehicles,
                    AVG(f.avg_speed)        AS avg_speed,
                    AVG(f.congestion_level) AS avg_congestion
                FROM fact_traffic_events f
                JOIN dim_time   dt ON f.time_id   = dt.time_id
                JOIN dim_camera dc ON f.camera_id  = dc.camera_id
                GROUP BY dt.hour, dc.camera_id, dc.camera_name
            """,
            "agg_daily_traffic": """
                SELECT
                    dt.year,
                    dt.month,
                    dt.day,
                    dc.camera_id,
                    dc.camera_name,
                    SUM(f.vehicle_count)    AS total_vehicles,
                    AVG(f.avg_speed)        AS avg_speed,
                    AVG(f.congestion_level) AS avg_congestion
                FROM fact_traffic_events f
                JOIN dim_time   dt ON f.time_id   = dt.time_id
                JOIN dim_camera dc ON f.camera_id  = dc.camera_id
                GROUP BY dt.year, dt.month, dt.day,
                         dc.camera_id, dc.camera_name
            """,
            "agg_vehicle_type_traffic": """
                SELECT
                    vt.type_name,
                    vt.category,
                    dc.camera_id,
                    dc.camera_name,
                    SUM(f.vehicle_count) AS total_vehicles,
                    AVG(f.avg_speed)     AS avg_speed
                FROM fact_traffic_events f
                JOIN dim_vehicle_type vt ON f.vehicle_type_id = vt.vehicle_type_id
                JOIN dim_camera       dc ON f.camera_id       = dc.camera_id
                GROUP BY vt.type_name, vt.category,
                         dc.camera_id, dc.camera_name
            """,
        }
        for table_name, select_sql in agg_specs.items():
            self._db.execute(f"DROP TABLE IF EXISTS {table_name};", fetch=False)
            self._db.execute(
                f"CREATE TABLE {table_name} AS {select_sql};",
                fetch=False,
            )
            logger.info("Refreshed aggregation table: %s", table_name)

        logger.info("All aggregation tables refreshed.")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Release underlying database resources."""
        self._db.close()

    def __del__(self) -> None:
        self.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    mgr = DatamartManager()
    mgr.create_all_tables()
    mgr.populate_all_dimensions()
    print("Datamart initialised successfully.")
