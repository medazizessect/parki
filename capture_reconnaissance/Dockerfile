# ==============================================================
# Parki Capture Reconnaissance — Dockerfile
# ==============================================================
FROM python:3.9-slim

LABEL maintainer="parki-team" \
      description="Parki capture reconnaissance pipeline"

# System dependencies required by OpenCV and general tooling
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/parki

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ src/
COPY airflow_dags/ airflow_dags/
COPY config/ config/
COPY sql/ sql/

# Default command — run the capture pipeline
ENTRYPOINT ["python", "-m", "src.main"]
