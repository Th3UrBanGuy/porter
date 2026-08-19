#!/usr/bin/env bash
# ============================================================================
# Porter — VPS Setup
# Installs everything, creates a systemd service, starts on boot.
#
# Usage:
#   bash setup.sh
# ============================================================================

PORT=7262
SERVICE_NAME="porter"
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

ok()   { printf "  ${GREEN}✔${RESET} %s\n" "$1"; }
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
            return 0
        fi
    done
    warn "No supported package manager found, skipping system deps"
    return 0
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
    info "System dependencies..."
    pkg_install python3 python3-pip python3-venv curl || true
    ok "System dependencies"
}

# ── Install cloudflared ─────────────────────────────────────
install_cloudflared() {
    if command -v cloudflared &>/dev/null; then
        ok "cloudflared"
        return 0
    fi

    info "Installing cloudflared..."
    local arch
    arch="$(detect_arch)"
    local url="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}"

    curl -fsSL "$url" -o /tmp/cloudflared 2>/dev/null || { warn "cloudflared download failed"; return 0; }
    sudo install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared 2>/dev/null || true
    rm -f /tmp/cloudflared
    ok "cloudflared installed"
}

# ── Install Python deps ─────────────────────────────────────
install_python_deps() {
    info "Python dependencies..."
    cd "$INSTALL_DIR" || return 0

    if python3 -m pip install --dry-run nonexistent-pkg 2>&1 | grep -qi "break-system-packages"; then
        python3 -m venv "$INSTALL_DIR/.venv" 2>/dev/null || true
        if [ -f "$INSTALL_DIR/.venv/bin/activate" ]; then
            source "$INSTALL_DIR/.venv/bin/activate"
            pip install --upgrade pip -q 2>/dev/null
            pip install -r requirements.txt -q 2>/dev/null || true
        fi
    else
        python3 -m pip install -r requirements.txt -q --break-system-packages 2>/dev/null || \
        python3 -m pip install -r requirements.txt -q 2>/dev/null || true
    fi
    ok "Python dependencies"
}

# ── Determine python/gunicorn commands ──────────────────────
get_python_cmd() {
    [ -f "$INSTALL_DIR/.venv/bin/python" ] && echo "$INSTALL_DIR/.venv/bin/python" && return
    echo "python3"
}

get_gunicorn_cmd() {
    [ -f "$INSTALL_DIR/.venv/bin/gunicorn" ] && echo "$INSTALL_DIR/.venv/bin/gunicorn" && return
    echo "gunicorn"
}

# ── Detect systemd ──────────────────────────────────────────
has_systemd() {
    command -v systemctl &>/dev/null && [ "$(ps -p 1 -o comm= 2>/dev/null)" = "systemd" ]
}

# ── Create systemd service ──────────────────────────────────
create_service() {
    if ! has_systemd; then
        return 0
    fi

    info "Creating systemd service..."

    local python_cmd gunicorn_cmd
    python_cmd="$(get_python_cmd)"
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
    sudo systemctl enable ${SERVICE_NAME} 2>/dev/null
    ok "Systemd service created"
}

# ── Start service ────────────────────────────────────────────
start_service() {
    # Kill anything on the port
    local existing_pid
    existing_pid=$(lsof -ti:"$PORT" 2>/dev/null || true)
    if [ -n "${existing_pid:-}" ]; then
        kill "$existing_pid" 2>/dev/null || true
        sleep 1
    fi

    local python_cmd gunicorn_cmd
    python_cmd="$(get_python_cmd)"
    gunicorn_cmd="$(get_gunicorn_cmd)"

    if has_systemd; then
        sudo systemctl start ${SERVICE_NAME}
        sleep 2
    else
        cd "${INSTALL_DIR}" || return 0
        nohup ${gunicorn_cmd} \
            --bind "0.0.0.0:${PORT}" \
            --workers 2 \
            --worker-class gevent \
            --worker-connections 1000 \
            --timeout 120 \
            --keep-alive 5 \
            --log-level warning \
            --error-logfile - \
            --preload \
            app:app > /dev/null 2>&1 &
        disown
        sleep 2
    fi

    # Verify server is up
    local waited=0
    while [ $waited -lt 15 ]; do
        if curl -sf "http://127.0.0.1:${PORT}/" > /dev/null 2>&1 || \
           curl -sf "http://0.0.0.0:${PORT}/" > /dev/null 2>&1; then
            ok "Server running on port ${PORT}"
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done

    # One more try — longer wait for slow systems
    sleep 3
    if curl -sf "http://127.0.0.1:${PORT}/" > /dev/null 2>&1; then
        ok "Server running on port ${PORT}"
        return 0
    fi

    warn "Server may still be starting..."
    return 0
}

# ── Start cloudflared quick tunnel ───────────────────────────
start_tunnel() {
    command -v cloudflared &>/dev/null || return 0

    # Kill existing tunnel
    local old_pid
    old_pid=$(cat "${INSTALL_DIR}/.tunnel.pid" 2>/dev/null || true)
    if [ -n "${old_pid:-}" ] && kill -0 "${old_pid}" 2>/dev/null; then
        kill "${old_pid}" 2>/dev/null || true
        sleep 1
    fi

    info "Opening public tunnel..."
    cloudflared tunnel --url "http://localhost:${PORT}" \
        > "${INSTALL_DIR}/.tunnel.log" 2>&1 &
    local tunnel_pid=$!
    echo "$tunnel_pid" > "${INSTALL_DIR}/.tunnel.pid"

    # Wait for URL
    local waited=0 tunnel_url=""
    while [ $waited -lt 15 ]; do
        sleep 1
        waited=$((waited + 1))
        tunnel_url=$(grep -oP 'https://[a-zA-Z0-9.-]+\.trycloudflare\.com' "${INSTALL_DIR}/.tunnel.log" 2>/dev/null | head -1)
        [ -n "$tunnel_url" ] && break
    done

    if [ -n "$tunnel_url" ]; then
        echo "$tunnel_url" > "${INSTALL_DIR}/.tunnel_url"
        ok "Public URL: ${tunnel_url}"
        ok "Dashboard:  ${tunnel_url}/setup"
    else
        warn "Tunnel started but URL not ready yet"
    fi
}

# ── Main ─────────────────────────────────────────────────────
main() {
    echo
    printf "${BOLD}Porter Setup${RESET}\n"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo

    install_system_deps
    install_cloudflared
    install_python_deps
    create_service
    start_service
    start_tunnel

    echo
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    printf "${BOLD}  Porter is running!${RESET}\n"
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    echo
    info "Local:   http://localhost:${PORT}"
    info "Setup:   http://localhost:${PORT}/setup"

    if [ -f "${INSTALL_DIR}/.tunnel_url" ]; then
        local public_url
        public_url=$(cat "${INSTALL_DIR}/.tunnel_url" 2>/dev/null || true)
        [ -n "${public_url:-}" ] && info "Public:  ${public_url}"
    fi
    echo

    if has_systemd; then
        info "Status:  sudo systemctl status ${SERVICE_NAME}"
        info "Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
        info "Stop:    sudo systemctl stop ${SERVICE_NAME}"
    else
        info "Logs:    tail -f ${INSTALL_DIR}/portal.log"
        info "Stop:    kill \$(lsof -ti:${PORT})"
    fi
    echo
}

main "$@"
