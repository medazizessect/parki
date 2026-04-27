"""MySQL data storage for traffic events.

Provides connection pooling, batch inserts, auto-reconnect on
connection loss, and automatic table creation.
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Generator, List, Optional

import mysql.connector
from mysql.connector import pooling

from .vehicle_tracker import TrafficEvent

logger = logging.getLogger(__name__)

_CREATE_TRAFFIC_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS traffic_events (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    camera_id       VARCHAR(64)   NOT NULL,
    event_timestamp DATETIME(3)   NOT NULL,
    vehicle_type    VARCHAR(32)   NOT NULL,
    confidence      FLOAT         NOT NULL,
    speed_estimate  FLOAT         DEFAULT 0,
    direction       VARCHAR(16)   DEFAULT 'unknown',
    bbox_x          FLOAT         DEFAULT 0,
    bbox_y          FLOAT         DEFAULT 0,
    bbox_w          FLOAT         DEFAULT 0,
    bbox_h          FLOAT         DEFAULT 0,
    frame_number    INT           DEFAULT 0,
    created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_camera_id (camera_id),
    INDEX idx_event_timestamp (event_timestamp),
    INDEX idx_vehicle_type (vehicle_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


class DatabaseHandler:
    """MySQL handler with connection pooling and auto-reconnect.

    Parameters
    ----------
    host, port, user, password, database:
        Standard MySQL connection parameters.
    pool_size:
        Number of connections to keep in the pool.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "parki",
        password: str = "parki_secret",
        database: str = "parki_capture",
        pool_size: int = 5,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.pool_size = pool_size
        self._pool: Optional[pooling.MySQLConnectionPool] = None
        self._init_pool()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _init_pool(self) -> None:
        """Create the connection pool and ensure tables exist."""
        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name="parki_pool",
                pool_size=self.pool_size,
                pool_reset_session=True,
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            )
            self._ensure_tables()
            logger.info(
                "Database pool initialised (%s@%s:%s/%s, pool_size=%d)",
                self.user,
                self.host,
                self.port,
                self.database,
                self.pool_size,
            )
        except mysql.connector.Error:
            logger.exception("Failed to initialise database connection pool.")
            self._pool = None

    @contextmanager
    def _get_connection(self) -> Generator:
        """Yield a connection from the pool, handling reconnect."""
        if self._pool is None:
            self._init_pool()
        if self._pool is None:
            raise ConnectionError("Database pool is not available.")
        conn = self._pool.get_connection()
        try:
            yield conn
            conn.commit()
        except mysql.connector.Error:
            conn.rollback()
            raise
        finally:
            conn.close()

    def health_check(self) -> bool:
        """Return ``True`` if the database is reachable."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
            return True
        except Exception:
            logger.exception("Database health check failed.")
            return False

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def _ensure_tables(self) -> None:
        """Create required tables if they do not exist."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(_CREATE_TRAFFIC_EVENTS_TABLE)
                cursor.close()
            logger.info("Database tables verified / created.")
        except Exception:
            logger.exception("Could not ensure database tables.")

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    _INSERT_SQL = (
        "INSERT INTO traffic_events "
        "(camera_id, event_timestamp, vehicle_type, confidence, "
        "speed_estimate, direction, bbox_x, bbox_y, bbox_w, bbox_h, "
        "frame_number) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )

    @staticmethod
    def _event_to_row(event: TrafficEvent) -> tuple:
        x1, y1, x2, y2 = event.bbox
        return (
            event.camera_id,
            datetime.fromtimestamp(event.timestamp),
            event.vehicle_type,
            event.confidence,
            event.speed_estimate,
            event.direction,
            x1,
            y1,
            x2 - x1,
            y2 - y1,
            event.frame_number,
        )

    def insert_event(self, event: TrafficEvent) -> None:
        """Insert a single traffic event into the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(self._INSERT_SQL, self._event_to_row(event))
                cursor.close()
        except Exception:
            logger.exception("Failed to insert event.")

    def insert_batch(self, events: List[TrafficEvent]) -> None:
        """Insert multiple traffic events in a single transaction."""
        if not events:
            return
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                rows = [self._event_to_row(e) for e in events]
                cursor.executemany(self._INSERT_SQL, rows)
                cursor.close()
            logger.info("Inserted batch of %d events.", len(events))
        except Exception:
            logger.exception("Failed to insert event batch.")

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_events(
        self,
        camera_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[dict]:
        """Query traffic events for a camera within a time range."""
        sql = (
            "SELECT id, camera_id, event_timestamp, vehicle_type, "
            "confidence, speed_estimate, direction, bbox_x, bbox_y, "
            "bbox_w, bbox_h, frame_number, created_at "
            "FROM traffic_events "
            "WHERE camera_id = %s AND event_timestamp BETWEEN %s AND %s "
            "ORDER BY event_timestamp"
        )
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(sql, (camera_id, start_time, end_time))
                rows = cursor.fetchall()
                cursor.close()
            return rows
        except Exception:
            logger.exception("Failed to query events.")
            return []

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup_old_data(self, retention_days: int = 30) -> int:
        """Delete events older than *retention_days*. Returns count deleted."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        sql = "DELETE FROM traffic_events WHERE created_at < %s"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, (cutoff,))
                deleted = cursor.rowcount
                cursor.close()
            logger.info("Cleaned up %d old events (before %s).", deleted, cutoff)
            return deleted
        except Exception:
            logger.exception("Failed to clean up old data.")
            return 0

    def close(self) -> None:
        """Release the connection pool (best-effort)."""
        self._pool = None
        logger.info("Database handler closed.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    handler = DatabaseHandler()
    logger.info("Health check: %s", handler.health_check())
