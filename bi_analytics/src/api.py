"""Circuli - FastAPI application for Smart Traffic & Parking Analytics."""

import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

import cv2
import yt_dlp
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ultralytics import YOLO

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

YOUTUBE_STREAMS_CONFIG_CANDIDATES = [
    BASE_DIR / "config" / "youtube_streams.json",
    BASE_DIR.parent / "capture_reconnaissance" / "config" / "youtube_streams.json",
]
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
_YOLO_MODEL: YOLO | None = None
_YOLO_LOCK = threading.Lock()


def _load_youtube_streams() -> list[dict]:
    """Load YouTube streams from configuration file."""
    try:
        for config_path in YOUTUBE_STREAMS_CONFIG_CANDIDATES:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return [{**s, "status": "active"} for s in data.get("streams", []) if s.get("enabled", False)]
    except Exception as exc:
        logger.warning("Could not load YouTube streams config: %s", exc)
    return []


def _resolve_stream_url(youtube_url: str) -> str:
    ydl_opts = {"format": "best[height<=720]", "quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
    stream_url = info.get("url", "")
    if not stream_url:
        raise RuntimeError("Empty stream URL returned by yt-dlp")
    return stream_url


def _get_yolo_model() -> YOLO:
    global _YOLO_MODEL
    if _YOLO_MODEL is None:
        _YOLO_MODEL = YOLO("yolov8n.pt")
    return _YOLO_MODEL


def _annotate_frame(frame):
    model = _get_yolo_model()
    with _YOLO_LOCK:
        results = model(frame, verbose=False)

    for result in results:
        boxes = result.boxes
        if boxes is None:
            continue
        for i in range(len(boxes)):
            class_id = int(boxes.cls[i].item())
            confidence = float(boxes.conf[i].item())
            if class_id not in VEHICLE_CLASSES:
                continue
            x1, y1, x2, y2 = [int(v) for v in boxes.xyxy[i].tolist()]
            label = f"{VEHICLE_CLASSES[class_id]} {confidence:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (41, 121, 255), 2)
            cv2.putText(
                frame,
                label,
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (41, 121, 255),
                2,
                cv2.LINE_AA,
            )
    return frame


async def _stream_generator(request: Request, stream: dict):
    cap = None
    try:
        direct_url = await asyncio.to_thread(_resolve_stream_url, stream["url"])
        cap = await asyncio.to_thread(cv2.VideoCapture, direct_url)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open stream {stream['id']}")

        while True:
            if await request.is_disconnected():
                break
            ret, frame = await asyncio.to_thread(cap.read)
            if not ret:
                await asyncio.sleep(0.1)
                continue
            frame = await asyncio.to_thread(_annotate_frame, frame)
            ok, jpeg = await asyncio.to_thread(cv2.imencode, ".jpg", frame)
            if not ok:
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            await asyncio.sleep(0)
    except Exception as exc:
        logger.error("Circuli stream %s failed: %s", stream.get("id"), exc)
    finally:
        if cap is not None:
            await asyncio.to_thread(cap.release)

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
            content={"app_name": __app_name__, "error": "Internal server error"},
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
            content={"app_name": __app_name__, "error": "Internal server error"},
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
            content={"app_name": __app_name__, "error": "Internal server error"},
        )


@app.get("/api/v1/streams")
async def get_streams():
    """Return configured YouTube streams."""
    streams = _load_youtube_streams()
    return {
        "app_name": __app_name__,
        "streams": streams,
    }


@app.get("/api/v1/stream/{stream_id}")
async def stream_video(stream_id: int, request: Request):
    """Stream live video with YOLOv8 overlays as MJPEG."""
    streams = _load_youtube_streams()
    stream = next((item for item in streams if int(item.get("id", -1)) == stream_id), None)
    if not stream:
        raise HTTPException(status_code=404, detail=f"stream {stream_id} not found")

    return StreamingResponse(
        _stream_generator(request, stream),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
