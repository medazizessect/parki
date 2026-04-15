"""Circuli - YOLO-based vehicle detection module."""

import logging
from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO

APP_NAME = "Circuli"
logger = logging.getLogger(APP_NAME)

# COCO class IDs for vehicle types
VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}


@dataclass
class Detection:
    """A single vehicle detection result."""

    class_id: int
    class_name: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


class VehicleDetector:
    """Detect vehicles in video frames using YOLOv8."""

    def __init__(self, model_path: str = "yolov8s.pt", confidence_threshold: float = 0.5) -> None:
        logger.info("[%s] Loading YOLO model: %s", APP_NAME, model_path)
        self.model = YOLO(model_path)
        self.confidence_threshold = confidence_threshold
        logger.info("[%s] YOLO model loaded successfully", APP_NAME)

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Run vehicle detection on a single frame.

        Returns a list of Detection objects for vehicles found.
        """
        results = self.model(frame, verbose=False)
        detections: list[Detection] = []

        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for i in range(len(boxes)):
                class_id = int(boxes.cls[i].item())
                confidence = float(boxes.conf[i].item())

                if class_id not in VEHICLE_CLASSES:
                    continue
                if confidence < self.confidence_threshold:
                    continue

                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                detection = Detection(
                    class_id=class_id,
                    class_name=VEHICLE_CLASSES[class_id],
                    confidence=confidence,
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                )
                detections.append(detection)

        logger.debug(
            "[%s] Detected %d vehicles in frame", APP_NAME, len(detections)
        )
        return detections
