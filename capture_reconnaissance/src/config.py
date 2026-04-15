"""Circuli - Configuration module for Capture & Reconnaissance."""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yt_dlp

APP_NAME = "Circuli"

logger = logging.getLogger(APP_NAME)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
YOUTUBE_STREAMS_PATH = CONFIG_DIR / "youtube_streams.json"


@dataclass
class CirculiConfig:
    """Central configuration for the Circuli capture pipeline."""

    app_name: str = APP_NAME
    rtsp_urls: list[str] = field(default_factory=list)
    yolo_model_path: str = "yolov8s.pt"
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "circuli"
    db_password: str = "circuli"
    db_name: str = "circuli"
    max_retries: int = 3
    retry_delay_seconds: int = 5
    extraction_format: str = "best[height<=720]"
    auto_start: bool = True

    @classmethod
    def from_env(
        cls,
        db_host: Optional[str] = None,
        db_port: Optional[int] = None,
        db_user: Optional[str] = None,
        db_password: Optional[str] = None,
        db_name: Optional[str] = None,
    ) -> "CirculiConfig":
        """Create config with optional overrides."""
        config = cls()
        if db_host:
            config.db_host = db_host
        if db_port:
            config.db_port = db_port
        if db_user:
            config.db_user = db_user
        if db_password:
            config.db_password = db_password
        if db_name:
            config.db_name = db_name
        return config


def load_youtube_streams(path: Optional[Path] = None) -> dict:
    """Load YouTube stream configuration from JSON file."""
    config_path = path or YOUTUBE_STREAMS_PATH
    logger.info("[%s] Loading YouTube streams from %s", APP_NAME, config_path)

    if not config_path.exists():
        logger.error("[%s] Config file not found: %s", APP_NAME, config_path)
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    enabled = [s for s in data.get("streams", []) if s.get("enabled", False)]
    logger.info("[%s] Loaded %d enabled streams", APP_NAME, len(enabled))
    return data


def get_stream_url(youtube_url: str, config: Optional[CirculiConfig] = None) -> str:
    """Extract a direct stream URL from a YouTube link using yt-dlp.

    Retries up to max_retries on failure.
    """
    cfg = config or CirculiConfig()
    max_retries = cfg.max_retries
    retry_delay = cfg.retry_delay_seconds

    ydl_opts = {
        "format": cfg.extraction_format,
        "quiet": True,
        "no_warnings": True,
    }

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "[%s] Extracting stream URL (attempt %d/%d): %s",
                APP_NAME,
                attempt,
                max_retries,
                youtube_url,
            )
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                stream_url = info.get("url", "")
                if stream_url:
                    logger.info("[%s] Successfully extracted stream URL", APP_NAME)
                    return stream_url
                raise ValueError("Empty stream URL returned")
        except Exception as exc:
            logger.warning(
                "[%s] Attempt %d failed: %s", APP_NAME, attempt, exc
            )
            if attempt < max_retries:
                time.sleep(retry_delay)

    raise RuntimeError(
        f"[{APP_NAME}] Failed to extract stream URL after {max_retries} attempts: {youtube_url}"
    )
