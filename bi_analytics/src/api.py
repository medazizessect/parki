"""Circuli - FastAPI application for Smart Traffic & Parking Analytics."""

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __app_name__, __version__
from .database import DatabaseManager
from .datamart import DataMart
from .geo_analysis import GeoAnalyzer
from .recommendations import ParkingRecommender

logger = logging.getLogger("circuli.api")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# ---------------------------------------------------------------------------
# Database and domain objects (lazy-initialised)
# ---------------------------------------------------------------------------
db = DatabaseManager()
datamart = DataMart(db)
geo_analyzer = GeoAnalyzer(db)
recommender = ParkingRecommender(db)

YOUTUBE_STREAMS: list[dict] = [
    {
        "id": "default_stream_1",
        "name": "City Center Camera",
        "url": "https://www.youtube.com/watch?v=example1",
        "status": "active",
    },
    {
        "id": "default_stream_2",
        "name": "Highway Junction",
        "url": "https://www.youtube.com/watch?v=example2",
        "status": "active",
    },
]

BANNER = r"""
   _____ _                     _ _
  / ____(_)                   | (_)
 | |     _ _ __ ___ _   _ | |_
 | |    | | '__/ __| | | | | | |
 | |____| | | | (__| |_| | | | |
  \_____|_|_|  \___|\__,_|_|_|_|

  Circuli — Smart Traffic & Parking Analytics  v{}
""".format(
    __version__
)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info(BANNER)
    try:
        db.connect()
        logger.info("Circuli database connected")
    except Exception:
        logger.warning("Circuli could not connect to database – running without DB")
    yield
    db.disconnect()
    logger.info("Circuli shutdown complete")


app = FastAPI(
    title="Circuli API",
    description="Smart Traffic & Parking Analytics",
    version=__version__,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files & templates
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
async def index(request: Request):
    """Serve the main dashboard page."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": __app_name__,
            "version": __version__,
            "logo": "/static/logo_circuli.png",
        },
    )


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve the Circuli logo as favicon."""
    favicon_path = STATIC_DIR / "logo_circuli.png"
    if favicon_path.exists():
        return FileResponse(str(favicon_path), media_type="image/png")
    return JSONResponse(status_code=404, content={"detail": "favicon not found"})


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "app": __app_name__}


@app.get("/api/v1/detections")
async def get_detections(days: int = 7):
    """Return recent detection data."""
    try:
        summary = datamart.get_daily_summary(days)
        return {
            "app_name": __app_name__,
            "days": days,
            "data": summary,
        }
    except Exception as exc:
        logger.error("Circuli detections error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"app_name": __app_name__, "error": str(exc)},
        )


@app.get("/api/v1/analytics/traffic")
async def traffic_analytics(days: int = 7):
    """Return traffic analytics data."""
    try:
        volume = datamart.get_traffic_volume_by_hour(days)
        distribution = datamart.get_vehicle_type_distribution(days)
        density = geo_analyzer.calculate_traffic_density(days)
        geojson = geo_analyzer.to_geojson(days)
        return {
            "app_name": __app_name__,
            "days": days,
            "volume_by_hour": volume,
            "vehicle_distribution": distribution,
            "density": [asdict(d) for d in density],
            "geojson": geojson,
        }
    except Exception as exc:
        logger.error("Circuli traffic analytics error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"app_name": __app_name__, "error": str(exc)},
        )


@app.get("/api/v1/analytics/parking")
async def parking_analytics(days: int = 30, limit: int = 10):
    """Return parking analytics and recommendations."""
    try:
        occupancy = datamart.get_parking_occupancy()
        recommendations = recommender.recommend(days=days, limit=limit)
        return {
            "app_name": __app_name__,
            "occupancy": occupancy,
            "recommendations": [asdict(r) for r in recommendations],
        }
    except Exception as exc:
        logger.error("Circuli parking analytics error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"app_name": __app_name__, "error": str(exc)},
        )


@app.get("/api/v1/streams")
async def get_streams():
    """Return configured YouTube streams."""
    return {
        "app_name": __app_name__,
        "streams": YOUTUBE_STREAMS,
    }
