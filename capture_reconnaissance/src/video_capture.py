"""Circuli - Video capture module for RTSP and YouTube streams."""

import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np

from .config import (
    APP_NAME,
    CirculiConfig,
    get_stream_url,
    load_youtube_streams,
)

logger = logging.getLogger(APP_NAME)


class VideoCapture:
    """Capture video frames from RTSP or YouTube streams."""

    def __init__(self, config: Optional[CirculiConfig] = None) -> None:
        self.config = config or CirculiConfig()
        self.captures: dict[int, cv2.VideoCapture] = {}
        self.threads: dict[int, threading.Thread] = {}
        self._running: dict[int, bool] = {}
        self._latest_frames: dict[int, Optional[np.ndarray]] = {}
        self._lock = threading.Lock()

    def _resolve_stream_url(self, url: str) -> str:
        """Resolve a YouTube URL to a direct stream URL, or return as-is for RTSP."""
        if "youtube.com" in url or "youtu.be" in url:
            return get_stream_url(url, self.config)
        return url

    def load_streams(self) -> list[dict]:
        """Load enabled streams from youtube_streams.json."""
        data = load_youtube_streams()
        streams = [s for s in data.get("streams", []) if s.get("enabled", False)]
        logger.info("[%s] Loaded %d enabled streams", APP_NAME, len(streams))
        return streams

    def start(self, stream_id: int, url: str) -> None:
        """Start capturing frames from a single stream."""
        if stream_id in self._running and self._running[stream_id]:
            logger.warning(
                "[%s] Stream %d is already running", APP_NAME, stream_id
            )
            return

        resolved_url = self._resolve_stream_url(url)
        logger.info(
            "[%s] Starting capture for stream %d", APP_NAME, stream_id
        )

        cap = cv2.VideoCapture(resolved_url)
        if not cap.isOpened():
            logger.error(
                "[%s] Failed to open stream %d: %s",
                APP_NAME,
                stream_id,
                url,
            )
            raise RuntimeError(f"Cannot open stream {stream_id}")

        self.captures[stream_id] = cap
        self._running[stream_id] = True
        self._latest_frames[stream_id] = None

        thread = threading.Thread(
            target=self._capture_loop,
            args=(stream_id,),
            daemon=True,
        )
        self.threads[stream_id] = thread
        thread.start()
        logger.info("[%s] Stream %d capture started", APP_NAME, stream_id)

    def start_all(self) -> None:
        """Start all enabled streams from configuration."""
        streams = self.load_streams()
        for stream in streams:
            try:
                self.start(stream["id"], stream["url"])
            except RuntimeError:
                logger.error(
                    "[%s] Skipping stream %d due to error",
                    APP_NAME,
                    stream["id"],
                )

    def stop(self, stream_id: int) -> None:
        """Stop capturing frames from a single stream."""
        self._running[stream_id] = False
        if stream_id in self.threads:
            self.threads[stream_id].join(timeout=5)
        if stream_id in self.captures:
            self.captures[stream_id].release()
        logger.info("[%s] Stream %d capture stopped", APP_NAME, stream_id)

    def stop_all(self) -> None:
        """Stop all active streams."""
        for stream_id in list(self._running.keys()):
            self.stop(stream_id)

    def get_frame(self, stream_id: int) -> Optional[np.ndarray]:
        """Return the latest captured frame for a stream."""
        with self._lock:
            return self._latest_frames.get(stream_id)

    def _capture_loop(self, stream_id: int) -> None:
        """Continuously read frames from a stream."""
        cap = self.captures[stream_id]
        while self._running.get(stream_id, False):
            ret, frame = cap.read()
            if not ret:
                logger.warning(
                    "[%s] Stream %d: frame read failed, retrying...",
                    APP_NAME,
                    stream_id,
                )
                time.sleep(1)
                continue
            with self._lock:
                self._latest_frames[stream_id] = frame
        logger.info("[%s] Capture loop ended for stream %d", APP_NAME, stream_id)
