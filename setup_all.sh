#!/usr/bin/env bash
# ==============================================================
# Parki — Full Stack Setup Script (Ubuntu)
# ==============================================================
# Sets up both the capture_reconnaissance and bi_analytics
# modules with their dependencies and configuration.
#
# Usage:  bash setup_all.sh
# ==============================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
header(){ echo -e "\n${BLUE}=== $* ===${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

header "Parki — Full Stack Setup"

# ---------------------------------------------------------------
# 1. System dependencies
# ---------------------------------------------------------------
header "1/5 — System Dependencies"
if command -v apt-get &>/dev/null; then
    info "Checking system packages …"
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        python3 python3-pip python3-venv \
        docker.io docker-compose \
        mysql-client \
        curl wget git 2>/dev/null || true
    info "System packages installed."
else
    warn "apt-get not found — skipping system package installation."
    warn "Please install Python 3.9+, Docker, and MySQL client manually."
fi

# ---------------------------------------------------------------
# 2. Capture Reconnaissance setup
# ---------------------------------------------------------------
header "2/5 — Capture Reconnaissance Module"
if [ -f "${SCRIPT_DIR}/capture_reconnaissance/setup.sh" ]; then
    cd "${SCRIPT_DIR}/capture_reconnaissance"
    bash setup.sh
    cd "${SCRIPT_DIR}"
else
    error "capture_reconnaissance/setup.sh not found!"
fi

# ---------------------------------------------------------------
# 3. BI Analytics setup
# ---------------------------------------------------------------
header "3/5 — BI Analytics Module"
if [ -f "${SCRIPT_DIR}/bi_analytics/setup.sh" ]; then
    cd "${SCRIPT_DIR}/bi_analytics"
    bash setup.sh
    cd "${SCRIPT_DIR}"
else
    error "bi_analytics/setup.sh not found!"
fi

# ---------------------------------------------------------------
# 4. Docker setup
# ---------------------------------------------------------------
header "4/5 — Docker Stack"
if command -v docker &>/dev/null; then
    info "Docker found: $(docker --version)"
    if [ -f "${SCRIPT_DIR}/docker-compose.yml" ]; then
        info "Building Docker images …"
        docker compose -f "${SCRIPT_DIR}/docker-compose.yml" build --quiet 2>/dev/null \
            && info "Docker images built." \
            || warn "Docker build failed — you can try again later with 'docker compose build'."
    fi
else
    warn "Docker not installed — skipping Docker setup."
    warn "Install Docker: https://docs.docker.com/engine/install/ubuntu/"
fi

# ---------------------------------------------------------------
# 5. Root .env
# ---------------------------------------------------------------
header "5/5 — Configuration"
if [ ! -f "${SCRIPT_DIR}/.env" ]; then
    cat > "${SCRIPT_DIR}/.env" <<'EOF'
# Parki Global Configuration
MYSQL_ROOT_PASSWORD=root_secret
MYSQL_PASSWORD=parki_secret
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
EOF
    info "Created root .env file (edit with your production values)."
else
    info "Root .env already exists."
fi

# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------
echo ""
echo -e "${GREEN}=========================================="
echo " Parki — Setup Complete!"
echo "==========================================${NC}"
echo ""
echo " Start the full stack with Docker:"
echo "   docker compose up -d"
echo ""
echo " Or run modules individually:"
echo ""
echo "   Capture:"
echo "     cd capture_reconnaissance"
echo "     source .venv/bin/activate"
echo "     python -m src.main --cameras-config config/cameras.yaml"
echo ""
echo "   BI API:"
echo "     cd bi_analytics"
echo "     source venv/bin/activate"
echo "     uvicorn src.api:app --reload"
echo ""
echo " Access services:"
echo "   Grafana:     http://localhost:3000  (admin/admin)"
echo "   Airflow:     http://localhost:8080  (admin/admin)"
echo "   BI API:      http://localhost:8000/docs"
echo ""
