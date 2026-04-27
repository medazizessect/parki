"""Main entry point for the Parki capture reconnaissance pipeline.

Initialises cameras, the YOLO detector, the vehicle tracker, and the
database handler, then runs a continuous processing loop with graceful
shutdown support.
"""

import argparse
import logging
import signal
import sys
import time
from typing import Optional

import cv2
import yaml

from .config import AppConfig, setup_logging
from .data_handler import DatabaseHandler
from .vehicle_tracker import VehicleTracker
from .video_capture import MultiCameraManager
from .yolo_detector import VehicleDetector

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
_shutdown_requested = False


def _signal_handler(signum: int, frame) -> None:  # noqa: ANN001
    global _shutdown_requested
    logger.info("Received signal %s — shutting down …", signal.Signals(signum).name)
    _shutdown_requested = True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parki Capture Reconnaissance — real-time traffic monitoring",
    )
    parser.add_argument(
        "--cameras-config",
        type=str,
        default=None,
        help="Path to cameras.yaml configuration file.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        default=False,
        help="Show a live preview window for each camera.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of events to accumulate before a batch insert.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="Override log level (DEBUG, INFO, WARNING, ERROR).",
    )
    return parser.parse_args()


def _load_cameras_yaml(path: str) -> list:
    """Load camera definitions from a YAML file."""
    try:
        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
        return data.get("cameras", [])
    except Exception:
        logger.exception("Failed to load cameras config from %s", path)
        return []


def run(
    config: Optional[AppConfig] = None,
    cameras_config_path: Optional[str] = None,
    preview: bool = False,
    batch_size: int = 50,
) -> None:
    """Run the main capture-reconnaissance pipeline.

    Parameters
    ----------
    config:
        Application configuration; built from env if ``None``.
    cameras_config_path:
        Optional YAML file listing camera streams.
    preview:
        If ``True``, display live frames via OpenCV highgui.
    batch_size:
        Number of events to buffer before flushing to the DB.
    """
    global _shutdown_requested
    _shutdown_requested = False

    if config is None:
        config = AppConfig.from_env()

    # --- Initialise components -------------------------------------------
    detector = VehicleDetector(
        model_path=config.yolo.model_path,
        confidence_threshold=config.yolo.confidence_threshold,
        device=config.yolo.device,
    )

    db = DatabaseHandler(
        host=config.mysql.host,
        port=config.mysql.port,
        user=config.mysql.user,
        password=config.mysql.password,
        database=config.mysql.database,
        pool_size=config.mysql.pool_size,
    )

    trackers: dict[str, VehicleTracker] = {}
    event_buffer: list = []

    with MultiCameraManager() as manager:
        # Register cameras from YAML or environment
        camera_defs: list = []
        if cameras_config_path:
            camera_defs = _load_cameras_yaml(cameras_config_path)
        if not camera_defs:
            # Fallback to env-configured URLs
            for idx, url in enumerate(config.camera.rtsp_urls):
                camera_defs.append({"id": f"cam_{idx}", "rtsp_url": url})

        for cam in camera_defs:
            cid = str(cam["id"])
            url = cam["rtsp_url"]
            manager.add_camera(
                camera_id=cid,
                rtsp_url=url,
                target_fps=config.camera.fps,
                resolution=(
                    config.camera.resolution_width,
                    config.camera.resolution_height,
                ),
            )
            trackers[cid] = VehicleTracker(
                camera_id=cid,
                pixels_per_metre=8.0,
                target_fps=float(config.camera.fps),
            )

        manager.start_all()
        logger.info("Pipeline started with %d camera(s).", len(manager.camera_ids))

        # --- Main loop ---------------------------------------------------
        try:
            while not _shutdown_requested:
                frames = manager.get_frames()
                now = time.time()

                for cid, frame in frames.items():
                    if frame is None:
                        continue

                    detections = detector.detect(frame)
                    tracker = trackers.get(cid)
                    if tracker is None:
                        continue

                    events = tracker.update(detections, frame_time=now)
                    event_buffer.extend(events)

                    if preview:
                        _draw_preview(frame, detections, cid)

                # Flush buffer when it reaches batch_size
                if len(event_buffer) >= batch_size:
                    db.insert_batch(event_buffer)
                    event_buffer.clear()

                if preview:
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        logger.info("Preview window closed by user.")
                        break

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received.")
        finally:
            # Flush remaining events
            if event_buffer:
                db.insert_batch(event_buffer)
                event_buffer.clear()
            db.close()
            if preview:
                cv2.destroyAllWindows()
            logger.info("Pipeline shut down cleanly.")


def _draw_preview(frame, detections, camera_id: str) -> None:  # noqa: ANN001
    """Draw bounding boxes on the frame and display it."""
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det.bbox]
        label = f"{det.class_name} {det.confidence:.2f}"
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            frame, label, (x1, y1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2,
        )
    cv2.imshow(f"Parki — {camera_id}", frame)


def main() -> None:
    """CLI entry point."""
    args = _parse_args()
    config = AppConfig.from_env()
    log_level = args.log_level or config.log_level
    setup_logging(log_level)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    run(
        config=config,
        cameras_config_path=args.cameras_config,
        preview=args.preview,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
