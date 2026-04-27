"""Vehicle tracking and traffic metrics.

Implements a simple centroid-based tracker that associates detections
across consecutive frames, counts vehicles by type, estimates speed
from pixel displacement, and infers travel direction.
"""

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .yolo_detector import Detection

logger = logging.getLogger(__name__)

# Default calibration: pixels-per-metre (must be tuned per camera)
_DEFAULT_PPM = 8.0
_MAX_DISAPPEARED_FRAMES = 30


@dataclass
class TrafficEvent:
    """A recorded traffic observation."""

    timestamp: float
    camera_id: str
    vehicle_type: str
    speed_estimate: float  # km/h
    direction: str  # e.g. "north", "south", "east", "west"
    bbox: Tuple[float, float, float, float]
    confidence: float
    frame_number: int = 0


@dataclass
class _TrackedObject:
    """Internal bookkeeping for a tracked centroid."""

    object_id: int
    centroid: np.ndarray
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]
    prev_centroid: Optional[np.ndarray] = None
    disappeared: int = 0
    frame_time: float = field(default_factory=time.time)
    prev_frame_time: float = 0.0


class VehicleTracker:
    """Centroid-based multi-object tracker with traffic metrics.

    Parameters
    ----------
    max_disappeared:
        Number of consecutive frames an object may be missing before
        it is deregistered.
    pixels_per_metre:
        Camera calibration factor used to convert pixel displacement
        to real-world speed estimates.
    target_fps:
        Expected capture FPS — used for speed calculation when frame
        timestamps are not available.
    """

    def __init__(
        self,
        camera_id: str = "cam_0",
        max_disappeared: int = _MAX_DISAPPEARED_FRAMES,
        pixels_per_metre: float = _DEFAULT_PPM,
        target_fps: float = 15.0,
    ) -> None:
        self.camera_id = camera_id
        self.max_disappeared = max_disappeared
        self.pixels_per_metre = pixels_per_metre
        self.target_fps = target_fps

        self._next_id = 0
        self._objects: OrderedDict[int, _TrackedObject] = OrderedDict()
        self._vehicle_counts: Dict[str, int] = {}
        self._frame_number: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self, detections: List[Detection], frame_time: Optional[float] = None
    ) -> List[TrafficEvent]:
        """Process a new set of detections and return generated events.

        Parameters
        ----------
        detections:
            Detections in the current frame.
        frame_time:
            Timestamp of the current frame (``time.time()``).

        Returns
        -------
        List of :class:`TrafficEvent` for any newly deregistered or
        actively tracked objects.
        """
        self._frame_number += 1
        now = frame_time if frame_time is not None else time.time()
        events: List[TrafficEvent] = []

        if not detections:
            events.extend(self._mark_all_disappeared(now))
            return events

        input_centroids = np.array(
            [self._centroid(d.bbox) for d in detections]
        )

        if not self._objects:
            for i, det in enumerate(detections):
                self._register(input_centroids[i], det, now)
            return events

        object_ids = list(self._objects.keys())
        object_centroids = np.array(
            [self._objects[oid].centroid for oid in object_ids]
        )

        # Pairwise distance matrix
        dists = np.linalg.norm(
            object_centroids[:, np.newaxis] - input_centroids[np.newaxis, :],
            axis=2,
        )

        rows = dists.min(axis=1).argsort()
        cols = dists.argmin(axis=1)[rows]

        used_rows: set = set()
        used_cols: set = set()

        for row, col in zip(rows, cols):
            if row in used_rows or col in used_cols:
                continue
            used_rows.add(row)
            used_cols.add(col)
            oid = object_ids[row]
            obj = self._objects[oid]
            obj.prev_centroid = obj.centroid.copy()
            obj.prev_frame_time = obj.frame_time
            obj.centroid = input_centroids[col]
            obj.class_name = detections[col].class_name
            obj.confidence = detections[col].confidence
            obj.bbox = detections[col].bbox
            obj.disappeared = 0
            obj.frame_time = now

            event = self._build_event(obj)
            if event is not None:
                events.append(event)

        # Handle unmatched existing objects
        for row in set(range(len(object_ids))) - used_rows:
            oid = object_ids[row]
            ev = self._mark_disappeared(oid, now)
            if ev is not None:
                events.append(ev)

        # Register new detections
        for col in set(range(len(detections))) - used_cols:
            self._register(input_centroids[col], detections[col], now)

        return events

    @property
    def vehicle_counts(self) -> Dict[str, int]:
        """Cumulative vehicle counts by type."""
        return dict(self._vehicle_counts)

    def reset(self) -> None:
        """Clear all tracked objects and counters."""
        self._objects.clear()
        self._vehicle_counts.clear()
        self._next_id = 0
        self._frame_number = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _centroid(bbox: Tuple[float, float, float, float]) -> np.ndarray:
        x1, y1, x2, y2 = bbox
        return np.array([(x1 + x2) / 2.0, (y1 + y2) / 2.0])

    def _register(
        self, centroid: np.ndarray, det: Detection, now: float
    ) -> None:
        obj = _TrackedObject(
            object_id=self._next_id,
            centroid=centroid,
            class_name=det.class_name,
            confidence=det.confidence,
            bbox=det.bbox,
            frame_time=now,
        )
        self._objects[self._next_id] = obj
        self._next_id += 1
        self._vehicle_counts[det.class_name] = (
            self._vehicle_counts.get(det.class_name, 0) + 1
        )

    def _deregister(self, object_id: int) -> None:
        del self._objects[object_id]

    def _mark_disappeared(self, oid: int, now: float) -> Optional[TrafficEvent]:
        obj = self._objects[oid]
        obj.disappeared += 1
        if obj.disappeared > self.max_disappeared:
            event = self._build_event(obj)
            self._deregister(oid)
            return event
        return None

    def _mark_all_disappeared(self, now: float) -> List[TrafficEvent]:
        events: List[TrafficEvent] = []
        for oid in list(self._objects.keys()):
            ev = self._mark_disappeared(oid, now)
            if ev is not None:
                events.append(ev)
        return events

    def _estimate_speed(self, obj: _TrackedObject) -> float:
        """Estimate speed in km/h from pixel displacement between frames."""
        if obj.prev_centroid is None:
            return 0.0
        displacement_px = float(np.linalg.norm(obj.centroid - obj.prev_centroid))
        dt = obj.frame_time - obj.prev_frame_time
        if dt <= 0:
            dt = 1.0 / self.target_fps
        displacement_m = displacement_px / self.pixels_per_metre
        speed_ms = displacement_m / dt
        return speed_ms * 3.6  # m/s → km/h

    @staticmethod
    def _estimate_direction(obj: _TrackedObject) -> str:
        """Infer cardinal direction from centroid movement."""
        if obj.prev_centroid is None:
            return "unknown"
        dx = obj.centroid[0] - obj.prev_centroid[0]
        dy = obj.centroid[1] - obj.prev_centroid[1]
        if abs(dx) > abs(dy):
            return "east" if dx > 0 else "west"
        elif abs(dy) > 0:
            return "south" if dy > 0 else "north"
        return "stationary"

    def _build_event(self, obj: _TrackedObject) -> Optional[TrafficEvent]:
        speed = self._estimate_speed(obj)
        direction = self._estimate_direction(obj)
        return TrafficEvent(
            timestamp=obj.frame_time,
            camera_id=self.camera_id,
            vehicle_type=obj.class_name,
            speed_estimate=round(speed, 2),
            direction=direction,
            bbox=obj.bbox,
            confidence=round(obj.confidence, 4),
            frame_number=self._frame_number,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tracker = VehicleTracker(camera_id="test_cam")
    sample = Detection(
        bbox=(100, 100, 200, 200), class_name="car", confidence=0.9, class_id=2
    )
    events = tracker.update([sample])
    logger.info("Events after first frame: %s", events)
    sample2 = Detection(
        bbox=(110, 105, 210, 205), class_name="car", confidence=0.88, class_id=2
    )
    events2 = tracker.update([sample2])
    logger.info("Events after second frame: %s", events2)
    logger.info("Vehicle counts: %s", tracker.vehicle_counts)
