"""Circuli - Parking recommendation engine."""

import logging
from dataclasses import dataclass, field

from .database import DatabaseManager

logger = logging.getLogger("circuli.recommendations")


@dataclass
class ParkingRecommendation:
    """A scored parking recommendation."""

    location: str
    city: str
    latitude: float
    longitude: float
    score: float
    available_spots: int
    avg_occupancy_pct: float
    peak_hour: int
    reason: str
    tags: list[str] = field(default_factory=list)


class ParkingRecommender:
    """Suggests optimal parking locations based on availability and historical data."""

    # Weights for scoring
    WEIGHT_AVAILABILITY = 0.45
    WEIGHT_LOW_TRAFFIC = 0.30
    WEIGHT_OFF_PEAK = 0.25

    def __init__(self, db: DatabaseManager, total_capacity_per_location: int = 100):
        self.db = db
        self.total_capacity = total_capacity_per_location

    def _fetch_parking_stats(self, days: int = 30) -> list[dict]:
        """Fetch historical parking and traffic statistics per location."""
        return self.db.execute_query(
            """
            SELECT dl.stream_name AS location, dl.city,
                   dl.latitude, dl.longitude,
                   SUM(CASE WHEN f.is_parked THEN f.count ELSE 0 END) AS total_parked,
                   SUM(f.count) AS total_vehicles,
                   COUNT(DISTINCT dt.date) AS active_days,
                   (SELECT sub_dt.hour
                    FROM fact_detections sub_f
                    JOIN dim_time sub_dt ON sub_f.time_id = sub_dt.time_id
                    WHERE sub_f.location_id = dl.location_id
                      AND sub_f.is_parked = TRUE
                      AND sub_dt.date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    GROUP BY sub_dt.hour
                    ORDER BY SUM(sub_f.count) DESC
                    LIMIT 1) AS peak_hour
            FROM fact_detections f
            JOIN dim_location dl ON f.location_id = dl.location_id
            JOIN dim_time dt ON f.time_id = dt.time_id
            WHERE dt.date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY dl.location_id, dl.stream_name, dl.city,
                     dl.latitude, dl.longitude
            """,
            (days, days),
        )

    def _score_location(self, row: dict) -> tuple[float, str, list[str]]:
        """Compute a recommendation score for a location.

        Higher score = better recommendation.
        """
        active_days = int(row["active_days"]) or 1
        avg_daily_parked = float(row["total_parked"]) / active_days
        avg_daily_vehicles = float(row["total_vehicles"]) / active_days

        occupancy_pct = min(avg_daily_parked / self.total_capacity, 1.0)
        availability_score = 1.0 - occupancy_pct

        max_traffic = self.total_capacity * 5
        traffic_score = max(0.0, 1.0 - (avg_daily_vehicles / max_traffic))

        peak_hour = int(row["peak_hour"]) if row["peak_hour"] is not None else 12
        off_peak_score = 1.0 if peak_hour < 7 or peak_hour > 20 else 0.5

        score = (
            self.WEIGHT_AVAILABILITY * availability_score
            + self.WEIGHT_LOW_TRAFFIC * traffic_score
            + self.WEIGHT_OFF_PEAK * off_peak_score
        )
        score = round(min(score, 1.0), 4)

        tags: list[str] = []
        reasons: list[str] = []

        if availability_score > 0.7:
            tags.append("high-availability")
            reasons.append("high availability")
        elif availability_score > 0.3:
            tags.append("moderate-availability")
        else:
            tags.append("low-availability")
            reasons.append("limited spots")

        if traffic_score > 0.6:
            tags.append("low-traffic")
            reasons.append("low surrounding traffic")
        if off_peak_score == 1.0:
            tags.append("off-peak-friendly")

        reason = "; ".join(reasons) if reasons else "average conditions"
        return score, reason, tags

    def recommend(
        self,
        days: int = 30,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[ParkingRecommendation]:
        """Return scored parking recommendations sorted best-first.

        Args:
            days: Number of historical days to consider.
            limit: Maximum number of recommendations to return.
            min_score: Minimum score threshold.
        """
        rows = self._fetch_parking_stats(days)
        if not rows:
            logger.info("Circuli recommender: no data available")
            return []

        recommendations: list[ParkingRecommendation] = []
        for row in rows:
            active_days = int(row["active_days"]) or 1
            avg_daily_parked = float(row["total_parked"]) / active_days
            occupancy_pct = round(min(avg_daily_parked / self.total_capacity, 1.0) * 100, 1)
            available = max(0, self.total_capacity - int(avg_daily_parked))

            score, reason, tags = self._score_location(row)
            if score < min_score:
                continue

            recommendations.append(
                ParkingRecommendation(
                    location=row["location"] or "Unknown",
                    city=row["city"] or "Unknown",
                    latitude=float(row["latitude"]) if row["latitude"] else 0.0,
                    longitude=float(row["longitude"]) if row["longitude"] else 0.0,
                    score=score,
                    available_spots=available,
                    avg_occupancy_pct=occupancy_pct,
                    peak_hour=int(row["peak_hour"]) if row["peak_hour"] is not None else 0,
                    reason=reason,
                    tags=tags,
                )
            )

        recommendations.sort(key=lambda r: r.score, reverse=True)
        logger.info("Circuli recommender: %d recommendations generated", len(recommendations))
        return recommendations[:limit]
