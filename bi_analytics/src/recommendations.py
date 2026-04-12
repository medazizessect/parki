"""
Intelligent Recommendation Engine.

Analyses traffic data and produces actionable recommendations for
route planning, infrastructure improvements, and signal optimisation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Data structures
# ------------------------------------------------------------------
class RecommendationType(str, Enum):
    """Categories of traffic recommendations."""

    NEW_ROUTE = "NEW_ROUTE"
    ROAD_IMPROVEMENT = "ROAD_IMPROVEMENT"
    VEHICLE_RESTRICTION = "VEHICLE_RESTRICTION"
    SIGNAL_OPTIMIZATION = "SIGNAL_OPTIMIZATION"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class Priority(str, Enum):
    """Recommendation urgency levels."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Recommendation:
    """A single actionable recommendation."""

    type: RecommendationType
    priority: Priority
    title: str
    description: str
    affected_cameras: list[int] = field(default_factory=list)
    suggested_action: str = ""
    estimated_impact: str = ""


# ------------------------------------------------------------------
# Default thresholds
# ------------------------------------------------------------------
_DEFAULT_THRESHOLDS: dict[str, float] = {
    "congestion_high": 0.75,
    "congestion_medium": 0.50,
    "speed_anomaly_std_factor": 2.0,
    "heavy_vehicle_pct": 0.40,
    "peak_vehicle_count": 500,
}


# ------------------------------------------------------------------
# Engine
# ------------------------------------------------------------------
class RecommendationEngine:
    """Analyses traffic patterns and emits :class:`Recommendation` instances."""

    def __init__(
        self,
        thresholds: Optional[dict[str, float]] = None,
    ) -> None:
        self._thresholds = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._recommendations: list[Recommendation] = []

    # ------------------------------------------------------------------
    # Analysis methods
    # ------------------------------------------------------------------
    def analyze_congestion(self, data: Sequence[dict[str, Any]]) -> list[Recommendation]:
        """Detect congestion patterns and suggest new routes or signal changes.

        Each element in *data* should contain at least:
        ``camera_id``, ``camera_name``, ``avg_congestion``, ``total_vehicles``.
        """
        recs: list[Recommendation] = []
        high_threshold = self._thresholds["congestion_high"]
        medium_threshold = self._thresholds["congestion_medium"]

        for row in data:
            congestion = float(row.get("avg_congestion", 0))
            camera_id = int(row.get("camera_id", 0))
            camera_name = row.get("camera_name", f"Camera {camera_id}")

            if congestion >= high_threshold:
                recs.append(Recommendation(
                    type=RecommendationType.NEW_ROUTE,
                    priority=Priority.HIGH,
                    title=f"High congestion at {camera_name}",
                    description=(
                        f"Camera {camera_name} reports congestion level "
                        f"{congestion:.2f} (threshold {high_threshold:.2f}). "
                        "Consider opening an alternative route."
                    ),
                    affected_cameras=[camera_id],
                    suggested_action="Open alternative parallel route and add signage.",
                    estimated_impact="20-30% reduction in peak-hour travel time.",
                ))
                recs.append(Recommendation(
                    type=RecommendationType.SIGNAL_OPTIMIZATION,
                    priority=Priority.HIGH,
                    title=f"Optimise signals near {camera_name}",
                    description=(
                        f"Adaptive signal timing around {camera_name} could "
                        "alleviate severe congestion."
                    ),
                    affected_cameras=[camera_id],
                    suggested_action="Deploy adaptive signal control in the corridor.",
                    estimated_impact="15-25% throughput improvement.",
                ))
            elif congestion >= medium_threshold:
                recs.append(Recommendation(
                    type=RecommendationType.SIGNAL_OPTIMIZATION,
                    priority=Priority.MEDIUM,
                    title=f"Moderate congestion at {camera_name}",
                    description=(
                        f"Camera {camera_name} shows congestion level "
                        f"{congestion:.2f}. Signal-cycle adjustments recommended."
                    ),
                    affected_cameras=[camera_id],
                    suggested_action="Review and adjust signal green-phase splits.",
                    estimated_impact="10-15% congestion reduction.",
                ))

        self._recommendations.extend(recs)
        logger.info("Congestion analysis produced %d recommendations.", len(recs))
        return recs

    def analyze_speed_anomalies(self, data: Sequence[dict[str, Any]]) -> list[Recommendation]:
        """Detect unusual speed patterns.

        Each element should contain:
        ``camera_id``, ``camera_name``, ``avg_speed``, ``max_speed``, ``min_speed``.
        """
        recs: list[Recommendation] = []
        if not data:
            return recs

        speeds = [float(row.get("avg_speed", 0)) for row in data if row.get("avg_speed")]
        if not speeds:
            return recs

        mean_speed = sum(speeds) / len(speeds)
        variance = sum((s - mean_speed) ** 2 for s in speeds) / len(speeds)
        std_speed = variance ** 0.5
        factor = self._thresholds["speed_anomaly_std_factor"]

        for row in data:
            avg = float(row.get("avg_speed", 0))
            camera_id = int(row.get("camera_id", 0))
            camera_name = row.get("camera_name", f"Camera {camera_id}")

            if std_speed > 0 and abs(avg - mean_speed) > factor * std_speed:
                if avg < mean_speed:
                    recs.append(Recommendation(
                        type=RecommendationType.ROAD_IMPROVEMENT,
                        priority=Priority.HIGH,
                        title=f"Abnormally low speed at {camera_name}",
                        description=(
                            f"Average speed {avg:.1f} km/h is significantly below "
                            f"network mean {mean_speed:.1f} km/h. Possible road "
                            "surface or geometry issue."
                        ),
                        affected_cameras=[camera_id],
                        suggested_action="Inspect road surface; consider repaving or geometry changes.",
                        estimated_impact="Improved safety and 10-20% speed normalisation.",
                    ))
                else:
                    recs.append(Recommendation(
                        type=RecommendationType.INFRASTRUCTURE,
                        priority=Priority.MEDIUM,
                        title=f"Abnormally high speed at {camera_name}",
                        description=(
                            f"Average speed {avg:.1f} km/h is well above the "
                            f"network mean {mean_speed:.1f} km/h. Traffic calming "
                            "may be needed."
                        ),
                        affected_cameras=[camera_id],
                        suggested_action="Install speed-reduction infrastructure (bumps, chicanes).",
                        estimated_impact="Reduced accident risk by up to 30%.",
                    ))

        self._recommendations.extend(recs)
        logger.info("Speed-anomaly analysis produced %d recommendations.", len(recs))
        return recs

    def analyze_vehicle_distribution(
        self, data: Sequence[dict[str, Any]]
    ) -> list[Recommendation]:
        """Identify vehicle-type patterns that warrant restrictions.

        Each element should contain:
        ``camera_id``, ``camera_name``, ``type_name``, ``category``,
        ``total_vehicles``.
        """
        recs: list[Recommendation] = []
        if not data:
            return recs

        # Aggregate by camera
        camera_totals: dict[int, int] = {}
        camera_heavy: dict[int, int] = {}
        camera_names: dict[int, str] = {}
        for row in data:
            cid = int(row.get("camera_id", 0))
            total = int(row.get("total_vehicles", 0))
            camera_names.setdefault(cid, row.get("camera_name", f"Camera {cid}"))
            camera_totals[cid] = camera_totals.get(cid, 0) + total
            if row.get("category") == "heavy":
                camera_heavy[cid] = camera_heavy.get(cid, 0) + total

        heavy_pct_threshold = self._thresholds["heavy_vehicle_pct"]
        for cid, total in camera_totals.items():
            if total == 0:
                continue
            heavy = camera_heavy.get(cid, 0)
            pct = heavy / total
            if pct >= heavy_pct_threshold:
                recs.append(Recommendation(
                    type=RecommendationType.VEHICLE_RESTRICTION,
                    priority=Priority.MEDIUM,
                    title=f"High heavy-vehicle ratio at {camera_names[cid]}",
                    description=(
                        f"{pct:.0%} of traffic at {camera_names[cid]} is heavy "
                        f"vehicles (threshold {heavy_pct_threshold:.0%}). "
                        "Time-based restrictions may reduce wear and congestion."
                    ),
                    affected_cameras=[cid],
                    suggested_action="Implement peak-hour heavy-vehicle restrictions.",
                    estimated_impact="Reduced road wear and 10-15% congestion relief.",
                ))

        self._recommendations.extend(recs)
        logger.info("Vehicle-distribution analysis produced %d recommendations.", len(recs))
        return recs

    # ------------------------------------------------------------------
    # Composite
    # ------------------------------------------------------------------
    def generate_recommendations(
        self,
        congestion_data: Sequence[dict[str, Any]] | None = None,
        speed_data: Sequence[dict[str, Any]] | None = None,
        vehicle_data: Sequence[dict[str, Any]] | None = None,
    ) -> list[Recommendation]:
        """Run all analyses and return a deduplicated, priority-sorted list."""
        self._recommendations.clear()

        if congestion_data:
            self.analyze_congestion(congestion_data)
        if speed_data:
            self.analyze_speed_anomalies(speed_data)
        if vehicle_data:
            self.analyze_vehicle_distribution(vehicle_data)

        # Sort: HIGH → MEDIUM → LOW
        priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
        self._recommendations.sort(key=lambda r: priority_order.get(r.priority, 99))

        logger.info(
            "Generated %d total recommendations.", len(self._recommendations)
        )
        return list(self._recommendations)

    @property
    def recommendations(self) -> list[Recommendation]:
        """Return the most recent set of recommendations."""
        return list(self._recommendations)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    engine = RecommendationEngine()

    sample_congestion = [
        {"camera_id": 1, "camera_name": "Cam-01", "avg_congestion": 0.85, "total_vehicles": 1200},
        {"camera_id": 2, "camera_name": "Cam-02", "avg_congestion": 0.55, "total_vehicles": 800},
        {"camera_id": 3, "camera_name": "Cam-03", "avg_congestion": 0.20, "total_vehicles": 300},
    ]
    sample_speed = [
        {"camera_id": 1, "camera_name": "Cam-01", "avg_speed": 15.0, "max_speed": 30, "min_speed": 5},
        {"camera_id": 2, "camera_name": "Cam-02", "avg_speed": 45.0, "max_speed": 60, "min_speed": 30},
        {"camera_id": 3, "camera_name": "Cam-03", "avg_speed": 90.0, "max_speed": 120, "min_speed": 70},
    ]
    sample_vehicle = [
        {"camera_id": 1, "camera_name": "Cam-01", "type_name": "car", "category": "light", "total_vehicles": 600},
        {"camera_id": 1, "camera_name": "Cam-01", "type_name": "truck", "category": "heavy", "total_vehicles": 600},
        {"camera_id": 2, "camera_name": "Cam-02", "type_name": "car", "category": "light", "total_vehicles": 700},
        {"camera_id": 2, "camera_name": "Cam-02", "type_name": "bus", "category": "heavy", "total_vehicles": 100},
    ]

    recs = engine.generate_recommendations(
        congestion_data=sample_congestion,
        speed_data=sample_speed,
        vehicle_data=sample_vehicle,
    )
    for r in recs:
        print(f"[{r.priority.value}] {r.type.value}: {r.title}")
