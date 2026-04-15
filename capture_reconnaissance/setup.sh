#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Circuli"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "   $APP_NAME - Capture & Reconnaissance"
echo "   Setup Script"
echo "============================================"
echo ""

# Create virtual environment
echo "[${APP_NAME}] Creating virtual environment..."
python3 -m venv "${SCRIPT_DIR}/venv"
source "${SCRIPT_DIR}/venv/bin/activate"

# Install requirements
echo "[${APP_NAME}] Installing Python dependencies..."
pip install --upgrade pip
pip install -r "${SCRIPT_DIR}/requirements.txt"

# Download YOLOv8s model
echo "[${APP_NAME}] Downloading YOLOv8s model..."
python3 -c "from ultralytics import YOLO; YOLO('yolov8s.pt')"

# Validate youtube_streams.json
echo "[${APP_NAME}] Validating youtube_streams.json..."
CONFIG_FILE="${SCRIPT_DIR}/config/youtube_streams.json"
if [ -f "$CONFIG_FILE" ]; then
    python3 -c "
import json, sys
with open('${CONFIG_FILE}') as f:
    data = json.load(f)
streams = [s for s in data.get('streams', []) if s.get('enabled')]
print(f'[${APP_NAME}] Config valid: {len(streams)} enabled streams found')
"
else
    echo "[${APP_NAME}] WARNING: youtube_streams.json not found at ${CONFIG_FILE}"
    exit 1
fi

echo ""
echo "============================================"
echo "   ${APP_NAME} setup completed successfully!"
echo "============================================"
echo ""
echo "To activate the environment:"
echo "  source ${SCRIPT_DIR}/venv/bin/activate"
echo ""
echo "To start the capture pipeline:"
echo "  python -m src.video_capture"
echo ""
