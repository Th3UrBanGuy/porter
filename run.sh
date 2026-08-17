#!/usr/bin/env bash
# Porter - Cloudflare Tunnel Portal
# Production launcher with gunicorn + gevent
#
# Usage:
#   ./run.sh              # Production mode (gunicorn)
#   ./run.sh dev          # Development mode (Flask dev server)
#   ./run.sh --protocol http2   # Force HTTP/2 protocol

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PORT="${PORT:-7262}"
WORKERS="${WORKERS:-2}"
PROTOCOL_FLAG=""

# Parse args
MODE="prod"
for arg in "$@"; do
    case "$arg" in
        dev|--dev) MODE="dev" ;;
        --protocol) PROTOCOL_FLAG="--protocol" ;;
        http2|quic|auto) PROTOCOL_FLAG_VAL="$arg" ;;
    esac
done

# Ensure dependencies
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
fi

echo "=========================================="
echo "  Porter - Tunnel Portal"
echo "  http://localhost:$PORT"
echo "=========================================="

if [ "$MODE" = "dev" ]; then
    echo "  Mode: Development"
    echo "  Protocol: auto (WSL2-aware)"
    echo "=========================================="
    exec python3 app.py
else
    echo "  Mode: Production (gunicorn + gevent)"
    echo "  Workers: $WORKERS"
    echo "  Protocol: auto (WSL2-aware)"
    echo "=========================================="
    exec gunicorn \
        --bind "0.0.0.0:$PORT" \
        --workers "$WORKERS" \
        --worker-class gevent \
        --worker-connections 1000 \
        --timeout 120 \
        --keep-alive 5 \
        --log-level info \
        --access-logfile - \
        --error-logfile - \
        --preload \
        app:app
fi
