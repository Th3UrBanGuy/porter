#!/usr/bin/env bash
# ============================================================================
# Porter — VPS Setup
# Installs everything, creates a systemd service, starts on boot.
#
# Usage:
#   bash setup.sh
#
# Env vars:
#   PORT=8080 bash setup.sh
#   DOMAIN=example.com SUBDOMAIN=tunnel bash setup.sh
# ============================================================================
set -euo pipefail

PORT="${PORT:-7262}"
SERVICE_NAME="porter"
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"

# Validate PORT
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "ERROR: Invalid PORT '$PORT', using 7262"
    PORT=7262
fi

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

ok()   { printf "  ${GREEN}✔${RESET} %s\n" "$1"; }
err()  { printf "  ${RED}✘${RESET} %s\n" "$1" >&2; }
warn() { printf "  ${YELLOW}⚠${RESET} %s\n" "$1"; }
info() { printf "  ${CYAN}→${RESET} %s\n" "$1"; }

# ── Detect package manager ──────────────────────────────────
pkg_install() {
    for mgr in apt dnf yum pacman; do
        if command -v "$mgr" &>/dev/null; then
            case "$mgr" in
                apt)    sudo apt-get update -qq && sudo apt-get install -y -qq "$@" ;;
                dnf)    sudo dnf install -y -q "$@" ;;
                yum)    sudo yum install -y -q "$@" ;;
                pacman) sudo pacman -S --noconfirm --needed "$@" ;;
            esac
            return
        fi
    done
    err "No supported package manager found (apt/dnf/yum/pacman)"
    return 1
}

# ── Detect arch ─────────────────────────────────────────────
detect_arch() {
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64|amd64)   echo "amd64" ;;
        aarch64|arm64)   echo "arm64" ;;
        armv7*|armhf)    echo "arm" ;;
        *)               echo "amd64" ;;
    esac
}

# ── Install system deps ─────────────────────────────────────
install_system_deps() {
    info "Installing system dependencies..."
    pkg_install python3 python3-pip python3-venv curl
    ok "System dependencies installed"
}

# ── Install cloudflared ─────────────────────────────────────
install_cloudflared() {
    if command -v cloudflared &>/dev/null; then
        ok "cloudflared already installed ($(cloudflared --version 2>&1 | head -1))"
        return
    fi

    info "Installing cloudflared..."
    local arch
    arch="$(detect_arch)"
    local url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}"

    curl -fsSL "$url" -o /tmp/cloudflared
    sudo install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared
    rm -f /tmp/cloudflared

    ok "cloudflared installed"
}

# ── Install Python deps ─────────────────────────────────────
install_python_deps() {
    info "Installing Python dependencies..."
    cd "$INSTALL_DIR"

    # Use venv if system packages are protected (PEP 668)
    if python3 -m pip install --dry-run nonexistent-pkg 2>&1 | grep -qi "break-system-packages"; then
        info "Creating virtual environment..."
        python3 -m venv "$INSTALL_DIR/.venv"
        source "$INSTALL_DIR/.venv/bin/activate"
        pip install --upgrade pip -q
        pip install -r requirements.txt -q
        ok "Dependencies installed (venv)"
    else
        python3 -m pip install -r requirements.txt -q --break-system-packages 2>/dev/null || \
        python3 -m pip install -r requirements.txt -q || true
        ok "Dependencies installed"
    fi
}

# ── Determine python/pip commands ───────────────────────────
get_python_cmd() {
    if [ -f "$INSTALL_DIR/.venv/bin/python" ]; then
        echo "$INSTALL_DIR/.venv/bin/python"
    else
        echo "python3"
    fi
}

get_gunicorn_cmd() {
    if [ -f "$INSTALL_DIR/.venv/bin/gunicorn" ]; then
        echo "$INSTALL_DIR/.venv/bin/gunicorn"
    else
        echo "gunicorn"
    fi
}

# ── Detect systemd ──────────────────────────────────────────
has_systemd() {
    command -v systemctl &>/dev/null && [ "$(ps -p 1 -o comm= 2>/dev/null)" = "systemd" ]
}

# ── Create systemd service ──────────────────────────────────
create_service() {
    if ! has_systemd; then
        warn "systemd not available (container / non-systemd init), skipping service"
        return 1
    fi

    info "Creating systemd service..."

    local python_cmd
    python_cmd="$(get_python_cmd)"
    local gunicorn_cmd
    gunicorn_cmd="$(get_gunicorn_cmd)"

    sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=Porter - Cloudflare Tunnel Portal
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
Environment=PORT=${PORT}
ExecStartPre=/bin/bash -c '! ss -tlnp sport = :${PORT} | grep -q LISTEN'
ExecStart=${gunicorn_cmd} \\
    --bind 0.0.0.0:${PORT} \\
    --workers 2 \\
    --worker-class gevent \\
    --worker-connections 1000 \\
    --timeout 120 \\
    --keep-alive 5 \\
    --log-level info \\
    --access-logfile - \\
    --error-logfile - \\
    --preload \\
    app:app
KillSignal=SIGTERM
TimeoutStopSec=10
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=porter

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable ${SERVICE_NAME}
    ok "Systemd service created and enabled"
}

# ── Start service ────────────────────────────────────────────
start_service() {
    info "Starting Porter on port ${PORT}..."

    # Kill anything on the port
    local existing_pid
    existing_pid=$(lsof -ti:"$PORT" 2>/dev/null || true)
    if [ -n "${existing_pid:-}" ]; then
        warn "Port ${PORT} in use (PID ${existing_pid}), killing..."
        sudo kill "$existing_pid" 2>/dev/null || true
        sleep 1
    fi

    local python_cmd
    python_cmd="$(get_python_cmd)"
    local gunicorn_cmd
    gunicorn_cmd="$(get_gunicorn_cmd)"

    if has_systemd; then
        sudo systemctl start ${SERVICE_NAME}

        # Wait for port
        local waited=0
        while [ $waited -lt 20 ]; do
            sleep 1
            waited=$((waited + 1))
            if curl -sf "http://localhost:${PORT}/api/status" > /dev/null 2>&1; then
                ok "Porter is running at http://localhost:${PORT}"
                return
            fi
        done
        warn "Service started but port not responding yet. Check: journalctl -u porter -f"
    else
        # No systemd — run directly with nohup
        cd "${INSTALL_DIR}"
        nohup ${gunicorn_cmd} \
            --bind "0.0.0.0:${PORT}" \
            --workers 2 \
            --worker-class gevent \
            --worker-connections 1000 \
            --timeout 120 \
            --keep-alive 5 \
            --log-level info \
            --access-logfile - \
            --error-logfile - \
            --preload \
            app:app >> "${INSTALL_DIR}/portal.log" 2>&1 &

        local server_pid=$!
        info "Server PID: ${server_pid}"

        # Wait for port
        local waited=0
        while [ $waited -lt 20 ]; do
            sleep 1
            waited=$((waited + 1))
            if curl -sf "http://localhost:${PORT}/api/status" > /dev/null 2>&1; then
                ok "Porter is running at http://localhost:${PORT}"
                return
            fi
        done
        warn "Server may still be starting... check http://localhost:${PORT}"
    fi
}

# ── Main ─────────────────────────────────────────────────────
main() {
    echo
    printf "${BOLD}Porter VPS Setup${RESET}\n"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    install_system_deps
    install_cloudflared
    install_python_deps
    create_service
    start_service

    echo
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    printf "${BOLD}  Porter is running!${RESET}\n"
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    echo
    info "URL:      http://localhost:${PORT}"
    info "Setup:    http://localhost:${PORT}/setup"
    info "Port:     ${PORT}"
    echo
    if has_systemd; then
        info "Service:  sudo systemctl status ${SERVICE_NAME}"
        info "Logs:     sudo journalctl -u ${SERVICE_NAME} -f"
        info "Restart:  sudo systemctl restart ${SERVICE_NAME}"
        info "Stop:     sudo systemctl stop ${SERVICE_NAME}"
    else
        info "Logs:     tail -f ${INSTALL_DIR}/portal.log"
        info "Stop:     kill \$(lsof -ti:${PORT})"
    fi
    echo
}

main "$@"
