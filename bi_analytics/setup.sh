#!/usr/bin/env bash
# =============================================================
# Parki BI Analytics – Setup Script (Ubuntu)
# =============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
ENV_FILE="${SCRIPT_DIR}/.env"

echo "=========================================="
echo " Parki BI Analytics – Setup"
echo "=========================================="

# -----------------------------------------------------------
# 1. Create virtual environment
# -----------------------------------------------------------
echo ""
echo "[1/4] Creating Python virtual environment..."
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
    echo "      Virtual environment created at ${VENV_DIR}"
else
    echo "      Virtual environment already exists."
fi

# Activate
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# -----------------------------------------------------------
# 2. Install Python requirements
# -----------------------------------------------------------
echo ""
echo "[2/4] Installing Python requirements..."
pip install --quiet --upgrade pip
pip install --quiet -r "${SCRIPT_DIR}/requirements.txt"
echo "      Requirements installed."

# -----------------------------------------------------------
# 3. Initialise MySQL datamart schema
# -----------------------------------------------------------
echo ""
echo "[3/4] Initialising MySQL datamart schema..."

# Source .env if it exists
if [ -f "${ENV_FILE}" ]; then
    set -a
    # shellcheck disable=SC1090
    source "${ENV_FILE}"
    set +a
fi

MYSQL_HOST="${BI_MYSQL_HOST:-localhost}"
MYSQL_PORT="${BI_MYSQL_PORT:-3306}"
MYSQL_USER="${BI_MYSQL_USER:-parki}"
MYSQL_PASS="${BI_MYSQL_PASSWORD:-parki_secret}"

if command -v mysql &>/dev/null; then
    mysql -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" \
          -u "${MYSQL_USER}" -p"${MYSQL_PASS}" \
          < "${SCRIPT_DIR}/sql/star_schema.sql" \
        && echo "      Star schema initialised successfully." \
        || echo "      WARNING: Could not initialise schema (MySQL may not be running)."
else
    echo "      WARNING: mysql client not found. Skipping schema initialisation."
    echo "               Run sql/star_schema.sql manually or use docker-compose."
fi

# -----------------------------------------------------------
# 4. Verify Grafana datasource config
# -----------------------------------------------------------
echo ""
echo "[4/4] Verifying Grafana provisioning files..."
if [ -f "${SCRIPT_DIR}/grafana/datasources/mysql.yaml" ] && \
   [ -f "${SCRIPT_DIR}/grafana/provisioning/dashboards.yaml" ]; then
    echo "      Grafana provisioning files present."
else
    echo "      WARNING: Grafana provisioning files missing."
fi

# -----------------------------------------------------------
# Summary
# -----------------------------------------------------------
echo ""
echo "=========================================="
echo " Setup Complete"
echo "=========================================="
echo ""
echo " Virtual env : ${VENV_DIR}"
echo " Activate    : source ${VENV_DIR}/bin/activate"
echo ""
echo " Start API   : uvicorn src.api:app --reload"
echo " Start stack : docker-compose up -d"
echo ""
echo " Grafana     : http://localhost:${BI_GRAFANA_PORT:-3000}"
echo " API docs    : http://localhost:${BI_API_PORT:-8000}/docs"
echo "=========================================="
