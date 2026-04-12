#!/usr/bin/env bash
# ==============================================================
# Parki Capture Reconnaissance — Setup Script (Ubuntu)
# ==============================================================
# Usage:  bash setup.sh
# ==============================================================
set -euo pipefail

VENV_DIR=".venv"
YOLO_MODEL="yolov8s.pt"
YOLO_URL="https://github.com/ultralytics/assets/releases/download/v0.0.0/${YOLO_MODEL}"
SCHEMA_FILE="sql/schema.sql"

# ---- Colours ---------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ---- 1. Check Python 3.9+ -------------------------------------
info "Checking Python version …"
PYTHON=""
for candidate in python3.11 python3.10 python3.9 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    error "Python 3.9+ is required but not found."
    error "Install it with:  sudo apt install python3.9 python3.9-venv"
    exit 1
fi
info "Using $PYTHON ($($PYTHON --version))"

# ---- 2. Create virtual environment ----------------------------
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment in ${VENV_DIR} …"
    $PYTHON -m venv "$VENV_DIR"
else
    info "Virtual environment already exists."
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# ---- 3. Install requirements ----------------------------------
info "Installing Python dependencies …"
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

# ---- 4. Download YOLOv8s model --------------------------------
if [ ! -f "$YOLO_MODEL" ]; then
    info "Downloading YOLOv8s model …"
    curl -fSL -o "$YOLO_MODEL" "$YOLO_URL"
else
    info "YOLOv8s model already present."
fi

# ---- 5. Initialise MySQL schema (optional) --------------------
if command -v mysql &>/dev/null; then
    info "MySQL client found — attempting schema initialisation …"
    if [ -f "$SCHEMA_FILE" ]; then
        MYSQL_HOST="${MYSQL_HOST:-localhost}"
        MYSQL_PORT="${MYSQL_PORT:-3306}"
        MYSQL_USER="${MYSQL_USER:-parki}"
        # Prompt only if MYSQL_PASSWORD is not already set
        if [ -z "${MYSQL_PASSWORD:-}" ]; then
            read -rsp "Enter MySQL password for user '${MYSQL_USER}': " MYSQL_PASSWORD
            echo
        fi
        mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" < "$SCHEMA_FILE" \
            && info "Schema initialised." \
            || warn "Schema initialisation failed — you can run it manually later."
    else
        warn "Schema file not found at ${SCHEMA_FILE}."
    fi
else
    warn "MySQL client not installed — skipping schema initialisation."
    warn "Run the schema manually:  mysql -u parki -p < ${SCHEMA_FILE}"
fi

# ---- 6. Copy .env.example → .env if needed --------------------
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    info "Copied .env.example → .env (edit it with your real values)."
fi

# ---- Summary ---------------------------------------------------
echo ""
info "============================================"
info "  Parki Capture Reconnaissance — Setup Done"
info "============================================"
info "  Python:       $($PYTHON --version)"
info "  Virtualenv:   ${VENV_DIR}"
info "  YOLO model:   ${YOLO_MODEL}"
info "  Config:       config/cameras.yaml"
info "  Schema:       ${SCHEMA_FILE}"
info ""
info "  Activate venv:   source ${VENV_DIR}/bin/activate"
info "  Run pipeline:    python -m src.main --cameras-config config/cameras.yaml"
info "  Docker:          docker compose up -d"
info "============================================"
