"""Multi-camera RTSP stream handler.

Provides thread-safe frame reading, automatic reconnection with
exponential backoff, FPS tracking, and health monitoring for
multiple simultaneous camera streams.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Reconnection constants
_INITIAL_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 60.0
_BACKOFF_FACTOR = 2.0


@dataclass
class CameraInfo:
    """Metadata describing a camera stream."""

    camera_id: str
    rtsp_url: str
    resolution: Tuple[int, int] = (0, 0)
    fps: float = 0.0
    connected: bool = False


class CameraStream:
    """Manages a single RTSP / video stream using OpenCV.

    Reads frames in a dedicated background thread and exposes the
    latest frame via a thread-safe ``read()`` method.
    """

    def __init__(
        self,
        camera_id: str,
        rtsp_url: str,
        target_fps: int = 15,
        resolution: Optional[Tuple[int, int]] = None,
    ) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.target_fps = target_fps
        self.resolution = resolution

        self._cap: Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Metrics
        self._fps: float = 0.0
        self._frame_count: int = 0
        self._last_fps_time: float = 0.0
        self._connected = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Open the stream and start the background reader thread."""
        if self._running:
            logger.warning("Camera %s is already running.", self.camera_id)
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._reader_loop, name=f"cam-{self.camera_id}", daemon=True
        )
        self._thread.start()
        logger.info("Camera %s reader thread started.", self.camera_id)

    def stop(self) -> None:
        """Signal the reader thread to stop and release resources."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._release_capture()
        logger.info("Camera %s stopped.", self.camera_id)

    def read(self) -> Optional[np.ndarray]:
        """Return the latest frame (thread-safe), or ``None``."""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def info(self) -> CameraInfo:
        res = self.resolution or (0, 0)
        if self._cap and self._cap.isOpened():
            res = (
                int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )
        return CameraInfo(
            camera_id=self.camera_id,
            rtsp_url=self.rtsp_url,
            resolution=res,
            fps=self._fps,
            connected=self._connected,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open_stream(self) -> bool:
        """Attempt to open the video capture stream."""
        self._release_capture()
        try:
            self._cap = cv2.VideoCapture(self.rtsp_url)
            if self._cap.isOpened():
                if self.resolution:
                    self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
                    self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
                self._connected = True
                logger.info("Camera %s connected to %s", self.camera_id, self.rtsp_url)
                return True
        except Exception:
            logger.exception("Error opening stream for camera %s", self.camera_id)
        self._connected = False
        return False

    def _release_capture(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                logger.exception("Error releasing capture for camera %s", self.camera_id)
            self._cap = None
        self._connected = False

    def _reader_loop(self) -> None:
        """Background loop: connect, read frames, reconnect on failure."""
        backoff = _INITIAL_BACKOFF_S
        self._last_fps_time = time.monotonic()
        self._frame_count = 0

        while self._running:
            if not self._connected or self._cap is None or not self._cap.isOpened():
                if not self._open_stream():
                    logger.warning(
                        "Camera %s reconnecting in %.1fs …",
                        self.camera_id,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * _BACKOFF_FACTOR, _MAX_BACKOFF_S)
                    continue
                backoff = _INITIAL_BACKOFF_S

            ret, frame = self._cap.read()  # type: ignore[union-attr]
            if not ret or frame is None:
                logger.warning("Camera %s lost frame, will reconnect.", self.camera_id)
                self._connected = False
                continue

            with self._lock:
                self._frame = frame

            self._frame_count += 1
            self._update_fps()

        self._release_capture()

    def _update_fps(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._last_fps_time = now


class MultiCameraManager:
    """Manages multiple :class:`CameraStream` instances.

    Supports dynamic add/remove, bulk start/stop, and health monitoring.
    Can be used as a context manager.
    """

    def __init__(self) -> None:
        self._cameras: Dict[str, CameraStream] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "MultiCameraManager":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[override]
        self.stop_all()

    # ------------------------------------------------------------------
    # Camera management
    # ------------------------------------------------------------------

    def add_camera(
        self,
        camera_id: str,
        rtsp_url: str,
        target_fps: int = 15,
        resolution: Optional[Tuple[int, int]] = None,
    ) -> None:
        """Register a new camera stream."""
        with self._lock:
            if camera_id in self._cameras:
                logger.warning("Camera %s already registered.", camera_id)
                return
            stream = CameraStream(camera_id, rtsp_url, target_fps, resolution)
            self._cameras[camera_id] = stream
            logger.info("Camera %s added.", camera_id)

    def remove_camera(self, camera_id: str) -> None:
        """Stop and remove a camera stream."""
        with self._lock:
            stream = self._cameras.pop(camera_id, None)
        if stream:
            stream.stop()
            logger.info("Camera %s removed.", camera_id)

    def start_all(self) -> None:
        """Start all registered camera streams."""
        with self._lock:
            cameras = list(self._cameras.values())
        for cam in cameras:
            cam.start()

    def stop_all(self) -> None:
        """Stop all registered camera streams."""
        with self._lock:
            cameras = list(self._cameras.values())
        for cam in cameras:
            cam.stop()
        logger.info("All cameras stopped.")

    def get_frames(self) -> Dict[str, Optional[np.ndarray]]:
        """Return the latest frame from every registered camera."""
        with self._lock:
            cameras = dict(self._cameras)
        return {cid: cam.read() for cid, cam in cameras.items()}

    def get_health(self) -> List[CameraInfo]:
        """Return health / metadata for every registered camera."""
        with self._lock:
            cameras = list(self._cameras.values())
        return [cam.info for cam in cameras]

    @property
    def camera_ids(self) -> List[str]:
        with self._lock:
            return list(self._cameras.keys())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mgr = MultiCameraManager()
    mgr.add_camera("test", "0")  # webcam index 0
    mgr.start_all()
    try:
        while True:
            frames = mgr.get_frames()
            for cid, frame in frames.items():
                if frame is not None:
                    cv2.imshow(cid, frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        mgr.stop_all()
        cv2.destroyAllWindows()
