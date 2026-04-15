"""Circuli - Data Mart with star schema for analytics."""

import logging
from datetime import datetime

from .database import DatabaseManager

logger = logging.getLogger("circuli.datamart")


class DataMart:
    """Star schema data mart for Circuli traffic and parking analytics."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    # ------------------------------------------------------------------
    # Schema creation
    # ------------------------------------------------------------------

    def create_tables(self) -> None:
        """Create all star-schema tables if they do not exist."""
        self._create_dim_location()
        self._create_dim_time()
        self._create_dim_vehicle()
        self._create_fact_detections()
        logger.info("Circuli data mart tables created")

    def _create_dim_location(self) -> None:
        self.db.execute_query(
            """
            CREATE TABLE IF NOT EXISTS dim_location (
                location_id   INT AUTO_INCREMENT PRIMARY KEY,
                stream_id     VARCHAR(255) NOT NULL,
                stream_name   VARCHAR(255),
                latitude      DECIMAL(10, 7),
                longitude     DECIMAL(10, 7),
                city          VARCHAR(255),
                region        VARCHAR(255),
                country       VARCHAR(100),
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_stream (stream_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            fetch=False,
        )

    def _create_dim_time(self) -> None:
        self.db.execute_query(
            """
            CREATE TABLE IF NOT EXISTS dim_time (
                time_id       INT AUTO_INCREMENT PRIMARY KEY,
                full_datetime DATETIME NOT NULL,
                date          DATE NOT NULL,
                year          SMALLINT NOT NULL,
                month         TINYINT NOT NULL,
                day           TINYINT NOT NULL,
                hour          TINYINT NOT NULL,
                minute        TINYINT NOT NULL,
                day_of_week   TINYINT NOT NULL,
                is_weekend    BOOLEAN NOT NULL,
                UNIQUE KEY uk_datetime (full_datetime)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            fetch=False,
        )

    def _create_dim_vehicle(self) -> None:
        self.db.execute_query(
            """
            CREATE TABLE IF NOT EXISTS dim_vehicle (
                vehicle_id    INT AUTO_INCREMENT PRIMARY KEY,
                vehicle_type  VARCHAR(100) NOT NULL,
                category      VARCHAR(100),
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_type (vehicle_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            fetch=False,
        )

    def _create_fact_detections(self) -> None:
        self.db.execute_query(
            """
            CREATE TABLE IF NOT EXISTS fact_detections (
                detection_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
                location_id   INT NOT NULL,
                time_id       INT NOT NULL,
                vehicle_id    INT NOT NULL,
                confidence    DECIMAL(5, 4),
                count         INT DEFAULT 1,
                speed_kmh     DECIMAL(6, 2),
                is_parked     BOOLEAN DEFAULT FALSE,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (location_id) REFERENCES dim_location(location_id),
                FOREIGN KEY (time_id) REFERENCES dim_time(time_id),
                FOREIGN KEY (vehicle_id) REFERENCES dim_vehicle(vehicle_id),
                INDEX idx_location (location_id),
                INDEX idx_time (time_id),
                INDEX idx_vehicle (vehicle_id),
                INDEX idx_parked (is_parked)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            fetch=False,
        )

    # ------------------------------------------------------------------
    # Dimension population
    # ------------------------------------------------------------------

    def populate_time_dimension(self, dt: datetime) -> int:
        """Insert a time record if it does not already exist. Returns time_id."""
        existing = self.db.execute_query(
            "SELECT time_id FROM dim_time WHERE full_datetime = %s",
            (dt.replace(second=0, microsecond=0),),
        )
        if existing:
            return existing[0]["time_id"]

        self.db.execute_query(
            """
            INSERT INTO dim_time (full_datetime, date, year, month, day, hour, minute, day_of_week, is_weekend)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                dt.replace(second=0, microsecond=0),
                dt.date(),
                dt.year,
                dt.month,
                dt.day,
                dt.hour,
                dt.minute,
                dt.weekday(),
                dt.weekday() >= 5,
            ),
            fetch=False,
        )
        row = self.db.execute_query("SELECT LAST_INSERT_ID() AS id")
        return row[0]["id"]

    def populate_location_dimension(
        self,
        stream_id: str,
        stream_name: str = "",
        latitude: float = 0.0,
        longitude: float = 0.0,
        city: str = "",
        region: str = "",
        country: str = "",
    ) -> int:
        """Insert a location record if it does not exist. Returns location_id."""
        existing = self.db.execute_query(
            "SELECT location_id FROM dim_location WHERE stream_id = %s",
            (stream_id,),
        )
        if existing:
            return existing[0]["location_id"]

        self.db.execute_query(
            """
            INSERT INTO dim_location (stream_id, stream_name, latitude, longitude, city, region, country)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (stream_id, stream_name, latitude, longitude, city, region, country),
            fetch=False,
        )
        row = self.db.execute_query("SELECT LAST_INSERT_ID() AS id")
        return row[0]["id"]

    def populate_vehicle_dimension(self, vehicle_type: str, category: str = "") -> int:
        """Insert a vehicle type if it does not exist. Returns vehicle_id."""
        existing = self.db.execute_query(
            "SELECT vehicle_id FROM dim_vehicle WHERE vehicle_type = %s",
            (vehicle_type,),
        )
        if existing:
            return existing[0]["vehicle_id"]

        self.db.execute_query(
            "INSERT INTO dim_vehicle (vehicle_type, category) VALUES (%s, %s)",
            (vehicle_type, category),
            fetch=False,
        )
        row = self.db.execute_query("SELECT LAST_INSERT_ID() AS id")
        return row[0]["id"]

    # ------------------------------------------------------------------
    # Aggregation queries for dashboards
    # ------------------------------------------------------------------

    def get_traffic_volume_by_hour(self, days: int = 7) -> list[dict]:
        """Aggregate traffic volume grouped by hour for the last N days."""
        return self.db.execute_query(
            """
            SELECT dt.hour, SUM(f.count) AS total_vehicles
            FROM fact_detections f
            JOIN dim_time dt ON f.time_id = dt.time_id
            WHERE dt.date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY dt.hour
            ORDER BY dt.hour
            """,
            (days,),
        )

    def get_vehicle_type_distribution(self, days: int = 7) -> list[dict]:
        """Vehicle type distribution for the last N days."""
        return self.db.execute_query(
            """
            SELECT dv.vehicle_type, dv.category, SUM(f.count) AS total
            FROM fact_detections f
            JOIN dim_vehicle dv ON f.vehicle_id = dv.vehicle_id
            JOIN dim_time dt ON f.time_id = dt.time_id
            WHERE dt.date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY dv.vehicle_type, dv.category
            ORDER BY total DESC
            """,
            (days,),
        )

    def get_parking_occupancy(self) -> list[dict]:
        """Current parking occupancy by location."""
        return self.db.execute_query(
            """
            SELECT dl.stream_name AS location, dl.city,
                   SUM(CASE WHEN f.is_parked = TRUE THEN f.count ELSE 0 END) AS parked,
                   SUM(f.count) AS total
            FROM fact_detections f
            JOIN dim_location dl ON f.location_id = dl.location_id
            JOIN dim_time dt ON f.time_id = dt.time_id
            WHERE dt.date = CURDATE()
            GROUP BY dl.stream_name, dl.city
            """
        )

    def get_daily_summary(self, days: int = 30) -> list[dict]:
        """Daily detection summary for the last N days."""
        return self.db.execute_query(
            """
            SELECT dt.date, SUM(f.count) AS total_vehicles,
                   COUNT(DISTINCT f.location_id) AS active_streams,
                   SUM(CASE WHEN f.is_parked THEN f.count ELSE 0 END) AS parked_vehicles
            FROM fact_detections f
            JOIN dim_time dt ON f.time_id = dt.time_id
            WHERE dt.date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY dt.date
            ORDER BY dt.date
            """,
            (days,),
        )
