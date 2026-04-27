"""
MySQL Datamart Connection and Query Layer.

Provides pooled connections and pre-built analytical queries for the
BI datamart star-schema.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Generator, Optional

import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector.pooling import MySQLConnectionPool

from .config import MySQLConfig, get_settings

logger = logging.getLogger(__name__)


class DatamartConnection:
    """Manages a MySQL connection pool and exposes analytical query helpers."""

    def __init__(self, config: Optional[MySQLConfig] = None) -> None:
        self._config = config or get_settings().mysql
        self._pool: Optional[MySQLConnectionPool] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def _ensure_pool(self) -> MySQLConnectionPool:
        if self._pool is None:
            try:
                self._pool = MySQLConnectionPool(**self._config.to_pool_kwargs())
                logger.info(
                    "MySQL connection pool '%s' created (size=%d).",
                    self._config.pool_name,
                    self._config.pool_size,
                )
            except MySQLError as exc:
                logger.error("Failed to create MySQL pool: %s", exc)
                raise
        return self._pool

    @contextmanager
    def connection(self) -> Generator[mysql.connector.MySQLConnection, None, None]:
        """Yield a connection from the pool; returns it on exit."""
        pool = self._ensure_pool()
        conn = pool.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def cursor(self, dictionary: bool = True):
        """Yield a cursor from a pooled connection."""
        with self.connection() as conn:
            cur = conn.cursor(dictionary=dictionary)
            try:
                yield cur
                conn.commit()
            except MySQLError:
                conn.rollback()
                raise
            finally:
                cur.close()

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------
    def execute(
        self,
        query: str,
        params: Optional[tuple] = None,
        *,
        fetch: bool = True,
    ) -> list[dict[str, Any]]:
        """Execute *query* with optional *params* and return rows as dicts."""
        with self.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                return cur.fetchall()
            return []

    def execute_many(self, query: str, data: list[tuple]) -> int:
        """Execute *query* for every tuple in *data*. Return rowcount."""
        with self.cursor() as cur:
            cur.executemany(query, data)
            return cur.rowcount

    # ------------------------------------------------------------------
    # Analytical queries
    # ------------------------------------------------------------------
    def get_hourly_traffic(
        self,
        camera_id: int,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Return hourly aggregated vehicle counts for a camera."""
        query = """
            SELECT
                dt.hour,
                dt.day,
                dt.month,
                dt.year,
                SUM(f.vehicle_count) AS total_vehicles,
                AVG(f.avg_speed)     AS avg_speed
            FROM fact_traffic_events f
            JOIN dim_time   dt ON f.time_id = dt.time_id
            WHERE f.camera_id = %s
              AND CONCAT(dt.year, '-', LPAD(dt.month, 2, '0'), '-', LPAD(dt.day, 2, '0'))
                  BETWEEN %s AND %s
            GROUP BY dt.year, dt.month, dt.day, dt.hour
            ORDER BY dt.year, dt.month, dt.day, dt.hour;
        """
        return self.execute(query, (camera_id, str(start_date), str(end_date)))

    def get_vehicle_type_distribution(
        self,
        camera_id: int,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Return vehicle-type breakdown for a camera in a date range."""
        query = """
            SELECT
                vt.type_name,
                vt.category,
                SUM(f.vehicle_count) AS total_vehicles,
                AVG(f.avg_speed)     AS avg_speed
            FROM fact_traffic_events f
            JOIN dim_vehicle_type vt ON f.vehicle_type_id = vt.vehicle_type_id
            JOIN dim_time         dt ON f.time_id        = dt.time_id
            WHERE f.camera_id = %s
              AND CONCAT(dt.year, '-', LPAD(dt.month, 2, '0'), '-', LPAD(dt.day, 2, '0'))
                  BETWEEN %s AND %s
            GROUP BY vt.type_name, vt.category
            ORDER BY total_vehicles DESC;
        """
        return self.execute(query, (camera_id, str(start_date), str(end_date)))

    def get_speed_statistics(
        self,
        camera_id: int,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Return speed statistics for a camera in a date range."""
        query = """
            SELECT
                AVG(f.avg_speed) AS overall_avg_speed,
                MAX(f.max_speed) AS overall_max_speed,
                MIN(f.min_speed) AS overall_min_speed,
                AVG(f.congestion_level) AS avg_congestion
            FROM fact_traffic_events f
            JOIN dim_time dt ON f.time_id = dt.time_id
            WHERE f.camera_id = %s
              AND CONCAT(dt.year, '-', LPAD(dt.month, 2, '0'), '-', LPAD(dt.day, 2, '0'))
                  BETWEEN %s AND %s;
        """
        return self.execute(query, (camera_id, str(start_date), str(end_date)))

    def get_peak_hours(self, camera_id: int) -> list[dict[str, Any]]:
        """Return top-5 peak hours by vehicle count for a camera."""
        query = """
            SELECT
                dt.hour,
                SUM(f.vehicle_count) AS total_vehicles,
                AVG(f.avg_speed)     AS avg_speed,
                AVG(f.congestion_level) AS avg_congestion
            FROM fact_traffic_events f
            JOIN dim_time dt ON f.time_id = dt.time_id
            WHERE f.camera_id = %s
            GROUP BY dt.hour
            ORDER BY total_vehicles DESC
            LIMIT 5;
        """
        return self.execute(query, (camera_id,))

    def get_camera_comparison(self) -> list[dict[str, Any]]:
        """Compare all cameras by total traffic, speed, and congestion."""
        query = """
            SELECT
                dc.camera_id,
                dc.camera_name,
                dc.status,
                dl.zone_name,
                dl.road_name,
                dl.latitude,
                dl.longitude,
                SUM(f.vehicle_count)    AS total_vehicles,
                AVG(f.avg_speed)        AS avg_speed,
                AVG(f.congestion_level) AS avg_congestion
            FROM fact_traffic_events f
            JOIN dim_camera   dc ON f.camera_id   = dc.camera_id
            JOIN dim_location dl ON f.location_id  = dl.location_id
            GROUP BY dc.camera_id, dc.camera_name, dc.status,
                     dl.zone_name, dl.road_name, dl.latitude, dl.longitude
            ORDER BY total_vehicles DESC;
        """
        return self.execute(query)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    def health_check(self) -> dict[str, Any]:
        """Return datamart health information."""
        try:
            rows = self.execute("SELECT 1 AS ok")
            return {
                "status": "healthy",
                "database": self._config.database,
                "host": self._config.host,
                "pool_name": self._config.pool_name,
                "timestamp": datetime.utcnow().isoformat(),
            }
        except MySQLError as exc:
            logger.error("Health check failed: %s", exc)
            return {
                "status": "unhealthy",
                "error": str(exc),
                "timestamp": datetime.utcnow().isoformat(),
            }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Release the connection pool (best-effort)."""
        self._pool = None
        logger.info("DatamartConnection pool reference released.")

    def __del__(self) -> None:
        self.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    db = DatamartConnection()
    print(db.health_check())
