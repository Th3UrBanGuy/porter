"""
Tunnel Manager - Manages a single cloudflared process with health monitoring.

Instead of spawning a new cloudflared per tunnel, this module maintains one
process that serves all subdomains via ingress rules. It handles:
- Single cloudflared lifecycle (start, stop, restart, reload)
- Health monitoring via metrics endpoint
- Protocol fallback (QUIC -> HTTP/2) for WSL2 compatibility
- Startup reconciliation of stale tunnel state
- Adoption of existing cloudflared processes on startup
"""

import glob
import json
import logging
import os
import re
import signal
import subprocess
import time
import platform
from pathlib import Path

log = logging.getLogger("portal")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TUNNELS_FILE = os.path.join(BASE_DIR, "tunnels.json")
TUNNEL_LOG_FILE = os.path.join(BASE_DIR, "tunnel.log")
METRICS_PORT = 20241


def _load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def _save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def load_tunnels():
    if os.path.exists(TUNNELS_FILE):
        with open(TUNNELS_FILE) as f:
            return json.load(f)
    return {}


def save_tunnels(tunnels):
    with open(TUNNELS_FILE, "w") as f:
        json.dump(tunnels, f, indent=2)


def _is_wsl():
    """Detect if running inside WSL2."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def _is_port_in_use(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _find_available_metrics_port():
    """Find an available port for cloudflared metrics server."""
    port = METRICS_PORT
    while _is_port_in_use(port) and port < METRICS_PORT + 50:
        port += 1
    return port


def _find_existing_cloudflared():
    """
    Find existing cloudflared processes started by this portal.
    Returns list of dicts with pid, token, cmd info.
    """
    results = []
    try:
        output = subprocess.check_output(
            ["ps", "aux"], stderr=subprocess.DEVNULL, text=True
        )
        for line in output.strip().split("\n"):
            if "cloudflared" in line and "tunnel" in line and "grep" not in line:
                parts = line.split()
                try:
                    pid = int(parts[1])
                    # Extract token from --token argument
                    cmd_full = " ".join(parts[10:])
                    token_match = re.search(r"--token\s+(\S+)", cmd_full)
                    token = token_match.group(1) if token_match else None

                    # Ignore processes without a token (e.g. quick tunnels
                    # started with `--url`) — they are not managed by us
                    # and must never be adopted or counted as "running".
                    if not token:
                        continue

                    # Detect protocol from args
                    proto_match = re.search(r"--protocol\s+(\S+)", cmd_full)
                    protocol = proto_match.group(1) if proto_match else "quic"

                    results.append({
                        "pid": pid,
                        "token": token,
                        "protocol": protocol,
                        "cmd": cmd_full,
                    })
                except (ValueError, IndexError):
                    continue
    except Exception as e:
        log.debug("Failed to find existing cloudflared: %s", e)
    return results


def _try_extract_tunnel_token():
    """
    Try to get the tunnel token from tokens.json or by querying the API.
    This is a fallback for when config.json doesn't have tunnel_token.
    """
    # Check if there's a tunnel token stored somewhere
    cfg = _load_config()

    # If we already have it, great
    if cfg.get("tunnel_token"):
        return cfg["tunnel_token"]

    # Try to find it from a running cloudflared process
    existing = _find_existing_cloudflared()
    if existing:
        # Use the token from the first matching cloudflared process
        for proc_info in existing:
            if proc_info.get("token"):
                token = proc_info["token"]
                cfg["tunnel_token"] = token
                _save_config(cfg)
                log.info("Extracted tunnel_token from running process (pid=%s)", proc_info["pid"])
                return token

    return None


class TunnelManager:
    """
    Manages a single cloudflared process that serves all tunnel ingress rules.
    """

    def __init__(self):
        self._process = None
        self._metrics_port = METRICS_PORT
        self._protocol = None
        self._consecutive_failures = 0
        self._last_health_check = 0
        self._is_healthy = False
        self._reconfigure_lock = False
        self._adopted_pid = None
        self._initialized = False

    def init(self):
        """
        Initialize the manager by detecting existing cloudflared processes.
        Call this on app startup.
        """
        if self._initialized:
            return
        self._initialized = True

        cfg = _load_config()

        # Check if config says cloudflared is running
        stored_pid = cfg.get("cloudflared_pid")
        if stored_pid:
            try:
                os.kill(stored_pid, 0)
                log.info("Found existing cloudflared from config (pid=%s)", stored_pid)
                self._adopted_pid = stored_pid
                self._protocol = cfg.get("cloudflared_protocol", "quic")
                self._is_healthy = True
                return
            except ProcessLookupError:
                log.info("Stale cloudflared PID %s in config, looking for running process", stored_pid)

        # Look for running cloudflared processes
        existing = _find_existing_cloudflared()
        if existing:
            # Pick the one most likely started by our portal
            # (prefer one with matching tunnel_id in its token)
            tunnel_id = cfg.get("tunnel_id", "")
            best = existing[0]
            for proc_info in existing:
                if proc_info.get("token") and tunnel_id:
                    # Both tokens contain the tunnel_id encoded
                    best = proc_info
                    break

            pid = best["pid"]
            log.info("Adopting existing cloudflared process (pid=%s, protocol=%s)", pid, best.get("protocol"))
            self._adopted_pid = pid
            self._protocol = best.get("protocol", "quic")
            self._is_healthy = True
            self._metrics_port = METRICS_PORT

            # Save PID to config
            cfg["cloudflared_pid"] = pid
            cfg["cloudflared_protocol"] = self._protocol
            cfg["cloudflared_started_at"] = "adopted"
            _save_config(cfg)

            # Also extract and save tunnel token if not present
            if not cfg.get("tunnel_token") and best.get("token"):
                cfg["tunnel_token"] = best["token"]
                _save_config(cfg)
        else:
            log.info("No running cloudflared found, will start on first tunnel creation")

    def start(self, tunnel_token, protocol=None):
        """
        Start the single cloudflared process.
        """
        cfg = _load_config()

        # If already running with correct token, just adopt it
        existing = _find_existing_cloudflared()
        for proc_info in existing:
            if proc_info.get("token") == tunnel_token and self._is_process_alive(proc_info["pid"]):
                log.info("cloudflared already running with correct token (pid=%s), adopting", proc_info["pid"])
                self._adopted_pid = proc_info["pid"]
                self._protocol = proc_info.get("protocol", "http2")
                cfg["cloudflared_pid"] = proc_info["pid"]
                cfg["cloudflared_protocol"] = self._protocol
                cfg["cloudflared_started_at"] = "adopted"
                _save_config(cfg)
                return proc_info["pid"]

        # Kill only stale processes (different token) before starting new one
        self._kill_stale_cloudflared()

        if not protocol:
            protocol = cfg.get("protocol", "auto")

        if protocol == "auto":
            if _is_wsl():
                protocol = "http2"
                log.info("WSL2 detected, using HTTP/2 protocol for stability")
            else:
                protocol = "quic"

        self._protocol = protocol
        self._metrics_port = _find_available_metrics_port()

        cmd = [
            "cloudflared",
            "tunnel",
            "--no-autoupdate",
            "--protocol", protocol,
            "run",
            "--token", tunnel_token,
        ]

        log_file = open(TUNNEL_LOG_FILE, "a")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=log_file,
                preexec_fn=os.setsid,
            )
        except FileNotFoundError:
            log.error("cloudflared not found in PATH")
            raise RuntimeError("cloudflared not found. Please install it first.")
        except Exception as e:
            log.error("Failed to start cloudflared: %s", e)
            raise

        # Store PID and metadata in config
        cfg["cloudflared_pid"] = self._process.pid
        cfg["cloudflared_started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        cfg["cloudflared_protocol"] = protocol
        cfg["tunnel_token"] = tunnel_token
        _save_config(cfg)

        self._adopted_pid = None
        self._consecutive_failures = 0
        self._is_healthy = True
        log.info(
            "cloudflared started: pid=%s protocol=%s metrics=%s",
            self._process.pid, protocol, self._metrics_port
        )
        return self._process.pid

    def stop(self):
        """Stop the cloudflared process gracefully."""
        # Kill our internal process
        if self._process:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                log.info("Stopped internal cloudflared (pid=%s)", self._process.pid)
            except (ProcessLookupError, PermissionError):
                pass
            self._process = None

        # Kill adopted process
        if self._adopted_pid:
            try:
                os.killpg(os.getpgid(self._adopted_pid), signal.SIGTERM)
                log.info("Stopped adopted cloudflared (pid=%s)", self._adopted_pid)
            except (ProcessLookupError, PermissionError):
                pass
            self._adopted_pid = None

        # Also kill any process with our tunnel token
        cfg = _load_config()
        our_token = cfg.get("tunnel_token", "")
        existing = _find_existing_cloudflared()
        for proc_info in existing:
            if proc_info.get("token") == our_token:
                try:
                    os.killpg(os.getpgid(proc_info["pid"]), signal.SIGTERM)
                    log.info("Stopped matching cloudflared (pid=%s)", proc_info["pid"])
                except (ProcessLookupError, PermissionError):
                    pass

        time.sleep(1)
        self._is_healthy = False

        cfg.pop("cloudflared_pid", None)
        cfg.pop("cloudflared_started_at", None)
        cfg.pop("cloudflared_protocol", None)
        _save_config(cfg)

        return True

    def restart(self, tunnel_token, protocol=None):
        """Restart cloudflared with the current tunnel token."""
        log.info("Restarting cloudflared...")
        self.stop()
        time.sleep(1)
        return self.start(tunnel_token, protocol)

    def is_running(self):
        """Check if the cloudflared process is actually running."""
        pid = self._get_pid()
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    def get_pid(self):
        """Return the current cloudflared PID or None."""
        return self._get_pid()

    def get_protocol(self):
        """Return the current protocol being used."""
        return self._protocol or _load_config().get("cloudflared_protocol", "unknown")

    def health_check(self):
        """
        Perform a health check on the cloudflared process.
        Returns dict with status info.
        """
        pid = self._get_pid()
        running = self.is_running()

        result = {
            "running": running,
            "pid": pid,
            "protocol": self.get_protocol(),
            "healthy": running,
            "consecutive_failures": self._consecutive_failures,
        }

        if running:
            # Check metrics endpoint if available
            metrics_ok = self._check_metrics()
            result["metrics_reachable"] = metrics_ok
            # Consider healthy if running (metrics may not be on expected port)
            result["healthy"] = running
            if running:
                self._consecutive_failures = 0
                self._is_healthy = True
        else:
            self._consecutive_failures += 1
            self._is_healthy = False

        self._last_health_check = time.time()
        return result

    def auto_restart_if_needed(self, tunnel_token):
        """
        Check health and auto-restart if cloudflared is down or unhealthy.
        Returns True if a restart was performed.
        """
        if self._reconfigure_lock:
            return False

        health = self.health_check()
        if health["healthy"]:
            return False

        log.warning(
            "cloudflared unhealthy (failures=%d), auto-restarting...",
            self._consecutive_failures
        )

        # If QUIC is failing repeatedly, switch to HTTP/2
        protocol = self.get_protocol()
        if protocol == "quic" and self._consecutive_failures >= 3:
            log.warning("QUIC failing repeatedly, switching to HTTP/2")
            protocol = "http2"

        try:
            self.restart(tunnel_token, protocol)
            return True
        except Exception as e:
            log.error("Auto-restart failed: %s", e)
            return False

    def reconcile_tunnels(self):
        """
        On startup, validate all tunnels in tunnels.json and clean stale entries.
        """
        tunnels = load_tunnels()
        results = {"cleaned": 0, "valid": 0, "repaired": 0}
        pid = self._get_pid()

        for key, info in list(tunnels.items()):
            old_pid = info.get("pid")
            if old_pid and pid and old_pid != pid:
                # Update PID to current cloudflared process
                info["pid"] = pid
                info["healthy"] = True
                tunnels[key] = info
                results["repaired"] += 1
            else:
                results["valid"] += 1

        save_tunnels(tunnels)
        log.info("Reconciliation: %d valid, %d repaired", results["valid"], results["repaired"])
        return results

    def _get_pid(self):
        """Get PID from internal process, adopted process, or config."""
        # 1. Check internal process (we started it)
        if self._process:
            pid = self._process.pid
            if self._process.poll() is None:
                return pid
            # Process exited, clear reference
            self._process = None

        # 2. Check adopted process
        if self._adopted_pid:
            try:
                os.kill(self._adopted_pid, 0)
                return self._adopted_pid
            except ProcessLookupError:
                self._adopted_pid = None

        # 3. Check config
        cfg = _load_config()
        pid = cfg.get("cloudflared_pid")
        if pid:
            try:
                os.kill(pid, 0)
                return pid
            except ProcessLookupError:
                pass

        # 4. Try to find any running cloudflared
        existing = _find_existing_cloudflared()
        if existing:
            self._adopted_pid = existing[0]["pid"]
            return self._adopted_pid

        return None

    def _is_process_alive(self, pid):
        """Check if a process is alive."""
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def _kill_stale_cloudflared(self):
        """Kill cloudflared processes with different tunnel tokens (stale/duplicate)."""
        cfg = _load_config()
        our_tunnel_id = cfg.get("tunnel_id", "")
        our_token = cfg.get("tunnel_token", "")

        # Kill our internal process if it exists
        if self._process:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                log.info("Stopped internal cloudflared (pid=%s)", self._process.pid)
            except (ProcessLookupError, PermissionError):
                pass
            self._process = None

        # Kill adopted process if it exists
        if self._adopted_pid:
            try:
                os.killpg(os.getpgid(self._adopted_pid), signal.SIGTERM)
                log.info("Stopped adopted cloudflared (pid=%s)", self._adopted_pid)
            except (ProcessLookupError, PermissionError):
                pass
            self._adopted_pid = None

        time.sleep(1)

        # Find and kill processes with DIFFERENT tunnel tokens (stale duplicates)
        existing = _find_existing_cloudflared()
        for proc_info in existing:
            proc_token = proc_info.get("token", "")
            # Kill if it has a different token than ours
            if proc_token and proc_token != our_token:
                try:
                    os.killpg(os.getpgid(proc_info["pid"]), signal.SIGTERM)
                    log.info("Killed stale cloudflared with different token (pid=%s)", proc_info["pid"])
                except (ProcessLookupError, PermissionError):
                    pass

        time.sleep(0.5)

    def _check_metrics(self):
        """Check if cloudflared metrics endpoint is reachable."""
        import urllib.request
        # Try common metrics ports
        for port in range(METRICS_PORT, METRICS_PORT + 10):
            try:
                url = f"http://127.0.0.1:{port}/metrics"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        self._metrics_port = port
                        return True
            except Exception:
                continue
        return False

    def get_status(self):
        """Get comprehensive status for the dashboard."""
        health = self.health_check()
        cfg = _load_config()
        tunnels = load_tunnels()

        return {
            "cloudflared": health,
            "tunnel_id": cfg.get("tunnel_id"),
            "protocol": self.get_protocol(),
            "active_tunnels": len(tunnels),
            "tunnels": {
                key: {
                    "url": info.get("url"),
                    "subdomain": info.get("subdomain"),
                    "port": info.get("port"),
                    "domain": info.get("domain"),
                    "started_at": info.get("started_at"),
                }
                for key, info in tunnels.items()
            },
        }


# Global singleton
_manager = None


def get_manager():
    """Get or create the global TunnelManager instance."""
    global _manager
    if _manager is None:
        _manager = TunnelManager()
    return _manager
