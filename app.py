"""
Cloudflare Tunnel Portal - Main Application

A web portal that creates DNS records + cloudflared tunnels
to expose local services on your own domain.
Uses OAuth 2.1 with PKCE for Cloudflare authentication.

Stable version: uses a single cloudflared process managed by TunnelManager.
"""

import fcntl
import hashlib
import json
import logging
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from functools import wraps
from logging.handlers import RotatingFileHandler
from queue import Queue
from threading import Thread

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from cloudflare_client import CloudflareAPI, CloudflareOAuth, TokenStorage, _load_config, _save_config
from tunnel_manager import TunnelManager, get_manager, load_tunnels, save_tunnels
import api_keys

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config["TEMPLATES_AUTO_RELOAD"] = True

def _resolve_port():
    """Always use 7262."""
    return 7262


def _port_is_available(port):
    """Return True if the port is free on 0.0.0.0."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            return True
    except OSError:
        return False


PORT = _resolve_port()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "portal.log")

# --- Logging with rotation (graceful fallback for read-only filesystems) ---
_log_handlers = [logging.StreamHandler(sys.stdout)]
try:
    _file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    _log_handlers.append(_file_handler)
except (OSError, PermissionError):
    pass  # Read-only filesystem — log to stdout only

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_log_handlers,
)
log = logging.getLogger("portal")


# --- Force HTTPS for traffic arriving through Cloudflare ---
# Cloudflare sets X-Forwarded-Proto on every proxied request. Direct LAN /
# localhost access (OAuth callback, local dashboard) has no such header and
# is left untouched, so http://localhost:7262 keeps working.
@app.before_request
def _force_https():
    if request.headers.get("X-Forwarded-Proto") == "http":
        url = request.url.replace("http://", "https://", 1)
        return redirect(url, code=308)
    return None


@app.after_request
def _add_hsts(response):
    if (
        request.headers.get("X-Forwarded-Proto") == "https"
        or request.is_secure
    ):
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


# --- Startup reconciliation ---
def _startup_reconcile():
    """Validate tunnels and auto-restart cloudflared on app start."""
    manager = get_manager()
    cfg = _load_config()
    tunnels = load_tunnels()

    log.info("Startup: %d tunnels registered", len(tunnels))

    # Reconcile PIDs to the current cloudflared process
    manager.reconcile_tunnels()

    # Check if cloudflared needs to be restarted
    if tunnels and not manager.is_running():
        tunnel_token = cfg.get("tunnel_token")
        if tunnel_token:
            log.info("Startup: cloudflared not running, restarting...")
            try:
                manager.start(tunnel_token)
            except Exception as e:
                log.error("Startup: failed to restart cloudflared: %s", e)
        else:
            log.warning("Startup: tunnels exist but no tunnel_token in config")


def _background_health_check():
    """Background thread that monitors cloudflared health."""
    manager = get_manager()
    while True:
        time.sleep(30)
        try:
            cfg = _load_config()
            tunnel_token = cfg.get("tunnel_token")
            tunnels = load_tunnels()
            if tunnels and tunnel_token:
                manager.auto_restart_if_needed(tunnel_token)
        except Exception as e:
            log.error("Health check error: %s", e)


# --- Bootstrap (runs at import time so gunicorn workers get it too) ---
# Under `gunicorn app:app --preload`, code inside `if __name__ == "__main__"`
# never executes — which previously meant tunnels.json was never reconciled
# and cloudflared never restarted after a device reboot. A file lock ensures
# exactly one process performs initialization even with multiple workers.
_BOOTSTRAP_LOCK_FILE = os.path.join(BASE_DIR, ".bootstrap.lock")
_bootstrapped = False
_bootstrap_lock_fd = None


def _bootstrap():
    """Initialize manager, reconcile saved tunnels, start health monitor."""
    global _bootstrapped, _bootstrap_lock_fd
    if _bootstrapped:
        return
    _bootstrapped = True

    try:
        _bootstrap_lock_fd = open(_BOOTSTRAP_LOCK_FILE, "w")
        try:
            fcntl.flock(_bootstrap_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log.info("Bootstrap: another Porter process owns startup; skipping")
            return
    except OSError:
        pass  # read-only filesystem — proceed unlocked (single instance)

    try:
        manager = get_manager()
        manager.init()
        _startup_reconcile()
        Thread(target=_background_health_check, daemon=True).start()
    except Exception as e:
        log.error("Bootstrap failed: %s", e)


# --- Auth decorator ---
def is_setup_complete():
    cfg = _load_config()
    return bool(cfg.get("passcode_hash"))


def passcode_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_setup_complete():
            return redirect(url_for("setup"))

        if session.get("authenticated"):
            return f(*args, **kwargs)

        # Check X-API-Key header
        api_key = request.headers.get("X-API-Key")
        if api_key:
            if api_keys.validate_api_key(api_key):
                session["authenticated"] = True
                session.permanent = True
                return f(*args, **kwargs)
            if request.is_json:
                return jsonify({"error": "invalid API key"}), 401
            return redirect(url_for("login_page"))

        # Check X-Passcode header
        passcode = request.args.get("passcode") or request.form.get("passcode")
        if passcode:
            expected = _load_config().get("passcode_hash")
            if expected and hashlib.sha256(passcode.encode()).hexdigest() == expected:
                session["authenticated"] = True
                session.permanent = True
                return f(*args, **kwargs)

        if request.headers.get("X-Passcode"):
            expected = _load_config().get("passcode_hash")
            if expected and hashlib.sha256(request.headers["X-Passcode"].encode()).hexdigest() == expected:
                session["authenticated"] = True
                session.permanent = True
                return f(*args, **kwargs)

        if request.is_json:
            return jsonify({"error": "authentication required"}), 401

        return redirect(url_for("login_page"))
    return decorated


# --- Routes ---
@app.route("/")
def index():
    if not is_setup_complete():
        return redirect(url_for("setup"))
    if session.get("authenticated"):
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if not is_setup_complete():
        return redirect(url_for("setup"))

    error = None
    if request.method == "POST":
        passcode = request.form.get("passcode", "")
        expected = _load_config().get("passcode_hash")
        if expected and hashlib.sha256(passcode.encode()).hexdigest() == expected:
            session["authenticated"] = True
            session.permanent = True
            return redirect(url_for("dashboard"))
        error = "Invalid passcode"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/dashboard")
@passcode_required
def dashboard():
    oauth = CloudflareOAuth()
    tunnels = load_tunnels()
    is_connected = oauth.is_authenticated()
    cfg = _load_config()
    active_domain = cfg.get("domain", "kalandar.me")
    manager = get_manager()
    health = manager.health_check()

    zones = []
    if is_connected:
        try:
            cf = CloudflareAPI(oauth)
            zones = cf.list_zones()
        except Exception as e:
            log.warning("Failed to fetch zones: %s", e)
    domains = [z["name"] for z in zones] if zones else [active_domain]

    return render_template(
        "dashboard.html",
        tunnels=tunnels,
        domains=domains,
        zones=zones,
        active_domain=active_domain,
        is_connected=is_connected,
        tunnel_health=health,
        protocol=manager.get_protocol(),
    )


@app.route("/docs")
@passcode_required
def docs():
    return render_template("docs.html")


@app.route("/setup", methods=["GET", "POST"])
def setup():
    cfg = _load_config()
    oauth = CloudflareOAuth()
    is_connected = oauth.is_authenticated()
    setup_done = is_setup_complete()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "connect_cloudflare":
            try:
                auth_url = oauth.generate_auth_url()
                return redirect(auth_url)
            except Exception as e:
                log.error("OAuth initiation failed: %s", e)
                return render_template("setup.html", error=str(e), cfg=cfg, is_connected=is_connected, setup_done=setup_done)

        elif action == "set_passcode":
            passcode = request.form.get("passcode", "").strip()
            if passcode and len(passcode) >= 4:
                cfg["passcode_hash"] = hashlib.sha256(passcode.encode()).hexdigest()
                _save_config(cfg)
                if not setup_done:
                    return redirect(url_for("setup"))
                return render_template("setup.html", success="Passcode updated", cfg=cfg, is_connected=is_connected, setup_done=True)
            else:
                return render_template("setup.html", error="Passcode must be at least 4 characters", cfg=cfg, is_connected=is_connected, setup_done=setup_done)

        elif action == "set_active_domain":
            active = request.form.get("domain", "")
            if active in cfg.get("domains", []):
                cfg["domain"] = active
                _save_config(cfg)
            return redirect(url_for("dashboard"))

        elif action == "set_protocol":
            protocol = request.form.get("protocol", "auto")
            if protocol in ("auto", "quic", "http2"):
                cfg["protocol"] = protocol
                _save_config(cfg)
                # Restart cloudflared with new protocol if running
                manager = get_manager()
                if manager.is_running():
                    tunnel_token = cfg.get("tunnel_token")
                    if tunnel_token:
                        try:
                            manager.restart(tunnel_token, protocol if protocol != "auto" else None)
                            return render_template("setup.html", success=f"Protocol changed to {protocol}. Tunnels restarted.", cfg=cfg, is_connected=is_connected, setup_done=setup_done)
                        except Exception as e:
                            return render_template("setup.html", error=f"Failed to restart: {e}", cfg=cfg, is_connected=is_connected, setup_done=setup_done)
            return redirect(url_for("setup"))

        elif action == "reset":
            try:
                manager = get_manager()
                manager.stop()

                tokens_path = os.path.join(BASE_DIR, "tokens.json")
                if os.path.exists(tokens_path):
                    os.remove(tokens_path)

                cfg = {"domains": cfg.get("domains", []), "domain": cfg.get("domain", "")}
                _save_config(cfg)
                save_tunnels({})
                return redirect(url_for("setup"))
            except Exception as e:
                return render_template("setup.html", error=str(e), cfg=cfg, is_connected=is_connected, setup_done=setup_done)

    return render_template("setup.html", cfg=cfg, is_connected=is_connected, setup_done=setup_done)


@app.route("/auth/cloudflare")
def auth_cloudflare():
    oauth = CloudflareOAuth()
    try:
        auth_url = oauth.generate_auth_url()
        return redirect(auth_url)
    except Exception as e:
        log.error("OAuth initiation failed: %s", e)
        return redirect(url_for("setup", error=str(e)))


@app.route("/auth/callback")
def auth_callback():
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        log.error("OAuth error: %s", error)
        return redirect(url_for("setup", error=f"Cloudflare authorization failed: {error}"))

    if not code or not state:
        return redirect(url_for("setup", error="Missing authorization code"))

    oauth = CloudflareOAuth()
    try:
        oauth.exchange_code(code, state)
        log.info("OAuth authentication successful")

        cf_api = CloudflareAPI(oauth)
        try:
            account_id = cf_api.get_account_id()
            cfg = _load_config()
            cfg["account_id"] = account_id
            _save_config(cfg)
            log.info("Detected account ID: %s", account_id)
        except Exception as e:
            log.warning("Could not detect account ID: %s", e)

        return redirect(url_for("setup", success="Cloudflare connected successfully"))
    except Exception as e:
        log.error("Token exchange failed: %s", e)
        return redirect(url_for("setup", error=str(e)))


@app.route("/auth/disconnect", methods=["POST"])
def auth_disconnect():
    tokens_path = os.path.join(BASE_DIR, "tokens.json")
    if os.path.exists(tokens_path):
        os.remove(tokens_path)
    return redirect(url_for("setup"))


# --- Tunnel API (single-process model) ---
@app.route("/api/tunnel/create", methods=["POST"])
@passcode_required
def api_create_tunnel():
    data = request.get_json() or {}
    port = data.get("port")
    subdomain = data.get("subdomain", "").strip().lower()
    domain = data.get("domain", "").strip().lower()

    if not port:
        return jsonify({"error": "Port is required"}), 400
    if not subdomain:
        return jsonify({"error": "Subdomain is required"}), 400
    if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", subdomain):
        return jsonify({"error": "Invalid subdomain: only lowercase letters, numbers, and hyphens allowed"}), 400

    cfg = _load_config()
    if not domain:
        domain = cfg.get("domain", "kalandar.me")
    full_domain = f"{subdomain}.{domain}"

    tunnels = load_tunnels()
    tunnel_key = f"{domain}/{subdomain}"
    if tunnel_key in tunnels:
        return jsonify({"error": f"Subdomain '{subdomain}' on {domain} is already in use"}), 400

    oauth = CloudflareOAuth()
    if not oauth.is_authenticated():
        return jsonify({"error": "Not connected to Cloudflare. Please connect first.", "auth_required": True}), 401

    cf_api = CloudflareAPI(oauth)

    try:
        zone_id = cf_api.get_zone_id(domain)
    except Exception as e:
        return jsonify({"error": f"Could not find zone for {domain}: {str(e)}"}), 500

    try:
        existing = cf_api.list_dns_records(zone_id=zone_id, subdomain=subdomain, domain=domain)
        for rec in existing:
            if rec.get("name") == full_domain:
                cf_api.delete_dns_record(rec["id"], zone_id=zone_id)
                log.info("Cleaned up existing DNS record for %s", full_domain)
    except Exception as e:
        log.warning("DNS cleanup check failed: %s", e)

    tunnel_id = cfg.get("tunnel_id")
    tunnel_token = cfg.get("tunnel_token")

    if not tunnel_id:
        try:
            tunnel = cf_api.create_tunnel(f"portal-{subdomain}")
            tunnel_id = tunnel["id"]
            tunnel_token = tunnel.get("token", "")
            log.info("Created new tunnel: %s", tunnel_id)
        except Exception as e:
            return jsonify({"error": f"Failed to create tunnel: {str(e)}"}), 500

    try:
        cf_api.add_tunnel_hostname(tunnel_id, full_domain, f"http://localhost:{port}")
        log.info("Configured tunnel hostname: %s -> localhost:%s", full_domain, port)
    except Exception as e:
        return jsonify({"error": f"Failed to configure tunnel hostname: {str(e)}"}), 500

    try:
        cf_api.create_dns_record(
            name=full_domain,
            content=f"{tunnel_id}.cfargotunnel.com",
            record_type="CNAME",
            zone_id=zone_id,
            proxied=True,
        )
        log.info("Created DNS record: %s -> %s.cfargotunnel.com", full_domain, tunnel_id)
    except Exception as e:
        return jsonify({"error": f"Failed to create DNS record: {str(e)}"}), 500

    if not tunnel_token:
        try:
            tunnel_token = cf_api.get_tunnel_token(tunnel_id)
        except Exception as e:
            return jsonify({"error": f"Failed to get tunnel token: {str(e)}"}), 500

    # Save tunnel token for manager (reload to avoid clobbering keys
    # written meanwhile, e.g. tunnel_id saved by create_tunnel)
    if tunnel_token:
        fresh_cfg = _load_config()
        if not fresh_cfg.get("tunnel_token"):
            fresh_cfg["tunnel_token"] = tunnel_token
            _save_config(fresh_cfg)

    # Start/restart cloudflared with this tunnel token (single process)
    manager = get_manager()
    try:
        # start() is idempotent: adopts a running process with the same
        # token, kills stale/different-token processes before starting.
        manager.start(tunnel_token)
    except Exception as e:
        return jsonify({"error": f"Failed to start cloudflared: {str(e)}"}), 500

    tunnels[tunnel_key] = {
        "port": int(port),
        "url": f"https://{full_domain}",
        "pid": manager.get_pid(),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tunnel_id": tunnel_id,
        "full_domain": full_domain,
        "domain": domain,
        "subdomain": subdomain,
        "healthy": True,
    }
    save_tunnels(tunnels)

    log.info("Tunnel started: %s -> localhost:%s (pid=%s)", full_domain, port, manager.get_pid())

    return jsonify({
        "success": True,
        "url": f"https://{full_domain}",
        "pid": manager.get_pid(),
        "message": f"Service exposed at https://{full_domain}",
    })


@app.route("/api/tunnel/create/stream", methods=["POST"])
@passcode_required
def api_create_tunnel_stream():
    data = request.get_json() or {}
    port = data.get("port")
    subdomain = data.get("subdomain", "").strip().lower()
    domain = data.get("domain", "").strip().lower()

    if not port:
        return jsonify({"error": "Port is required"}), 400
    if not subdomain:
        return jsonify({"error": "Subdomain is required"}), 400
    if not re.match(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", subdomain):
        return jsonify({"error": "Invalid subdomain: only lowercase letters, numbers, and hyphens allowed"}), 400

    cfg = _load_config()
    if not domain:
        domain = cfg.get("domain", "kalandar.me")
    full_domain = f"{subdomain}.{domain}"

    tunnels = load_tunnels()
    tunnel_key = f"{domain}/{subdomain}"
    if tunnel_key in tunnels:
        return jsonify({"error": f"Subdomain '{subdomain}' on {domain} is already in use"}), 400

    oauth = CloudflareOAuth()
    if not oauth.is_authenticated():
        return jsonify({"error": "Not connected to Cloudflare. Please connect first.", "auth_required": True}), 401

    def generate():
        q = Queue()

        def send(step, status, message, detail=None):
            evt = {"step": step, "status": status, "message": message}
            if detail:
                evt["detail"] = detail
            q.put(evt)

        def worker():
            cf_api = CloudflareAPI(oauth)
            tunnel_id = cfg.get("tunnel_id")
            tunnel_token = cfg.get("tunnel_token")
            manager = get_manager()

            try:
                send("dns_cleanup", "running", "Checking existing DNS records...")
                try:
                    zone_id = cf_api.get_zone_id(domain)
                    send("dns_cleanup", "ok", f"Zone found: {domain}")
                except Exception as e:
                    send("dns_cleanup", "error", f"Zone lookup failed: {e}")
                    q.put(None)
                    return

                try:
                    existing = cf_api.list_dns_records(zone_id=zone_id, subdomain=subdomain, domain=domain)
                    for rec in existing:
                        if rec.get("name") == full_domain:
                            cf_api.delete_dns_record(rec["id"], zone_id=zone_id)
                except Exception:
                    pass

                send("tunnel", "running", "Setting up tunnel...")
                if not tunnel_id:
                    try:
                        tunnel = cf_api.create_tunnel(f"portal-{subdomain}")
                        tunnel_id = tunnel["id"]
                        tunnel_token = tunnel.get("token", "")
                        send("tunnel", "ok", f"Tunnel created: {tunnel_id[:8]}...")
                    except Exception as e:
                        send("tunnel", "error", f"Failed to create tunnel: {e}")
                        q.put(None)
                        return
                else:
                    send("tunnel", "ok", f"Using existing tunnel: {tunnel_id[:8]}...")

                send("hostname", "running", "Configuring tunnel hostname...")
                try:
                    cf_api.add_tunnel_hostname(tunnel_id, full_domain, f"http://localhost:{port}")
                    send("hostname", "ok", f"Hostname: {full_domain} -> localhost:{port}")
                except Exception as e:
                    send("hostname", "error", f"Failed to configure hostname: {e}")
                    q.put(None)
                    return

                send("dns_create", "running", "Creating DNS record...")
                try:
                    cf_api.create_dns_record(
                        name=full_domain,
                        content=f"{tunnel_id}.cfargotunnel.com",
                        record_type="CNAME",
                        zone_id=zone_id,
                        proxied=True,
                    )
                    send("dns_create", "ok", f"DNS record created: {full_domain}")
                except Exception as e:
                    send("dns_create", "error", f"Failed to create DNS record: {e}")
                    q.put(None)
                    return

                if not tunnel_token:
                    try:
                        tunnel_token = cf_api.get_tunnel_token(tunnel_id)
                    except Exception as e:
                        send("start", "error", f"Failed to get tunnel token: {e}")
                        q.put(None)
                        return

                # Save tunnel token for manager (reload to avoid clobbering
                # keys written meanwhile, e.g. tunnel_id)
                if tunnel_token:
                    fresh_cfg = _load_config()
                    if not fresh_cfg.get("tunnel_token"):
                        fresh_cfg["tunnel_token"] = tunnel_token
                        _save_config(fresh_cfg)

                send("start", "running", "Starting cloudflared...")
                try:
                    # start() is idempotent: adopts matching token, kills stale
                    manager.start(tunnel_token)
                    send("start", "ok", f"cloudflared started (protocol={manager.get_protocol()})")
                except FileNotFoundError:
                    send("start", "error", "cloudflared not found. Please install it first.")
                    q.put(None)
                    return
                except Exception as e:
                    send("start", "error", f"Failed to start cloudflared: {e}")
                    q.put(None)
                    return

                tunnels[tunnel_key] = {
                    "port": int(port),
                    "url": f"https://{full_domain}",
                    "pid": manager.get_pid(),
                    "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "tunnel_id": tunnel_id,
                    "full_domain": full_domain,
                    "domain": domain,
                    "subdomain": subdomain,
                    "healthy": True,
                }
                save_tunnels(tunnels)

                log.info("Tunnel started: %s -> localhost:%s (pid=%s)", full_domain, port, manager.get_pid())
                send("done", "ok", f"Service live at https://{full_domain}", {
                    "url": f"https://{full_domain}",
                    "pid": manager.get_pid(),
                })
            except Exception as e:
                log.error("Tunnel creation error: %s", e)
                send("error", "error", f"Unexpected error: {e}")

            q.put(None)

        Thread(target=worker, daemon=True).start()

        import time as _time
        while True:
            evt = q.get()
            if evt is None:
                break
            yield f"data: {json.dumps(evt)}\n\n"
            _time.sleep(0.1)

    return generate(), 200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }


@app.route("/api/tunnel/stop/<path:tunnel_key>", methods=["POST"])
@passcode_required
def api_stop_tunnel(tunnel_key):
    tunnels = load_tunnels()
    if tunnel_key not in tunnels:
        return jsonify({"error": "Tunnel not found"}), 404

    info = tunnels[tunnel_key]
    full_domain = info.get("full_domain", "")
    tunnel_id = info.get("tunnel_id")

    oauth = CloudflareOAuth()
    if oauth.is_authenticated():
        cf_api = CloudflareAPI(oauth)
        domain = info.get("domain", _load_config().get("domain", "kalandar.me"))
        try:
            zone_id = cf_api.get_zone_id(domain)
            existing = cf_api.list_dns_records(zone_id=zone_id, subdomain=info.get("subdomain", tunnel_key), domain=domain)
            for rec in existing:
                if rec.get("name") == full_domain:
                    cf_api.delete_dns_record(rec["id"], zone_id=zone_id)
                    log.info("Deleted DNS record: %s", full_domain)
        except Exception as e:
            log.warning("DNS cleanup failed: %s", e)

        try:
            if tunnel_id:
                cf_api.remove_tunnel_hostname(tunnel_id, full_domain)
                log.info("Removed tunnel hostname: %s", full_domain)
        except Exception as e:
            log.warning("Tunnel hostname cleanup failed: %s", e)

    del tunnels[tunnel_key]
    save_tunnels(tunnels)

    # If no more tunnels, stop cloudflared to save resources
    if not tunnels:
        manager = get_manager()
        manager.stop()
        log.info("No more active tunnels, stopped cloudflared")

    return jsonify({"success": True, "message": f"Tunnel for {full_domain} stopped"})


@app.route("/api/tunnels")
@passcode_required
def api_list_tunnels():
    tunnels = load_tunnels()
    manager = get_manager()
    cloudflared_running = manager.is_running()

    result = []
    for key, info in tunnels.items():
        result.append({
            "key": key,
            "subdomain": info.get("subdomain", key),
            "domain": info.get("domain", ""),
            "port": info.get("port"),
            "url": info.get("url"),
            "pid": manager.get_pid(),
            "running": cloudflared_running,
            "healthy": info.get("healthy", cloudflared_running),
            "started_at": info.get("started_at"),
        })
    return jsonify(result)


@app.route("/api/tunnel/health")
@passcode_required
def api_tunnel_health():
    """Real-time health check endpoint."""
    manager = get_manager()
    health = manager.health_check()
    tunnels = load_tunnels()
    cfg = _load_config()

    return jsonify({
        "cloudflared": health,
        "tunnel_id": cfg.get("tunnel_id"),
        "protocol": manager.get_protocol(),
        "active_tunnels": len(tunnels),
        "tunnels": {k: {"url": v.get("url"), "healthy": v.get("healthy", True)} for k, v in tunnels.items()},
    })


@app.route("/api/tunnel/restart", methods=["POST"])
@passcode_required
def api_restart_tunnel():
    """Restart cloudflared process."""
    manager = get_manager()
    cfg = _load_config()
    tunnel_token = cfg.get("tunnel_token")

    if not tunnel_token:
        return jsonify({"error": "No tunnel token available"}), 400

    try:
        protocol = (request.get_json(silent=True) or {}).get("protocol")
        manager.restart(tunnel_token, protocol)
        return jsonify({"success": True, "message": "cloudflared restarted", "protocol": manager.get_protocol()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ports/scan")
@passcode_required
def api_scan_ports():
    import socket
    common_ports = [80, 443, 3000, 3001, 4000, 4200, 5000, 5173, 5500, 6000, 6379, 7262, 8000, 8080, 8443, 8888, 9000, 9090]
    open_ports = []
    for port in common_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", port))
            if result == 0:
                open_ports.append(port)
            sock.close()
        except Exception:
            pass
    return jsonify({"open_ports": open_ports})


@app.route("/api/domains", methods=["GET"])
@passcode_required
def api_get_domains():
    cfg = _load_config()
    oauth = CloudflareOAuth()
    zones = []
    if oauth.is_authenticated():
        try:
            cf = CloudflareAPI(oauth)
            zones = cf.list_zones()
        except Exception as e:
            log.warning("Failed to fetch zones: %s", e)
    return jsonify({
        "domains": [z["name"] for z in zones],
        "zones": zones,
        "active": cfg.get("domain", ""),
    })


@app.route("/api/domains/active", methods=["POST"])
@passcode_required
def api_set_active_domain():
    data = request.get_json() or {}
    domain = data.get("domain", "")
    cfg = _load_config()
    cfg["domain"] = domain
    _save_config(cfg)
    return jsonify({"success": True, "active": domain})


@app.route("/api/status")
def api_status():
    """Public status endpoint (no auth required)."""
    manager = get_manager()
    tunnels = load_tunnels()
    return jsonify({
        "running": True,
        "tunnels": len(tunnels),
        "cloudflared": manager.is_running(),
    })


@app.route("/api/keys", methods=["GET"])
@passcode_required
def api_keys_list():
    """List all API keys."""
    keys = api_keys.list_api_keys()
    return jsonify({"keys": keys})


@app.route("/api/keys", methods=["POST"])
@passcode_required
def api_keys_create():
    """Create a new API key."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    key_data = api_keys.generate_api_key(name)
    return jsonify({
        "success": True,
        "key": key_data["key"],
        "id": key_data["id"],
        "name": key_data["name"],
        "created_at": key_data["created_at"],
    }), 201


@app.route("/api/keys/<key_id>", methods=["DELETE"])
@passcode_required
def api_keys_delete(key_id):
    """Delete an API key."""
    if api_keys.delete_api_key(key_id):
        return jsonify({"success": True, "message": "key deleted"})
    return jsonify({"error": "key not found"}), 404


@app.route("/api/keys/<key_id>/rotate", methods=["POST"])
@passcode_required
def api_keys_rotate(key_id):
    """Rotate an API key."""
    result = api_keys.rotate_api_key(key_id)
    if result:
        return jsonify({
            "success": True,
            "key": result["key"],
            "id": result["id"],
            "name": result["name"],
            "created_at": result["created_at"],
        })
    return jsonify({"error": "key not found"}), 404


# Bootstrap on import — this is what makes tunnel restore work under
# gunicorn/systemd, where `if __name__ == "__main__"` never runs.
_bootstrap()


if __name__ == "__main__":
    # Validate port before doing anything else
    if not _port_is_available(PORT):
        log.error("Port %s is already in use. Set PORT env var to a free port.", PORT)
        sys.exit(1)

    # Graceful shutdown for systemd (SIGTERM)
    def _shutdown(signum, frame):
        log.info("Received signal %s, shutting down...", signum)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("=" * 50)
    log.info("  Porter - Cloudflare Tunnel Portal")
    log.info("  Port:     %s", PORT)
    log.info("  Bind:     0.0.0.0:%s", PORT)
    log.info("  URL:      http://0.0.0.0:%s", PORT)
    log.info("  PID:      %s", os.getpid())
    log.info("=" * 50)

    # Initialize TunnelManager, restore saved tunnels and start the
    # health monitor. Runs at import time so it works under gunicorn
    # (--preload) as well as `python app.py` dev mode.
    _bootstrap()

    app.run(host="0.0.0.0", port=PORT, debug=False)
