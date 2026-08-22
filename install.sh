#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════
#   P O R T E R  —  Universal Installer
#   One script · every platform · zero manual steps.
#
#     Linux (apt/dnf/pacman/apk/zypper) · macOS (brew) · Termux (pkg)
#     Windows: run inside WSL or Git Bash
#
#   One-liner:
#     curl -fsSL https://raw.githubusercontent.com/Th3UrBanGuy/porter/self-hosted/install.sh | bash
#
#   Flags:
#     --dir PATH       Install location          (default ~/.porter)
#     --port N         Server port               (default 7262)
#     --passcode XXX   Set portal passcode now   (else first-run wizard)
#     --service        Create auto-start service (systemd / launchd)
#     --no-service     Never ask about services
#     --no-start       Do not start the server after installing
#     --branch NAME    Source branch/tag         (default self-hosted)
#     --uninstall      Remove Porter completely
# ══════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── CRLF safety (curl through PowerShell mangles line endings) ─────────────
if [ -f "$0" ] && command -v sed >/dev/null 2>&1 && grep -q $'\r' "$0" 2>/dev/null; then
    tmpfile=$(mktemp); sed 's/\r$//' "$0" > "$tmpfile"; exec bash "$tmpfile" "$@"
fi

REPO="Th3UrBanGuy/porter"
DEFAULT_BRANCH="self-hosted"
BRANCH="$DEFAULT_BRANCH"
PORT=7262
PASSCODE=""
MAKE_SERVICE=""
NO_START=0
UNINSTALL=0
ASSUME_YES=0
[ -t 0 ] && ASSUME_YES=1

# ── Arg parsing ────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --dir)       INSTALL_DIR="$2"; shift 2 ;;
        --port)      PORT="$2"; shift 2 ;;
        --passcode)  PASSCODE="$2"; shift 2 ;;
        --service)   MAKE_SERVICE=1; shift ;;
        --no-service) MAKE_SERVICE=0; shift ;;
        --no-start)  NO_START=1; shift ;;
        --branch)    BRANCH="$2"; shift 2 ;;
        --uninstall) UNINSTALL=1; shift ;;
        -h|--help)   grep '^#\+' "$0" | head -24 | sed 's/^# \{0,2\}//'; exit 0 ;;
        *) echo "Unknown option: $1 (see --help)"; exit 1 ;;
    esac
done
INSTALL_DIR="${INSTALL_DIR:-${PORTER_DIR:-$HOME/.porter}}"
RAW_URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}"

# ── Presentation ───────────────────────────────────────────────────────────
if [ -t 1 ]; then
    R='\033[0m'; BOLD='\033[1m'; DIM='\033[2m'
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
    CYAN='\033[0;36m'; ORANGE='\033[0;33m'; WHITE='\033[1;37m'
else R=''; BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; CYAN=''; ORANGE=''; WHITE=''; fi

ok()   { printf "  ${GREEN}✔${R} %s\n" "$1"; }
warn() { printf "  ${YELLOW}⚠${R} %s\n" "$1"; }
fail() { printf "  ${RED}✘${R} %s\n" "$1"; exit 1; }
step() { printf "\n${BOLD}${WHITE}▸ %s${R}\n" "$1"; }

banner() {
    printf "${ORANGE}${BOLD}"
    printf '  ╔══════════════════════════════════════════╗\n'
    printf '  ║   P O R T E R   ·   C o n n e c t o r    ║\n'
    printf '  ╚══════════════════════════════════════════╝\n'
    printf "${R}  Cloudflare tunnels without the YAML — powered by your Connector Portal.\n\n"
}

# ── Platform detection ─────────────────────────────────────────────────────
detect_platform() {
    OS_NAME="$(uname -s)"
    ARCH_RAW="$(uname -m)"
    IS_TERMUX=0

    case "$ARCH_RAW" in
        x86_64|amd64)  ARCH="amd64" ;;
        aarch64|arm64) ARCH="arm64" ;;
        armv7*|armv6*) ARCH="arm" ;;
                arm64) ARCH="arm64" ;;
                    *) ARCH="amd64" ;;   # best guess
    esac

    PKG="" ; SUDO=""
    if [ "${TERMUX_VERSION-}" ] || { [ -n "${PREFIX:-}" ] && [ "${PREFIX#*com.termux}" != "${PREFIX}" ]; }; then
        PLATFORM="Termux ($ARCH)"; OS_NAME="termux"; IS_TERMUX=1; PKG="pkg"
    elif [ "$OS_NAME" = "Darwin" ]; then
        PLATFORM="macOS ($ARCH)"
        if command -v brew >/dev/null 2>&1; then PKG="brew"; else PKG="none"; fi
    elif [ "$OS_NAME" = "Linux" ]; then
        if [ -r /etc/os-release ]; then . /etc/os-release; DISTRO="$ID"; else DISTRO="linux"; fi
        case "$DISTRO" in
            ubuntu|debian|raspbian|linuxmint|pop|kali) PKG="apt" ;;
            fedora|rhel|centos|rocky|alma|amzn)        PKG="dnf" ;;
            opensuse*|sles)                            PKG="zypper" ;;
            alpine)                                    PKG="apk" ;;
            arch|manjaro|endeavouros|cachyos)          PKG="pacman" ;;
            *) [ "$(command -v apt)" ] && PKG=apt || { [ "$(command -v dnf)" ] && PKG=dnf || \
               { [ "$(command -v pacman)" ] && PKG=pacman || { [ "$(command -v apk)" ] && PKG=apk || \
                 { [ "$(command -v zypper)" ] && PKG=zypper || PKG=none; }; }; }; } ;;
        esac
        PLATFORM="Linux · $DISTRO ($ARCH)"
    elif printf '%s' "$OS_NAME" | grep -qi mingw\|msys\|cygwin; then
        PLATFORM="Windows (Git Bash) · $ARCH"; PKG="winget-hint"
    else
        PLATFORM="$OS_NAME ($ARCH)"; PKG="none"
    fi

    # Elevation helper (never needed on Termux/mac user-brew)
    if [ "$(id -u)" != "0" ] && command -v sudo >/dev/null 2>&1 \
       && [ "$IS_TERMUX" = "0" ] && ! [ "$PKG" = "brew" ]; then
        SUDO="sudo"
    fi
}

pkg_install() {
    pkgs="$*"
    case "$PKG" in
        apt)    $SUDO apt-get update -y >/dev/null 2>&1 || true
                $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y $pkgs ;;
        dnf)    $SUDO dnf install -y $pkgs ;;
        yum)    $SUDO yum install -y $pkgs ;;
        zypper) $SUDO zypper --non-interactive install $pkgs ;;
        pacman) $SUDO pacman -Sy --noconfirm --needed $pkgs ;;
        apk)    $SUDO apk add --no-cache $pkgs ;;
        brew)   brew install $pkgs ;;
        pkg)    pkg install -y $pkgs ;;
        none)   warn "No known package manager — please install manually: $pkgs"; return 1 ;;
        winget-hint) warn "Install manually via winget/choco: $pkgs"; return 1 ;;
    esac
}

have_python() {
    command -v python3 >/dev/null 2>&1 || return 1
    v=$(python3 -c 'import sys;print(1 if sys.version_info>=(3,9) else 0)' 2>/dev/null || echo 0)
    [ "$v" = "1" ]
}

install_cloudflared() {
    if command -v cloudflared >/dev/null 2>&1; then
        ok "cloudflared $(cloudflared --version 2>/dev/null | awk '{print $NF}') already present"; return 0
    fi
    step "Installing cloudflared"
    case "$OS_NAME" in
        Darwin) pkg_install cloudflared || fail "Install cloudflared manually: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" ;;
        termux) pkg_install cloudflared || warn "cloudflared unavailable in termux repos — tunneling may need manual setup" ;;
        *)
            base="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux"
            case "$ARCH" in amd64) url="${base}-amd64";; arm64) url="${base}-arm64";; arm) url="${base}-arm";; esac
            tmp=$(mktemp); curl -fsSL "$url" -o "$tmp"
            $SUDO install -m 0755 "$tmp" /usr/local/bin/cloudflared 2>/dev/null \
              || { mkdir -p "$HOME/.local/bin"; install -m 0755 "$tmp" "$HOME/.local/bin/cloudflared"; \
                   export PATH="$HOME/.local/bin:$PATH"; }
            rm -f "$tmp"
            ;;
    esac
    command -v cloudflared >/dev/null 2>&1 && ok "cloudflared installed" || warn "cloudflared not on PATH yet"
}

# ── Uninstall path ─────────────────────────────────────────────────────────
do_uninstall() {
    step "Stopping services"
    if command -v systemctl >/dev/null 2>&1; then
        systemctl --user stop porter.service 2>/dev/null || true
        systemctl --user disable porter.service 2>/dev/null || true
        rm -f "$HOME/.config/systemd/user/porter.service"
    fi
    pkill -f "python3.*app.py.*$INSTALL_DIR" 2>/dev/null || true
    step "Removing files"
    rm -rf "$INSTALL_DIR"
    rm -f "$HOME/.local/bin/porter" "/usr/local/bin/porter" 2>/dev/null || true
    ok "Porter removed. Goodbye 👋"
    exit 0
}

# ── Main ───────────────────────────────────────────────────────────────────
banner
detect_platform
printf "  ${DIM}Detected:${R} %s\n" "$PLATFORM"
[ "$ASSUME_YES" = "0" ] && printf "  ${DIM}Mode:${R} non-interactive (flags/env control everything)\n"
[ "$UNINSTALL" = "1" ] && do_uninstall

# 1 · System packages -------------------------------------------------------
step "Checking Python 3.9+"
if have_python; then
    ok "Python $(python3 -V | awk '{print $2}') found"
else
    warn "Python 3.9+ missing — installing"
    case "$PKG" in
        apt)    pkg_install python3 python3-venv python3-pip ;;
        dnf|yum)pkg_install python3 python3-pip ;;
        pacman) pkg_install python ;;
        apk)    pkg_install python3 py3-pip ;;
        zypper) pkg_install python3 python3-pip python3-venv ;;
        brew)   pkg_install python@3.12 ;;
        pkg)    pkg_install python ;;
        *)      fail "Could not install Python automatically on this platform." ;;
    esac
    have_python || fail "Python installation failed."
    ok "Python $(python3 -V | awk '{print $2}') installed"
fi

step "Checking cloudflared"
install_cloudflared

# 2 · Source -----------------------------------------------------------------
IN_REPO=0
SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
if [ -f "$SCRIPT_DIR/app.py" ] && [ -d "$SCRIPT_DIR/porter" ]; then
    IN_REPO=1
    step "Source detected next to installer — installing in place"
    INSTALL_DIR="$SCRIPT_DIR"
elif [ -f "$INSTALL_DIR/app.py" ]; then
    step "Existing installation at $INSTALL_DIR — updating"
else
    step "Downloading Porter → $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    tarball=$(mktemp)
    curl -fsSL "https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}" -o "$tarball" \
        || fail "Download failed — check network or branch name ($BRANCH)."
    tar -xzf "$tarball" -C "$INSTALL_DIR" --strip-components=1 && rm -f "$tarball"
    ok "Source ready (${BRANCH})"
fi

# 3 · Virtualenv + deps ------------------------------------------------------
step "Creating virtual environment"
cd "$INSTALL_DIR"
python3 -m venv .venv || { python3 -m venv --without-pip .venv && curl -fsSLo .venv/bin/pip https://bootstrap.pypa.io/get-pip.py && .venv/bin/python .venv/bin/pip --version >/dev/null; }
ok ".venv ready"

step "Installing dependencies (Flask + httpx)"
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
ok "Dependencies installed"

step "Registering the 'porter' command"
./.venv/bin/pip install --quiet -e . >/dev/null 2>&1 || warn "Editable install skipped (CLI still available via wrapper)"
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/porter" <<EOF
#!/usr/bin/env sh
exec "$INSTALL_DIR/.venv/bin/porter" "\$@"
EOF
chmod +x "$HOME/.local/bin/porter"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) printf 'export PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc" 2>/dev/null || true
       printf 'export PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.zshrc"  2>/dev/null || true
       export PATH="$HOME/.local/bin:$PATH"
       warn "~/.local/bin added to PATH (new shells pick it up)" ;;
esac
ok "'porter' CLI available"

# 4 · Optional service -------------------------------------------------------
if [ -z "$MAKE_SERVICE" ] && [ "$ASSUME_YES" = "1" ] && [ "$NO_START" = "0" ] \
   && command -v systemctl >/dev/null 2>&1 && systemctl --user status >/dev/null 2>&1; then
    printf "\n  Create an auto-start service (systemd)? [Y/n] "
    read -r answer || answer=Y
    [ "${answer:-Y}" = "Y" ] || [ "${answer:-Y}" = "y" ] && MAKE_SERVICE=1 || MAKE_SERVICE=0
fi

if [ "$MAKE_SERVICE" = "1" ] && command -v systemctl >/dev/null 2>&1; then
    step "Installing systemd user service"
    mkdir -p "$HOME/.config/systemd/user"
    cat > "$HOME/.config/systemd/user/porter.service" <<EOF
[Unit]
Description=Porter Tunnel Portal
After=network-online.target

[Service]
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python app.py --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now porter.service >/dev/null 2>&1 || true
    ok "Service enabled — Porter starts on boot"
fi

# 5 · Passcode ----------------------------------------------------------------
if [ -n "$PASSCODE" ]; then
    "$INSTALL_DIR/.venv/bin/python" - "$PASSCODE" <<'PYEOF'
import hashlib, json, sys, os
cfg_path = os.path.join(os.getcwd(), "config.json")
cfg = {}
if os.path.exists(cfg_path):
    cfg = json.load(open(cfg_path))
cfg["passcode_hash"] = hashlib.sha256(sys.argv[1].encode()).hexdigest()
json.dump(cfg, open(cfg_path, "w"), indent=2)
print("  ✔ Passcode set")
PYEOF
fi

# 6 · Start --------------------------------------------------------------------
if [ "$NO_START" = "0" ] && [ "$MAKE_SERVICE" != "1" ]; then
    step "Starting Porter"
    (
        cd "$INSTALL_DIR"
        setsid nohup ./.venv/bin/python app.py --port "$PORT" > "$INSTALL_DIR/server.log" 2>&1 < /dev/null &
    )
    sleep 3
    if curl -sf -m 5 "http://localhost:$PORT/api/status" > /dev/null 2>&1; then
        ok "Server live on http://localhost:$PORT"
    else
        warn "Server did not answer yet — check $INSTALL_DIR/server.log"
    fi
fi

# 7 · Summary -------------------------------------------------------------------
printf "\n${ORANGE}${BOLD}"
printf '  ════════════════════════════════════════════\n'
printf '   Installation complete\n'
printf '  ════════════════════════════════════════════%s\n' "$R"
printf "  Location : ${CYAN}%s${R}\n" "$INSTALL_DIR"
printf "  Portal   : ${CYAN}http://localhost:%s${R}\n" "$PORT"
printf "  Setup    : ${CYAN}http://localhost:%s/setup${R}\n" "$PORT"
printf "\n  Next:\n"
printf "    1. Open the URL above and set a passcode\n"
printf "    2. Connect Cloudflare via the Connector Portal\n"
printf "       ${DIM}(blank portal field = primary portal)${R}\n"
printf "    3. Pick one or many accounts — each is verified instantly\n"
printf "    4. Create your first tunnel 🚀\n\n"
