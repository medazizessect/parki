# 🚗 Circuli - Smart Traffic & Parking Analytics

![Circuli Logo](static/logo_circuli.png)

**Circuli** is a real-time traffic monitoring and parking analytics platform. It captures live video streams, detects and classifies vehicles using AI-powered computer vision, and delivers actionable insights through interactive dashboards and a REST API.

---

## 📐 Architecture

Circuli is composed of two core modules:

| Module | Description |
|---|---|
| **`capture_reconnaissance`** | Video capture and AI-based vehicle detection. Uses yt-dlp to pull live YouTube streams and YOLOv8 for object detection, counting, and classification. Orchestrated with Apache Airflow. |
| **`bi_analytics`** | Business-intelligence dashboards and REST API. Serves detection results via a FastAPI backend and visualises trends in Grafana. |

```
┌─────────────────────────────────────────────────────┐
│                     Circuli                         │
│                                                     │
│  ┌───────────────────┐   ┌───────────────────────┐  │
│  │ capture_recon…    │   │ bi_analytics          │  │
│  │                   │   │                       │  │
│  │  yt-dlp → YOLOv8  │──▶│  FastAPI  ┃  Grafana  │  │
│  │  Airflow (DAGs)   │   │  PostgreSQL           │  │
│  └───────────────────┘   └───────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 🛠 Tech Stack

- **Python 3.11+** — core language
- **FastAPI** — REST API
- **Apache Airflow** — workflow orchestration
- **Grafana** — dashboards & visualisation
- **Docker / Docker Compose** — containerisation
- **YOLOv8 (Ultralytics)** — vehicle detection model
- **yt-dlp** — YouTube live-stream capture

---

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/<your-org>/parki.git
cd parki

# Run the master setup (creates dirs, builds images)
chmod +x setup_all.sh
./setup_all.sh

# — or launch manually —
docker-compose up -d --build
```

---

## 🌐 Access URLs

| Service | URL | Default Credentials |
|---|---|---|
| Apache Airflow | [http://localhost:8080](http://localhost:8080) | `airflow` / `airflow` |
| Grafana | [http://localhost:3000](http://localhost:3000) | `admin` / `circuli` |
| FastAPI (docs) | [http://localhost:8000/docs](http://localhost:8000/docs) | — |

---

## 📺 YouTube Streams

Circuli ships with **7 default configured live streams** covering a variety of traffic cameras and intersections around the world. Stream URLs are defined in the capture_reconnaissance configuration and can be customised to monitor any public YouTube live feed.

---

## 📁 Project Structure

```
parki/
├── capture_reconnaissance/   # Video capture & AI detection module
│   ├── dags/                 # Airflow DAG definitions
│   ├── scripts/              # Helper scripts (download, detect)
│   ├── config/               # Stream & model configuration
│   └── Dockerfile
├── bi_analytics/             # Dashboards & API module
│   ├── app/                  # FastAPI application
│   ├── grafana/              # Grafana provisioning & dashboards
│   └── Dockerfile
├── static/                   # Static assets (logo, images)
├── docker-compose.yml        # Root orchestration
├── setup_all.sh              # Master setup script
├── .gitignore
└── README.md
```

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.