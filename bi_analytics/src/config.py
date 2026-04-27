"""
BI Analytics Configuration Management.

Loads configuration from environment variables and .env file
for database, Grafana, API, and map settings.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env from the bi_analytics root directory
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(key: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


@dataclass(frozen=True)
class MySQLConfig:
    """MySQL datamart connection settings."""

    host: str = field(default_factory=lambda: _env("BI_MYSQL_HOST", "localhost"))
    port: int = field(default_factory=lambda: _env_int("BI_MYSQL_PORT", 3306))
    user: str = field(default_factory=lambda: _env("BI_MYSQL_USER", "parki"))
    password: str = field(default_factory=lambda: _env("BI_MYSQL_PASSWORD", "parki_secret"))
    database: str = field(default_factory=lambda: _env("BI_MYSQL_DATABASE", "parki_datamart"))
    pool_name: str = field(default_factory=lambda: _env("BI_MYSQL_POOL_NAME", "parki_pool"))
    pool_size: int = field(default_factory=lambda: _env_int("BI_MYSQL_POOL_SIZE", 5))
    charset: str = "utf8mb4"
    collation: str = "utf8mb4_unicode_ci"

    def to_pool_kwargs(self) -> dict:
        """Return kwargs suitable for mysql.connector pooling."""
        return {
            "pool_name": self.pool_name,
            "pool_size": self.pool_size,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "charset": self.charset,
            "collation": self.collation,
        }


@dataclass(frozen=True)
class GrafanaConfig:
    """Grafana connection settings."""

    host: str = field(default_factory=lambda: _env("BI_GRAFANA_HOST", "localhost"))
    port: int = field(default_factory=lambda: _env_int("BI_GRAFANA_PORT", 3000))
    admin_user: str = field(default_factory=lambda: _env("BI_GRAFANA_ADMIN_USER", "admin"))
    admin_password: str = field(default_factory=lambda: _env("BI_GRAFANA_ADMIN_PASSWORD", "admin"))

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass(frozen=True)
class APIConfig:
    """FastAPI server settings."""

    host: str = field(default_factory=lambda: _env("BI_API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("BI_API_PORT", 8000))
    debug: bool = field(
        default_factory=lambda: _env("BI_API_DEBUG", "false").lower() == "true"
    )
    cors_origins: list[str] = field(
        default_factory=lambda: _env("BI_API_CORS_ORIGINS", "*").split(",")
    )


@dataclass(frozen=True)
class MapConfig:
    """Folium map default settings."""

    center_lat: float = field(
        default_factory=lambda: _env_float("BI_MAP_CENTER_LAT", -23.5505)
    )
    center_lng: float = field(
        default_factory=lambda: _env_float("BI_MAP_CENTER_LNG", -46.6333)
    )
    zoom_level: int = field(
        default_factory=lambda: _env_int("BI_MAP_ZOOM", 12)
    )
    tile_provider: str = field(
        default_factory=lambda: _env("BI_MAP_TILE_PROVIDER", "OpenStreetMap")
    )
    output_dir: str = field(
        default_factory=lambda: _env(
            "BI_MAP_OUTPUT_DIR",
            str(Path(__file__).resolve().parent.parent / "maps"),
        )
    )


@dataclass(frozen=True)
class Settings:
    """Root settings container aggregating all sub-configurations."""

    mysql: MySQLConfig = field(default_factory=MySQLConfig)
    grafana: GrafanaConfig = field(default_factory=GrafanaConfig)
    api: APIConfig = field(default_factory=APIConfig)
    map: MapConfig = field(default_factory=MapConfig)


# Module-level singleton
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the cached application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
        logger.info("BI Analytics settings loaded successfully.")
    return _settings


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    s = get_settings()
    print(f"MySQL : {s.mysql.host}:{s.mysql.port}/{s.mysql.database}")
    print(f"Grafana: {s.grafana.base_url}")
    print(f"API    : {s.api.host}:{s.api.port}")
    print(f"Map    : ({s.map.center_lat}, {s.map.center_lng}) zoom={s.map.zoom_level}")
