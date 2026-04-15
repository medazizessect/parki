#!/bin/bash
set -euo pipefail

# ─────────────────────────────────────────────
# Circuli — Master Setup Script
# ─────────────────────────────────────────────

BLUE='\033[1;34m'
GREEN='\033[1;32m'
RED='\033[1;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Colour

banner() {
cat << 'EOF'

   _____ _                  _ _
  / ____(_)                | (_)
 | |     _ _ __ ___ _   _| |_
 | |    | | '__/ __| | | | | |
 | |____| | | | (__| |_| | | |
  \_____|_|_|  \___|\__,_|_|_|

  Smart Traffic & Parking Analytics
  ──────────────────────────────────

EOF
}

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Pre-flight checks ──────────────────────

check_dependency() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 is not installed. Please install $1 and try again."
        exit 1
    fi
    log_ok "$1 found: $(command -v "$1")"
}

preflight() {
    log_info "Running pre-flight checks …"
    check_dependency docker

    if command -v docker-compose &> /dev/null; then
        log_ok "docker-compose found (standalone)"
        COMPOSE_CMD="docker-compose"
    elif docker compose version &> /dev/null; then
        log_ok "docker compose found (plugin)"
        COMPOSE_CMD="docker compose"
    else
        log_error "Neither docker-compose nor 'docker compose' plugin found."
        exit 1
    fi
}

# ── Directory scaffolding ───────────────────

create_directories() {
    log_info "Creating project directories …"

    local dirs=(
        "capture_reconnaissance/dags"
        "capture_reconnaissance/scripts"
        "capture_reconnaissance/config"
        "bi_analytics/app"
        "bi_analytics/grafana/provisioning/dashboards"
        "bi_analytics/grafana/provisioning/datasources"
        "static"
        "data"
        "logs"
    )

    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
        log_ok "  $dir/"
    done
}

# ── Module setup ────────────────────────────

setup_capture_reconnaissance() {
    log_info "Setting up capture_reconnaissance module …"

    if [ -f "capture_reconnaissance/setup.sh" ]; then
        log_info "Running capture_reconnaissance/setup.sh …"
        bash capture_reconnaissance/setup.sh
        log_ok "capture_reconnaissance setup complete."
    else
        log_warn "No capture_reconnaissance/setup.sh found — skipping module-level setup."
    fi
}

setup_bi_analytics() {
    log_info "Setting up bi_analytics module …"

    if [ -f "bi_analytics/setup.sh" ]; then
        log_info "Running bi_analytics/setup.sh …"
        bash bi_analytics/setup.sh
        log_ok "bi_analytics setup complete."
    else
        log_warn "No bi_analytics/setup.sh found — skipping module-level setup."
    fi
}

# ── Docker Compose launch ──────────────────

launch_services() {
    if [ ! -f "docker-compose.yml" ] && [ ! -f "docker-compose.yaml" ] && [ ! -f "compose.yml" ] && [ ! -f "compose.yaml" ]; then
        log_warn "No docker-compose file found in project root — skipping service launch."
        return
    fi

    log_info "Building and starting services with ${COMPOSE_CMD} …"
    ${COMPOSE_CMD} up -d --build

    log_ok "All services started."
}

# ── Summary ─────────────────────────────────

print_summary() {
    echo ""
    echo -e "${GREEN}══════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Circuli is ready!${NC}"
    echo -e "${GREEN}══════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${BLUE}Apache Airflow${NC}  → http://localhost:8080  (airflow / airflow)"
    echo -e "  ${BLUE}Grafana${NC}         → http://localhost:3000  (admin / circuli)"
    echo -e "  ${BLUE}FastAPI Docs${NC}    → http://localhost:8000/docs"
    echo ""
    echo -e "  Logs:  ${COMPOSE_CMD} logs -f"
    echo -e "  Stop:  ${COMPOSE_CMD} down"
    echo ""
}

# ── Main ────────────────────────────────────

main() {
    banner
    preflight
    create_directories
    setup_capture_reconnaissance
    setup_bi_analytics
    launch_services
    print_summary
}

main "$@"
