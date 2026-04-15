"""Circuli - Data handler for saving detection results."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import mysql.connector

APP_NAME = "Circuli"
logger = logging.getLogger(APP_NAME)


class DataHandler:
    """Save vehicle detection results to MySQL or local files."""

    def __init__(
        self,
        db_host: str = "localhost",
        db_port: int = 3306,
        db_user: str = "circuli",
        db_password: str = "circuli",
        db_name: str = "circuli",
        output_dir: Optional[str] = None,
    ) -> None:
        self.db_config = {
            "host": db_host,
            "port": db_port,
            "user": db_user,
            "password": db_password,
            "database": db_name,
        }
        self.output_dir = Path(output_dir) if output_dir else Path("output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[mysql.connector.MySQLConnection] = None

    def _get_connection(self) -> mysql.connector.MySQLConnection:
        """Get or create a MySQL connection."""
        if self._connection is None or not self._connection.is_connected():
            try:
                self._connection = mysql.connector.connect(**self.db_config)
                logger.info("[%s] Connected to MySQL database", APP_NAME)
                self._ensure_table()
            except mysql.connector.Error as err:
                logger.error("[%s] MySQL connection failed: %s", APP_NAME, err)
                raise
        return self._connection

    def _ensure_table(self) -> None:
        """Create the detections table if it does not exist."""
        create_sql = """
        CREATE TABLE IF NOT EXISTS vehicle_detections (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            stream_id INT NOT NULL,
            vehicle_class VARCHAR(50) NOT NULL,
            confidence FLOAT NOT NULL,
            bbox_x1 FLOAT NOT NULL,
            bbox_y1 FLOAT NOT NULL,
            bbox_x2 FLOAT NOT NULL,
            bbox_y2 FLOAT NOT NULL,
            location VARCHAR(255),
            detected_at DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
        assert self._connection is not None, "Connection must be established before ensuring table"
        conn = self._connection
        cursor = conn.cursor()
        try:
            cursor.execute(create_sql)
            conn.commit()
        finally:
            cursor.close()

    def save_detection(
        self,
        stream_id: int,
        vehicle_class: str,
        confidence: float,
        bbox: tuple[float, float, float, float],
        location: str = "",
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Save a single detection result to MySQL."""
        ts = timestamp or datetime.now(timezone.utc)
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            insert_sql = """
            INSERT INTO vehicle_detections
                (stream_id, vehicle_class, confidence, bbox_x1, bbox_y1, bbox_x2, bbox_y2, location, detected_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                insert_sql,
                (stream_id, vehicle_class, confidence, *bbox, location, ts),
            )
            conn.commit()
            cursor.close()
            logger.debug(
                "[%s] Saved detection: %s (%.2f) on stream %d",
                APP_NAME,
                vehicle_class,
                confidence,
                stream_id,
            )
        except mysql.connector.Error as err:
            logger.error("[%s] Failed to save detection: %s", APP_NAME, err)
            self._save_to_file(stream_id, vehicle_class, confidence, bbox, location, ts)

    def _save_to_file(
        self,
        stream_id: int,
        vehicle_class: str,
        confidence: float,
        bbox: tuple[float, float, float, float],
        location: str,
        timestamp: datetime,
    ) -> None:
        """Fallback: save detection to a local JSON file."""
        record: dict[str, Any] = {
            "stream_id": stream_id,
            "vehicle_class": vehicle_class,
            "confidence": confidence,
            "bbox": list(bbox),
            "location": location,
            "detected_at": timestamp.isoformat(),
        }
        date_str = timestamp.strftime("%Y%m%d")
        filepath = self.output_dir / f"detections_{date_str}.jsonl"
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            logger.info("[%s] Detection saved to file: %s", APP_NAME, filepath)
        except OSError as err:
            logger.error("[%s] Failed to write to file: %s", APP_NAME, err)

    def save_batch(
        self,
        detections: list[dict[str, Any]],
        stream_id: int,
        location: str = "",
    ) -> None:
        """Save a batch of detections."""
        for det in detections:
            self.save_detection(
                stream_id=stream_id,
                vehicle_class=det.get("class_name", "unknown"),
                confidence=det.get("confidence", 0.0),
                bbox=det.get("bbox", (0, 0, 0, 0)),
                location=location,
                timestamp=det.get("timestamp"),
            )

    def close(self) -> None:
        """Close the database connection."""
        if self._connection and self._connection.is_connected():
            self._connection.close()
            logger.info("[%s] Database connection closed", APP_NAME)
