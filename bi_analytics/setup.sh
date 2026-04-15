#!/usr/bin/env bash
set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${BLUE}"
cat << 'EOF'
   _____ _                     _ _
  / ____(_)                   | (_)
 | |     _ _ __ ___ _   _ | |_
 | |    | | '__/ __| | | | | | |
 | |____| | | | (__| |_| | | | |
  \_____|_|_|  \___|\__,_|_|_|_|

  Circuli — BI & Analytics Setup
EOF
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "📥 Installing requirements..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "✅ Validating Grafana dashboards..."
for dashboard in grafana/dashboards/*.json; do
    if python3 -c "import json; json.load(open('$dashboard'))" 2>/dev/null; then
        echo "   ✓ $(basename "$dashboard")"
    else
        echo "   ✗ $(basename "$dashboard") — invalid JSON"
        exit 1
    fi
done

echo ""
echo -e "${GREEN}✅ Circuli BI & Analytics setup complete!${NC}"
echo ""
echo "To start the services:"
echo "  docker compose up -d"
echo ""
echo "To run the API locally:"
echo "  source venv/bin/activate"
echo "  uvicorn src.api:app --reload"
