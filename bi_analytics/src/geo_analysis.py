"""Circuli - Geo-spatial traffic analysis."""

import logging
from dataclasses import dataclass, field

from .database import DatabaseManager

logger = logging.getLogger("circuli.geo_analysis")


@dataclass
class HeatmapPoint:
    """Single heatmap data point."""

    latitude: float
    longitude: float
    intensity: float
    label: str = ""


@dataclass
class TrafficDensity:
    """Traffic density result for a location."""

    location: str
    city: str
    latitude: float
    longitude: float
    vehicle_count: int
    density_score: float
    peak_hour: int
    tags: list[str] = field(default_factory=list)


class GeoAnalyzer:
    """Analyzes traffic patterns by geographic location for Circuli."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_traffic_by_location(self, days: int = 7) -> list[dict]:
        """Return traffic counts grouped by location for the last N days."""
        return self.db.execute_query(
            """
            SELECT dl.stream_name AS location, dl.city, dl.region, dl.country,
                   dl.latitude, dl.longitude,
                   SUM(f.count) AS total_vehicles
            FROM fact_detections f
            JOIN dim_location dl ON f.location_id = dl.location_id
            JOIN dim_time dt ON f.time_id = dt.time_id
            WHERE dt.date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            GROUP BY dl.location_id, dl.stream_name, dl.city, dl.region,
                     dl.country, dl.latitude, dl.longitude
            ORDER BY total_vehicles DESC
            """,
            (days,),
        )

    def generate_heatmap_data(self, days: int = 7) -> list[HeatmapPoint]:
        """Generate heatmap data points from traffic detections."""
        rows = self.get_traffic_by_location(days)
        if not rows:
            return []

        max_vehicles = max(r["total_vehicles"] for r in rows) or 1
        points: list[HeatmapPoint] = []
        for row in rows:
            lat = float(row["latitude"]) if row["latitude"] else 0.0
            lng = float(row["longitude"]) if row["longitude"] else 0.0
            if lat == 0.0 and lng == 0.0:
                continue
            intensity = float(row["total_vehicles"]) / max_vehicles
            points.append(
                HeatmapPoint(
                    latitude=lat,
                    longitude=lng,
                    intensity=round(intensity, 4),
                    label=row["location"] or row["city"] or "Unknown",
                )
            )
        logger.info("Circuli generated %d heatmap points", len(points))
        return points

    def calculate_traffic_density(self, days: int = 7) -> list[TrafficDensity]:
        """Calculate traffic density scores per location."""
        rows = self.db.execute_query(
            """
            SELECT dl.stream_name AS location, dl.city,
                   dl.latitude, dl.longitude,
                   SUM(f.count) AS total_vehicles,
                   COUNT(DISTINCT dt.date) AS active_days,
                   (SELECT sub_dt.hour
                    FROM fact_detections sub_f
                    JOIN dim_time sub_dt ON sub_f.time_id = sub_dt.time_id
                    WHERE sub_f.location_id = dl.location_id
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

        if not rows:
            return []

        max_vehicles = max(r["total_vehicles"] for r in rows) or 1
        densities: list[TrafficDensity] = []
        for row in rows:
            score = round(float(row["total_vehicles"]) / max_vehicles, 4)
            tags: list[str] = []
            if score > 0.8:
                tags.append("high-traffic")
            elif score > 0.4:
                tags.append("medium-traffic")
            else:
                tags.append("low-traffic")

            densities.append(
                TrafficDensity(
                    location=row["location"] or "Unknown",
                    city=row["city"] or "Unknown",
                    latitude=float(row["latitude"]) if row["latitude"] else 0.0,
                    longitude=float(row["longitude"]) if row["longitude"] else 0.0,
                    vehicle_count=int(row["total_vehicles"]),
                    density_score=score,
                    peak_hour=int(row["peak_hour"]) if row["peak_hour"] is not None else 0,
                    tags=tags,
                )
            )
        logger.info("Circuli calculated density for %d locations", len(densities))
        return densities

    def to_geojson(self, days: int = 7) -> dict:
        """Return traffic data as a GeoJSON FeatureCollection."""
        rows = self.get_traffic_by_location(days)
        features = []
        for row in rows:
            lat = float(row["latitude"]) if row["latitude"] else 0.0
            lng = float(row["longitude"]) if row["longitude"] else 0.0
            if lat == 0.0 and lng == 0.0:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lng, lat],
                    },
                    "properties": {
                        "location": row["location"],
                        "city": row["city"],
                        "region": row["region"],
                        "country": row["country"],
                        "total_vehicles": int(row["total_vehicles"]),
                    },
                }
            )
        return {
            "type": "FeatureCollection",
            "features": features,
        }
