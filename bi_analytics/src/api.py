"""
FastAPI REST API for the BI Analytics Module.

Exposes traffic data, recommendations, camera info, and map
generation endpoints.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .config import get_settings
from .database import DatamartConnection
from .datamart import DatamartManager
from .geo_analysis import CameraInfo, TrafficMapGenerator, TrafficPoint
from .recommendations import RecommendationEngine

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Pydantic response models
# ------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    database: Optional[str] = None
    host: Optional[str] = None
    timestamp: str


class TrafficSummary(BaseModel):
    total_cameras: int = 0
    total_vehicles: int = 0
    avg_speed: Optional[float] = None
    avg_congestion: Optional[float] = None
    last_updated: str = ""


class HourlyTraffic(BaseModel):
    hour: int
    total_vehicles: int
    avg_speed: Optional[float] = None


class VehicleTypeStats(BaseModel):
    type_name: str
    category: str
    total_vehicles: int
    avg_speed: Optional[float] = None


class CameraOut(BaseModel):
    camera_id: int
    camera_name: str
    status: str
    zone_name: Optional[str] = None
    road_name: Optional[str] = None
    total_vehicles: Optional[int] = None
    avg_speed: Optional[float] = None
    avg_congestion: Optional[float] = None


class RecommendationOut(BaseModel):
    type: str
    priority: str
    title: str
    description: str
    affected_cameras: list[int] = Field(default_factory=list)
    suggested_action: str = ""
    estimated_impact: str = ""


# ------------------------------------------------------------------
# Application factory
# ------------------------------------------------------------------


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title="Parki BI Analytics API",
        description="REST API for traffic analytics, recommendations, and map generation.",
        version="1.0.0",
    )

    # CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Shared resources attached to app state
    application.state.db = DatamartConnection()
    application.state.datamart = DatamartManager(application.state.db)
    application.state.recommendation_engine = RecommendationEngine()
    application.state.map_generator = TrafficMapGenerator()

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @application.get("/api/health", response_model=HealthResponse, tags=["Health"])
    async def health_check():
        """Return API and database health status."""
        try:
            info = application.state.db.health_check()
            return HealthResponse(**info)
        except Exception as exc:
            logger.error("Health-check error: %s", exc)
            return HealthResponse(
                status="unhealthy",
                timestamp=datetime.utcnow().isoformat(),
            )

    @application.get("/api/traffic/summary", response_model=TrafficSummary, tags=["Traffic"])
    async def traffic_summary():
        """Overall traffic summary across all cameras."""
        try:
            cameras = application.state.db.get_camera_comparison()
            if not cameras:
                return TrafficSummary(last_updated=datetime.utcnow().isoformat())

            total_vehicles = sum(int(c.get("total_vehicles", 0)) for c in cameras)
            speeds = [float(c["avg_speed"]) for c in cameras if c.get("avg_speed")]
            congestions = [float(c["avg_congestion"]) for c in cameras if c.get("avg_congestion")]

            return TrafficSummary(
                total_cameras=len(cameras),
                total_vehicles=total_vehicles,
                avg_speed=round(sum(speeds) / len(speeds), 2) if speeds else None,
                avg_congestion=round(sum(congestions) / len(congestions), 2) if congestions else None,
                last_updated=datetime.utcnow().isoformat(),
            )
        except Exception as exc:
            logger.error("Error fetching traffic summary: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @application.get("/api/traffic/camera/{camera_id}", tags=["Traffic"])
    async def camera_traffic(
        camera_id: int,
        start_date: date = Query(default=date(2024, 1, 1)),
        end_date: date = Query(default=date(2024, 12, 31)),
    ):
        """Traffic data for a specific camera in a date range."""
        try:
            hourly = application.state.db.get_hourly_traffic(camera_id, start_date, end_date)
            speed = application.state.db.get_speed_statistics(camera_id, start_date, end_date)
            peaks = application.state.db.get_peak_hours(camera_id)
            return {
                "camera_id": camera_id,
                "date_range": {"start": str(start_date), "end": str(end_date)},
                "hourly_traffic": hourly,
                "speed_statistics": speed,
                "peak_hours": peaks,
            }
        except Exception as exc:
            logger.error("Error fetching camera %d traffic: %s", camera_id, exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @application.get(
        "/api/traffic/hourly",
        response_model=list[HourlyTraffic],
        tags=["Traffic"],
    )
    async def hourly_traffic():
        """Hourly traffic breakdown across all cameras."""
        try:
            rows = application.state.datamart.aggregate_hourly_stats()
            return [
                HourlyTraffic(
                    hour=int(r["hour"]),
                    total_vehicles=int(r.get("total_vehicles", 0)),
                    avg_speed=float(r["avg_speed"]) if r.get("avg_speed") else None,
                )
                for r in rows
            ]
        except Exception as exc:
            logger.error("Error fetching hourly traffic: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @application.get(
        "/api/traffic/vehicle-types",
        response_model=list[VehicleTypeStats],
        tags=["Traffic"],
    )
    async def vehicle_types():
        """Vehicle type distribution across all cameras."""
        try:
            rows = application.state.datamart.aggregate_by_vehicle_type()
            return [
                VehicleTypeStats(
                    type_name=r["type_name"],
                    category=r["category"],
                    total_vehicles=int(r.get("total_vehicles", 0)),
                    avg_speed=float(r["avg_speed"]) if r.get("avg_speed") else None,
                )
                for r in rows
            ]
        except Exception as exc:
            logger.error("Error fetching vehicle types: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @application.get(
        "/api/recommendations",
        response_model=list[RecommendationOut],
        tags=["Recommendations"],
    )
    async def get_recommendations():
        """Generate intelligent traffic recommendations."""
        try:
            camera_data = application.state.db.get_camera_comparison()
            engine = application.state.recommendation_engine
            recs = engine.generate_recommendations(
                congestion_data=camera_data,
                speed_data=camera_data,
                vehicle_data=None,
            )
            return [
                RecommendationOut(
                    type=r.type.value,
                    priority=r.priority.value,
                    title=r.title,
                    description=r.description,
                    affected_cameras=r.affected_cameras,
                    suggested_action=r.suggested_action,
                    estimated_impact=r.estimated_impact,
                )
                for r in recs
            ]
        except Exception as exc:
            logger.error("Error generating recommendations: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @application.get("/api/maps/traffic", response_class=HTMLResponse, tags=["Maps"])
    async def traffic_map():
        """Generate and return the traffic map as HTML."""
        try:
            camera_rows = application.state.db.get_camera_comparison()

            cameras: list[CameraInfo] = []
            traffic_points: list[TrafficPoint] = []
            for row in camera_rows:
                lat = float(row["latitude"]) if row.get("latitude") else None
                lng = float(row["longitude"]) if row.get("longitude") else None
                if lat is None or lng is None:
                    continue
                cameras.append(CameraInfo(
                    camera_id=int(row["camera_id"]),
                    name=row.get("camera_name", ""),
                    latitude=lat,
                    longitude=lng,
                    status=row.get("status", "active"),
                    vehicle_count=int(row.get("total_vehicles", 0)),
                    avg_speed=float(row.get("avg_speed", 0)),
                ))
                traffic_points.append(TrafficPoint(lat, lng, float(row.get("total_vehicles", 1))))

            gen = TrafficMapGenerator()
            gen.generate_traffic_report_map(cameras=cameras, traffic=traffic_points)
            html = gen.map._repr_html_()
            return HTMLResponse(content=html)
        except Exception as exc:
            logger.error("Error generating traffic map: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    @application.get(
        "/api/cameras",
        response_model=list[CameraOut],
        tags=["Cameras"],
    )
    async def list_cameras():
        """List all cameras with current status and statistics."""
        try:
            rows = application.state.db.get_camera_comparison()
            return [
                CameraOut(
                    camera_id=int(r["camera_id"]),
                    camera_name=r.get("camera_name", ""),
                    status=r.get("status", "unknown"),
                    zone_name=r.get("zone_name"),
                    road_name=r.get("road_name"),
                    total_vehicles=int(r["total_vehicles"]) if r.get("total_vehicles") else None,
                    avg_speed=float(r["avg_speed"]) if r.get("avg_speed") else None,
                    avg_congestion=float(r["avg_congestion"]) if r.get("avg_congestion") else None,
                )
                for r in rows
            ]
        except Exception as exc:
            logger.error("Error listing cameras: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc))

    return application


# Module-level app instance used by ``uvicorn src.api:app``
app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.api:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.debug,
    )
