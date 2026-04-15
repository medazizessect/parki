"""Circuli - Centroid-based vehicle tracking module."""

import logging
import math
from collections import OrderedDict
from dataclasses import dataclass, field

APP_NAME = "Circuli"
logger = logging.getLogger(APP_NAME)


@dataclass
class TrackedVehicle:
    """A tracked vehicle with an assigned ID."""

    vehicle_id: int
    centroid: tuple[float, float]
    class_name: str
    frames_since_seen: int = 0


class VehicleTracker:
    """Track vehicles across frames using centroid distance matching."""

    def __init__(self, max_disappeared: int = 30, max_distance: float = 80.0) -> None:
        self._next_id = 0
        self._objects: OrderedDict[int, TrackedVehicle] = OrderedDict()
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance
        self.total_entered = 0
        self.total_exited = 0
        self._counted_ids: set[int] = set()

    @property
    def active_count(self) -> int:
        return len(self._objects)

    def _register(self, centroid: tuple[float, float], class_name: str) -> int:
        vehicle = TrackedVehicle(
            vehicle_id=self._next_id,
            centroid=centroid,
            class_name=class_name,
        )
        self._objects[self._next_id] = vehicle
        vehicle_id = self._next_id
        self._next_id += 1
        self.total_entered += 1
        logger.debug("[%s] Registered vehicle ID %d", APP_NAME, vehicle_id)
        return vehicle_id

    def _deregister(self, vehicle_id: int) -> None:
        del self._objects[vehicle_id]
        if vehicle_id not in self._counted_ids:
            self.total_exited += 1
            self._counted_ids.add(vehicle_id)
        logger.debug("[%s] Deregistered vehicle ID %d", APP_NAME, vehicle_id)

    @staticmethod
    def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)

    def update(
        self, detections: list[tuple[tuple[float, float], str]]
    ) -> dict[int, TrackedVehicle]:
        """Update tracker with new detections.

        Args:
            detections: List of (centroid, class_name) tuples.

        Returns:
            Dictionary of currently tracked vehicles.
        """
        if not detections:
            for vehicle_id in list(self._objects.keys()):
                self._objects[vehicle_id].frames_since_seen += 1
                if self._objects[vehicle_id].frames_since_seen > self.max_disappeared:
                    self._deregister(vehicle_id)
            return dict(self._objects)

        if not self._objects:
            for centroid, class_name in detections:
                self._register(centroid, class_name)
            return dict(self._objects)

        object_ids = list(self._objects.keys())
        object_centroids = [self._objects[oid].centroid for oid in object_ids]

        # Build distance matrix
        distances: list[list[float]] = []
        for obj_centroid in object_centroids:
            row = [self._distance(obj_centroid, det[0]) for det in detections]
            distances.append(row)

        # Greedy matching: assign closest pairs first
        used_rows: set[int] = set()
        used_cols: set[int] = set()

        flat = []
        for r, row in enumerate(distances):
            for c, d in enumerate(row):
                flat.append((d, r, c))
        flat.sort()

        for dist, row, col in flat:
            if row in used_rows or col in used_cols:
                continue
            if dist > self.max_distance:
                break
            vehicle_id = object_ids[row]
            self._objects[vehicle_id].centroid = detections[col][0]
            self._objects[vehicle_id].class_name = detections[col][1]
            self._objects[vehicle_id].frames_since_seen = 0
            used_rows.add(row)
            used_cols.add(col)

        # Handle unmatched existing objects
        for row in range(len(object_ids)):
            if row not in used_rows:
                vid = object_ids[row]
                self._objects[vid].frames_since_seen += 1
                if self._objects[vid].frames_since_seen > self.max_disappeared:
                    self._deregister(vid)

        # Register new detections
        for col in range(len(detections)):
            if col not in used_cols:
                self._register(detections[col][0], detections[col][1])

        return dict(self._objects)

    def get_counts(self) -> dict[str, int]:
        """Return current vehicle counts."""
        return {
            "active": self.active_count,
            "total_entered": self.total_entered,
            "total_exited": self.total_exited,
        }
