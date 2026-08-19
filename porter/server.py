"""
Server lifecycle manager — start, stop, restart, logs, status.
Cross-platform: works on Linux, macOS, Windows, Termux.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from porter import output as out
from porter.platform import (
    python_cmd, find_pid_by_port, kill_pid, is_pid_running,
    start_background_process, IS_WINDOWS, IS_LINUX, IS_TERMUX, OS_NAME,
)


BASE_DIR = Path(__file__).resolve().parent.parent
PID_FILE = BASE_DIR / "server.pid"
LOG_FILE = BASE_DIR / "portal.log"
PORTAL_LOG = BASE_DIR / "portal.log"
TUNNEL_LOG = BASE_DIR / "tunnel.log"
APP_FILE = BASE_DIR / "app.py"
RUN_SCRIPT = BASE_DIR / "run.sh"


def _read_pid():
    if PID_FILE.exists():
        try:
            return int(PID_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    # Fallback: find by port
    port = get_port()
    return find_pid_by_port(port)


def _write_pid(pid):
    PID_FILE.write_text(str(pid))


def _clear_pid():
    if PID_FILE.exists():
        PID_FILE.unlink()


def _is_running(pid):
    return is_pid_running(pid)


def _wait_for_port(port, timeout=30):
    """Block until the port is accepting connections."""
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        for host in ("0.0.0.0", "127.0.0.1"):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def get_port():
    # Try CLI config first (~/.porter/config.json)
    try:
        from porter.config import load_config
        cfg = load_config()
        if "port" in cfg:
            return int(cfg["port"])
    except Exception:
        pass
    # Fall back to project root config.json
    config = BASE_DIR / "config.json"
    if config.exists():
        try:
            with open(config) as f:
                return json.load(f).get("port", 7262)
        except Exception:
            pass
    return 7262


def start(port=None, mode="prod", workers=2, force=False):
    port = port or get_port()
    pid = _read_pid()

    if _is_running(pid) and not force:
        out.warning(f"Server already running (PID {pid})")
        out.info(f"  URL: http://localhost:{port}")
        return True

    # Kill any stale process occupying the port
    stale_pid = find_pid_by_port(port)
    if stale_pid and stale_pid != pid:
        out.warning(f"Killing stale process on port {port} (PID {stale_pid})...")
        try:
            kill_pid(stale_pid, force=True)
            time.sleep(1)
        except Exception:
            pass

    out.info(f"Starting Porter on port {port} ({OS_NAME})...")

    env = os.environ.copy()
    env["PORT"] = str(port)

    py = python_cmd()

    if mode == "dev":
        cmd = [py, str(APP_FILE)]
    else:
        if IS_WINDOWS and not IS_LINUX:
            # Windows: gunicorn doesn't work well, use waitress or flask
            try:
                import waitress
                cmd = [py, "-m", "waitress", f"--port={port}", "app:app"]
            except ImportError:
                # Fallback to Flask dev server
                cmd = [py, str(APP_FILE)]
                out.warning("gunicorn not available on Windows, using Flask dev server")
        else:
            # Check if gunicorn is available
            try:
                import gunicorn
                cmd = [
                    py, "-m", "gunicorn",
                    "--bind", f"0.0.0.0:{port}",
                    "--workers", str(workers),
                    "--worker-class", "gevent",
                    "--worker-connections", "1000",
                    "--timeout", "120",
                    "--keep-alive", "5",
                    "--log-level", "info",
                    "--access-logfile", "-",
                    "--error-logfile", "-",
                    "--preload",
                    "app:app",
                ]
            except ImportError:
                # Fallback to Flask dev server (Termux, minimal installs)
                cmd = [py, str(APP_FILE)]
                out.warning("gunicorn not available, using Flask dev server")

    log_path = str(LOG_FILE)
    if IS_WINDOWS and not IS_LINUX:
        # Windows: redirect to NUL if no log file
        stdout_dest = log_path if LOG_FILE.exists() else "NUL"
        stderr_dest = stdout_dest
    else:
        stdout_dest = log_path if LOG_FILE.exists() else subprocess.DEVNULL
        stderr_dest = stdout_dest

    # Open log files properly to avoid file descriptor leaks
    stdout_file = None
    stderr_file = None
    if not (IS_WINDOWS and not IS_LINUX):
        if LOG_FILE.exists() or mode == "prod":
            stdout_file = open(log_path, "a")
            stderr_file = stdout_file
        else:
            stdout_file = subprocess.DEVNULL
            stderr_file = subprocess.DEVNULL

    try:
        proc_pid = start_background_process(
            cmd,
            cwd=str(BASE_DIR),
            env=env,
            stdout_file=stdout_dest if (IS_WINDOWS and not IS_LINUX) else stdout_file,
            stderr_file=stderr_dest if (IS_WINDOWS and not IS_LINUX) else stderr_file,
        )
    finally:
        # Close file handles if we opened them
        if stdout_file is not None and stdout_file != subprocess.DEVNULL:
            try:
                stdout_file.close()
            except Exception:
                pass

    _write_pid(proc_pid)
    out.info(f"  PID: {proc_pid}")

    if _wait_for_port(port, timeout=15):
        out.success(f"Server running at http://localhost:{port}")
        return True
    else:
        out.warning("Server may still be starting (timeout waiting for port)")
        return True


def stop():
    pid = _read_pid()
    if not _is_running(pid):
        out.info("Server not running")
        _clear_pid()
        return True

    out.info(f"Stopping server (PID {pid})...")
    try:
        if IS_WINDOWS and not IS_LINUX:
            kill_pid(pid, force=False)
            time.sleep(1)
            if is_pid_running(pid):
                kill_pid(pid, force=True)
        else:
            os.kill(pid, signal.SIGTERM)
            # Wait up to 5s for graceful shutdown
            for _ in range(10):
                if not is_pid_running(pid):
                    break
                time.sleep(0.5)
            # Force kill if still running
            if is_pid_running(pid):
                kill_pid(pid, force=True)
                time.sleep(0.5)
    except OSError:
        pass

    _clear_pid()
    out.success("Server stopped")
    return True


def restart(port=None, mode="prod", workers=2):
    stop()
    time.sleep(1)
    return start(port=port, mode=mode, workers=workers, force=True)


def status():
    pid = _read_pid()
    running = _is_running(pid)
    port = get_port()

    out.header("Server Status")

    if running:
        out.table_row("Status", f"{out.OK} Running")
        out.table_row("PID", str(pid))
        out.table_row("Port", str(port))
        out.table_row("URL", f"http://localhost:{port}")
        out.table_row("Platform", OS_NAME)
    else:
        out.table_row("Status", f"{out.ERR} Stopped")
        out.table_row("Platform", OS_NAME)

    # Check cloudflared
    try:
        cf_pid_file = BASE_DIR / "config.json"
        if cf_pid_file.exists():
            with open(cf_pid_file) as f:
                cfg = json.load(f)
            cf_pid = cfg.get("cloudflared_pid")
            if cf_pid and _is_running(cf_pid):
                out.table_row("Cloudflared", f"{out.OK} Running (PID {cf_pid})")
            else:
                out.table_row("Cloudflared", f"{out.ERR} Stopped")
    except Exception:
        pass

    print()
    return running


def logs(lines=50, follow=False, which="portal"):
    if which == "portal" or which == "app":
        log_path = PORTAL_LOG
    elif which == "tunnel" or which == "cf":
        log_path = TUNNEL_LOG
    else:
        out.error(f"Unknown log: {which}")
        out.info("Available: portal, tunnel")
        return

    if not log_path.exists():
        out.warning(f"Log file not found: {log_path}")
        return

    if follow:
        if IS_WINDOWS and not IS_LINUX:
            # Windows: use PowerShell Get-Content -Wait
            try:
                subprocess.run(
                    ["powershell", "-Command", f"Get-Content -Wait -Tail {lines} '{log_path}'"],
                )
            except (KeyboardInterrupt, FileNotFoundError, subprocess.SubprocessError):
                pass
        else:
            try:
                subprocess.run(["tail", "-f", "-n", str(lines), str(log_path)])
            except (KeyboardInterrupt, FileNotFoundError, subprocess.SubprocessError):
                # Fallback: read file manually if tail not available
                try:
                    with open(log_path) as f:
                        all_lines = f.readlines()
                        for line in all_lines[-lines:]:
                            print(line, end="")
                except Exception:
                    pass
    else:
        # Read last N lines
        try:
            with open(log_path) as f:
                all_lines = f.readlines()
                for line in all_lines[-lines:]:
                    print(line, end="")
        except Exception as e:
            out.error(f"Failed to read logs: {e}")


def install_deps():
    req = BASE_DIR / "requirements.txt"
    if not req.exists():
        out.warning("No requirements.txt found")
        return False

    out.info("Installing dependencies...")
    from porter.platform import pip_install_cmd
    pip = pip_install_cmd()
    result = subprocess.run(
        pip + ["-r", str(req), "--quiet"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode == 0:
        out.success("Dependencies installed")
        return True
    else:
        out.error(f"pip install failed: {result.stderr[:200]}")
        return False
