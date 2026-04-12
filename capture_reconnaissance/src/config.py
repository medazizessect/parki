"""Configuration management for the capture reconnaissance module.

Loads settings from environment variables and .env files, providing
typed access to MySQL, camera, YOLO, and Airflow configuration.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from project root
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


def _get_env(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """Retrieve an environment variable with optional default and requirement check."""
    value = os.getenv(key, default)
    if required and value is None:
        raise EnvironmentError(f"Required environment variable '{key}' is not set.")
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class MySQLConfig:
    """MySQL connection settings."""

    host: str = "localhost"
    port: int = 3306
    user: str = "parki"
    password: str = "parki_secret"
    database: str = "parki_capture"
    pool_size: int = 5

    @classmethod
    def from_env(cls) -> "MySQLConfig":
        return cls(
            host=_get_env("MYSQL_HOST", "localhost"),
            port=int(_get_env("MYSQL_PORT", "3306")),
            user=_get_env("MYSQL_USER", "parki"),
            password=_get_env("MYSQL_PASSWORD", "parki_secret"),
            database=_get_env("MYSQL_DATABASE", "parki_capture"),
            pool_size=int(_get_env("MYSQL_POOL_SIZE", "5")),
        )


@dataclass(frozen=True)
class CameraConfig:
    """Camera / RTSP stream settings."""

    rtsp_urls: List[str] = field(default_factory=list)
    resolution_width: int = 1280
    resolution_height: int = 720
    fps: int = 15

    @classmethod
    def from_env(cls) -> "CameraConfig":
        raw_urls = _get_env("CAMERA_RTSP_URLS", "")
        urls = [u.strip() for u in raw_urls.split(",") if u.strip()]
        return cls(
            rtsp_urls=urls,
            resolution_width=int(_get_env("CAMERA_RESOLUTION_WIDTH", "1280")),
            resolution_height=int(_get_env("CAMERA_RESOLUTION_HEIGHT", "720")),
            fps=int(_get_env("CAMERA_FPS", "15")),
        )


@dataclass(frozen=True)
class YOLOConfig:
    """YOLOv8 model settings."""

    model_path: str = "yolov8s.pt"
    confidence_threshold: float = 0.4
    device: str = "cpu"

    @classmethod
    def from_env(cls) -> "YOLOConfig":
        return cls(
            model_path=_get_env("YOLO_MODEL_PATH", "yolov8s.pt"),
            confidence_threshold=float(
                _get_env("YOLO_CONFIDENCE_THRESHOLD", "0.4")
            ),
            device=_get_env("YOLO_DEVICE", "cpu"),
        )


@dataclass(frozen=True)
class AirflowConfig:
    """Airflow-related settings."""

    dag_schedule_capture: str = "*/5 * * * *"
    dag_schedule_etl: str = "0 * * * *"
    data_retention_days: int = 30

    @classmethod
    def from_env(cls) -> "AirflowConfig":
        return cls(
            dag_schedule_capture=_get_env(
                "AIRFLOW_DAG_SCHEDULE_CAPTURE", "*/5 * * * *"
            ),
            dag_schedule_etl=_get_env("AIRFLOW_DAG_SCHEDULE_ETL", "0 * * * *"),
            data_retention_days=int(
                _get_env("AIRFLOW_DATA_RETENTION_DAYS", "30")
            ),
        )


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration aggregating all sub-configs."""

    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    yolo: YOLOConfig = field(default_factory=YOLOConfig)
    airflow: AirflowConfig = field(default_factory=AirflowConfig)
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Build the full configuration from environment variables."""
        cfg = cls(
            mysql=MySQLConfig.from_env(),
            camera=CameraConfig.from_env(),
            yolo=YOLOConfig.from_env(),
            airflow=AirflowConfig.from_env(),
            log_level=_get_env("LOG_LEVEL", "INFO"),
        )
        logger.info("Configuration loaded successfully.")
        return cfg


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


if __name__ == "__main__":
    setup_logging()
    config = AppConfig.from_env()
    logger.info("MySQL host: %s", config.mysql.host)
    logger.info("Camera URLs: %s", config.camera.rtsp_urls)
    logger.info("YOLO model: %s", config.yolo.model_path)
