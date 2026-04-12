"""YOLOv8s vehicle detection module.

Wraps the Ultralytics YOLOv8 model to detect vehicles in video frames,
filtering results to relevant vehicle classes and exposing a clean
``Detection`` dataclass for downstream consumers.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# COCO class IDs for vehicle types
VEHICLE_CLASSES: dict[int, str] = {
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


@dataclass
class Detection:
    """A single detected vehicle."""

    bbox: Tuple[float, float, float, float]  # (x1, y1, x2, y2)
    class_name: str
    confidence: float
    class_id: int


class VehicleDetector:
    """Detect vehicles in frames using a YOLOv8 model.

    Parameters
    ----------
    model_path:
        Path to the YOLOv8 weights file (e.g. ``yolov8s.pt``).
    confidence_threshold:
        Minimum confidence to accept a detection.
    device:
        Inference device — ``"cpu"``, ``"cuda"``, ``"cuda:0"``, etc.
    """

    def __init__(
        self,
        model_path: str = "yolov8s.pt",
        confidence_threshold: float = 0.4,
        device: str = "cpu",
    ) -> None:
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.device = device
        self._model = None
        self._load_model()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Run detection on a single frame and return vehicle detections."""
        if self._model is None:
            logger.error("Model not loaded — skipping detection.")
            return []

        results = self._model.predict(
            source=frame,
            conf=self.confidence_threshold,
            device=self.device,
            verbose=False,
        )
        return self._parse_results(results)

    def detect_batch(self, frames: Sequence[np.ndarray]) -> List[List[Detection]]:
        """Run detection on a batch of frames.

        Returns a list of detection lists, one per input frame.
        """
        if self._model is None:
            logger.error("Model not loaded — skipping batch detection.")
            return [[] for _ in frames]

        results = self._model.predict(
            source=list(frames),
            conf=self.confidence_threshold,
            device=self.device,
            verbose=False,
        )
        return [self._parse_results([r]) for r in results]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Load the YOLO model, logging any errors."""
        try:
            from ultralytics import YOLO  # lazy import keeps module importable

            self._model = YOLO(self.model_path)
            logger.info(
                "YOLOv8 model loaded from %s on device=%s",
                self.model_path,
                self.device,
            )
        except Exception:
            logger.exception("Failed to load YOLO model from %s", self.model_path)
            self._model = None

    def _parse_results(self, results) -> List[Detection]:  # noqa: ANN001
        """Convert raw YOLO results into a list of ``Detection`` objects."""
        detections: List[Detection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls[0])
                if cls_id not in VEHICLE_CLASSES:
                    continue
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append(
                    Detection(
                        bbox=(x1, y1, x2, y2),
                        class_name=VEHICLE_CLASSES[cls_id],
                        confidence=conf,
                        class_id=cls_id,
                    )
                )
        return detections


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    detector = VehicleDetector()
    # Quick smoke test with a blank frame
    blank = np.zeros((640, 640, 3), dtype=np.uint8)
    dets = detector.detect(blank)
    logger.info("Detections on blank frame: %d", len(dets))
