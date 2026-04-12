# Parki — Intelligent Traffic Monitoring & Analytics

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://python.org)
[![MySQL 8.0](https://img.shields.io/badge/mysql-8.0-blue.svg)](https://mysql.com)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A production-ready, multi-camera vehicle detection and traffic analytics platform.  
Parki captures live RTSP video streams, detects and classifies vehicles with **YOLOv8s**, orchestrates ETL pipelines with **Apache Airflow**, and delivers real-time insights through **Grafana** dashboards, **Folium** geographic maps, and an intelligent recommendation engine.

---

## Architecture

```
parki/
├── capture_reconnaissance/     # 📹 Video capture & vehicle recognition
│   ├── src/                    #    Python source modules
│   │   ├── config.py           #    Configuration management
│   │   ├── video_capture.py    #    Multi-camera RTSP stream handler
│   │   ├── yolo_detector.py    #    YOLOv8s vehicle detection
│   │   ├── vehicle_tracker.py  #    Centroid tracker & traffic metrics
│   │   ├── data_handler.py     #    MySQL event storage
│   │   └── main.py             #    Pipeline entry point
│   ├── airflow_dags/           #    Airflow DAG definitions
│   │   ├── capture_dag.py      #    Camera health + detection pipeline
│   │   └── etl_dag.py          #    Hourly ETL to datamart
│   ├── sql/schema.sql          #    MySQL schema (raw events)
│   ├── config/cameras.yaml     #    Camera definitions
│   ├── docker-compose.yml      #    Module-level Docker stack
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── setup.sh
│
├── bi_analytics/               # 📊 Business Intelligence & Analytics
│   ├── src/                    #    Python source modules
│   │   ├── config.py           #    BI configuration management
│   │   ├── database.py         #    MySQL datamart connection & queries
│   │   ├── datamart.py         #    Star schema management
│   │   ├── geo_analysis.py     #    Folium geographic maps
│   │   ├── recommendations.py  #    Intelligent recommendation engine
│   │   └── api.py              #    FastAPI REST API
│   ├── grafana/                #    Grafana provisioning
│   │   ├── dashboards/         #    JSON dashboard definitions
│   │   ├── datasources/        #    MySQL datasource config
│   │   └── provisioning/       #    Auto-provisioning config
│   ├── sql/star_schema.sql     #    Star schema DDL + seed data
│   ├── config/config.yaml      #    BI configuration
│   ├── docker-compose.yml      #    Module-level Docker stack
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── setup.sh
│
├── docker-compose.yml          # 🐳 Global Docker orchestration
├── setup_all.sh                # 🚀 Full stack setup script
├── .gitignore
└── README.md
```

---

## Key Features

### Capture & Reconnaissance
- **Multi-camera RTSP streaming** — manage 5–10 simultaneous camera feeds with automatic reconnection and health monitoring
- **YOLOv8s vehicle detection** — real-time detection of cars, motorcycles, buses, trucks, and bicycles
- **Centroid-based tracking** — track vehicles across frames with speed estimation and direction inference
- **MySQL event storage** — batch inserts with connection pooling and auto-reconnect
- **Apache Airflow orchestration** — scheduled pipelines for capture, detection, ETL, and data cleanup

### BI & Analytics
- **Grafana dashboards** — real-time traffic overview with vehicle counts, speed gauges, type distribution, and camera comparison
- **Folium geographic maps** — interactive maps with camera markers, traffic heatmaps, and route overlays
- **Intelligent recommendations** — congestion analysis, speed anomaly detection, vehicle restriction suggestions, and infrastructure improvement recommendations
- **Star schema datamart** — dimensional model with time, vehicle type, camera, and location dimensions
- **FastAPI REST API** — 8 endpoints for traffic data, recommendations, maps, and camera status

---

## Quick Start

### Option 1: Docker (Recommended)

```bash
git clone https://github.com/medazizessect/parki.git
cd parki

# Start the full stack
docker compose up -d

# Access services:
#   Grafana:  http://localhost:3000  (admin/admin)
#   Airflow:  http://localhost:8080  (admin/admin)
#   BI API:   http://localhost:8000/docs
```

### Option 2: Manual Setup (Ubuntu)

```bash
git clone https://github.com/medazizessect/parki.git
cd parki

# Run the full setup script
chmod +x setup_all.sh
bash setup_all.sh
```

### Option 3: Module-by-Module

#### Capture Reconnaissance
```bash
cd capture_reconnaissance
cp .env.example .env        # Edit with your settings
bash setup.sh

# Run the pipeline
source .venv/bin/activate
python -m src.main --cameras-config config/cameras.yaml
```

#### BI Analytics
```bash
cd bi_analytics
cp .env.example .env        # Edit with your settings
bash setup.sh

# Start the API
source venv/bin/activate
uvicorn src.api:app --reload --host 0.0.0.0 --port 8000
```

---

## Configuration

### Camera Configuration (`capture_reconnaissance/config/cameras.yaml`)

```yaml
cameras:
  - id: cam_01
    name: "Main Entrance"
    rtsp_url: "rtsp://admin:password@192.168.1.101:554/stream1"
    latitude: -23.5613
    longitude: -46.6560
    location: "Main entrance"
```

### Environment Variables

Copy `.env.example` to `.env` in each module and update with your values:

| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_HOST` | MySQL server host | `localhost` |
| `MYSQL_PASSWORD` | MySQL password | `parki_secret` |
| `YOLO_MODEL_PATH` | Path to YOLOv8 weights | `yolov8s.pt` |
| `YOLO_DEVICE` | Inference device (cpu/cuda) | `cpu` |
| `CAMERA_RTSP_URLS` | Comma-separated RTSP URLs | — |

---

## Database Schema

### Capture Database (`parki_capture`)
- `cameras` — registered camera devices with GPS coordinates
- `traffic_events` — individual vehicle detections with type, speed, direction
- `camera_health` — periodic health check results

### BI Datamart (`parki_datamart`) — Star Schema
- **Dimensions:** `dim_time`, `dim_vehicle_type`, `dim_camera`, `dim_location`
- **Fact:** `fact_traffic_events` (vehicle_count, avg/max/min speed, congestion_level)

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/traffic/summary` | Overall traffic summary |
| GET | `/api/traffic/camera/{id}` | Traffic data for specific camera |
| GET | `/api/traffic/hourly` | Hourly traffic breakdown |
| GET | `/api/traffic/vehicle-types` | Vehicle type distribution |
| GET | `/api/recommendations` | Intelligent recommendations |
| GET | `/api/maps/traffic` | Interactive traffic map (HTML) |
| GET | `/api/cameras` | List all cameras with status |

---

## Tech Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Vehicle Detection | YOLOv8s (Ultralytics) | 8.1.0 |
| Video Capture | OpenCV | 4.9.0 |
| ETL Orchestration | Apache Airflow | 2.8.x |
| Database | MySQL | 8.0 |
| Dashboards | Grafana | Latest |
| Geographic Maps | Folium | 0.15.1 |
| REST API | FastAPI | 0.109.0 |
| Runtime | Python | 3.9+ |
| Containers | Docker & Docker Compose | — |

---

## Requirements

- **OS:** Ubuntu 20.04+ (or any Linux with Docker)
- **Python:** 3.9+
- **MySQL:** 8.0+
- **Docker:** 20.10+ (optional, recommended)
- **GPU:** NVIDIA GPU with CUDA (optional, for faster detection)

---

## License

This project is developed for traffic monitoring and urban planning research.