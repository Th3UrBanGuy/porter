"""
Cross-platform detection and shell abstractions.

Works on: Linux, macOS, Windows (PowerShell), Termux (Android).
Provides a unified interface for OS-specific operations.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
#  Platform detection
# ═══════════════════════════════════════════════════════════════

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform == "linux"
IS_TERMUX = False

# Detect Termux: Android with /data/data/com.termux
if IS_LINUX:
    try:
        # Check for Termux environment (most reliable)
        if os.environ.get("SHELL", "").endswith("sh") and os.path.exists("/data/data/com.termux"):
            IS_TERMUX = True
        elif os.path.exists("/data/data/com.termux") or os.path.exists("/data/user/0/com.termux"):
            IS_TERMUX = True
        elif os.environ.get("TERMUX_VERSION"):
            IS_TERMUX = True
    except Exception:
        pass

if IS_WINDOWS:
    # Distinguish WSL from native Windows
    # Check env var first (fast), fall back to uname
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("IS_WSL"):
        IS_LINUX = True
        IS_WINDOWS = False
    else:
        try:
            result = subprocess.run(
                ["uname", "-r"], capture_output=True, text=True, timeout=5
            )
            if "microsoft" in result.stdout.lower():
                IS_LINUX = True
                IS_WINDOWS = False
        except Exception:
            pass

OS_NAME = "termux" if IS_TERMUX else ("windows" if IS_WINDOWS else ("macos" if IS_MACOS else "linux"))
ARCH = platform.machine()


# ═══════════════════════════════════════════════════════════════
#  Python executable
# ═══════════════════════════════════════════════════════════════

def python_cmd():
    """Get the correct Python command for this platform."""
    if IS_WINDOWS and not IS_LINUX:
        # On native Windows, try python first
        for cmd in ["python", "python3", "py"]:
            if shutil.which(cmd):
                return cmd
        return "python3"
    else:
        # Linux, macOS, Termux, WSL
        for cmd in ["python3", "python"]:
            if shutil.which(cmd):
                return cmd
        return "python3"


def pip_cmd():
    """Get the correct pip command for this platform."""
    py = python_cmd()
    # Try module invocation first (most reliable)
    try:
        result = subprocess.run(
            [py, "-m", "pip", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return [py, "-m", "pip"]
    except Exception:
        pass

    # Try direct pip commands
    for cmd in ["pip3", "pip"]:
        if shutil.which(cmd):
            return [cmd]

    return [py, "-m", "pip"]


def pip_install_cmd():
    """Get pip install command with --break-system-packages if needed."""
    cmd = pip_cmd() + ["install"]
    # Detect PEP 668 (Debian/Ubuntu 23.04+)
    try:
        py = python_cmd()
        result = subprocess.run(
            [py, "-m", "pip", "install", "--dry-run", "nonexistent-package-porter-test"],
            capture_output=True, text=True, timeout=10,
        )
        if "break-system-packages" in (result.stderr or ""):
            cmd.append("--break-system-packages")
    except Exception:
        pass
    return cmd


# ═══════════════════════════════════════════════════════════════
#  Shell commands
# ═══════════════════════════════════════════════════════════════

def run(cmd, **kwargs):
    """Run a shell command with defaults."""
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 30)
    return subprocess.run(cmd, **kwargs)


def find_pid_by_port(port):
    """Find the PID listening on a given port. Cross-platform."""
    port = int(port)

    if IS_WINDOWS and not IS_LINUX:
        # Native Windows: use netstat
        try:
            result = run(["netstat", "-ano"], timeout=10)
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        return int(parts[-1])
        except Exception:
            pass
        # Fallback: PowerShell
        try:
            result = run(
                ["powershell", "-Command",
                 f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object OwningProcess"],
                timeout=10,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    return int(line)
        except Exception:
            pass

    elif IS_MACOS:
        # macOS: use lsof
        try:
            result = run(["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-t"], timeout=10)
            if result.stdout.strip():
                return int(result.stdout.strip().split("\n")[0])
        except Exception:
            pass

    else:
        # Linux / Termux / WSL: try ss first, then lsof, then netstat
        # ss (iproute2)
        try:
            result = run(["ss", "-tlnp", f"sport = :{port}"], timeout=10)
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTEN" in line:
                    import re
                    m = re.search(r'pid=(\d+)', line)
                    if m:
                        return int(m.group(1))
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        # lsof fallback
        try:
            result = run(["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-t"], timeout=10)
            if result.stdout.strip():
                return int(result.stdout.strip().split("\n")[0])
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        # netstat fallback (Termux often has this)
        try:
            result = run(["netstat", "-tlnp"], timeout=10)
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTEN" in line:
                    import re
                    m = re.search(r'(\d+)/', line)
                    if m:
                        return int(m.group(1))
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

    return None


def list_listening_ports():
    """List all listening ports. Returns list of (port, protocol, pid) tuples."""
    ports = []

    if IS_WINDOWS and not IS_LINUX:
        try:
            result = run(["netstat", "-ano"], timeout=10)
            for line in result.stdout.splitlines():
                if "LISTENING" in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        local = parts[1]
                        proto = parts[0]
                        pid = parts[-1] if parts[-1].isdigit() else None
                        port_str = local.split(":")[-1] if ":" in local else local
                        if port_str.isdigit():
                            ports.append((int(port_str), proto.lower(), int(pid) if pid else None))
        except Exception:
            pass

    elif IS_MACOS:
        try:
            result = run(["lsof", "-iTCP", "-sTCP:LISTEN", "-n", "-P"], timeout=10)
            for line in result.stdout.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 9:
                    addr = parts[8]
                    if ":" in addr:
                        port_str = addr.split(":")[-1]
                        if port_str.isdigit():
                            pid = parts[1] if parts[1].isdigit() else None
                            proto = parts[7].lower() if len(parts) > 7 else "tcp"
                            ports.append((int(port_str), proto, int(pid) if pid else None))
        except Exception:
            pass

    else:
        # ss (Linux/Termux/WSL)
        try:
            result = run(["ss", "-tlnp"], timeout=10)
            for line in result.stdout.splitlines():
                if "LISTEN" in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        local = parts[3]
                        port_str = local.split(":")[-1] if ":" in local else local
                        if port_str.isdigit():
                            import re
                            m = re.search(r'pid=(\d+)', line)
                            pid = int(m.group(1)) if m else None
                            proto = "tcp"
                            ports.append((int(port_str), proto, pid))
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
            pass

        # netstat fallback (Termux)
        if not ports:
            try:
                result = run(["netstat", "-tlnp"], timeout=10)
                for line in result.stdout.splitlines():
                    if "LISTEN" in line:
                        parts = line.split()
                        if len(parts) >= 4:
                            local = parts[3]
                            port_str = local.split(":")[-1] if ":" in local else local
                            if port_str.isdigit():
                                import re
                                m = re.search(r'(\d+)/', line)
                                pid = int(m.group(1)) if m else None
                                ports.append((int(port_str), "tcp", pid))
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass

    return ports


def kill_pid(pid, force=False):
    """Kill a process by PID. Cross-platform."""
    import signal

    if IS_WINDOWS and not IS_LINUX:
        try:
            cmd = ["taskkill", "/PID", str(pid)]
            if force:
                cmd.append("/F")
            run(cmd, timeout=10)
            return True
        except Exception:
            return False
    else:
        try:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(pid, sig)
            return True
        except OSError:
            return False


def is_pid_running(pid):
    """Check if a process is running. Cross-platform."""
    if pid is None:
        return False

    if IS_WINDOWS and not IS_LINUX:
        try:
            result = run(["tasklist", "/FI", f"PID eq {pid}"], timeout=10)
            return str(pid) in result.stdout
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


# ═══════════════════════════════════════════════════════════════
#  Package management
# ═══════════════════════════════════════════════════════════════

def install_system_package(package):
    """Install a system package using the platform's package manager."""
    if IS_TERMUX:
        return run(["pkg", "install", "-y", package], timeout=120).returncode == 0
    elif IS_MACOS:
        if shutil.which("brew"):
            return run(["brew", "install", package], timeout=120).returncode == 0
        return False
    elif IS_WINDOWS and not IS_LINUX:
        # Windows: try winget, then choco, then scoop
        for mgr in [
            ["winget", "install", "--id", package, "--accept-source-agreements", "--accept-package-agreements"],
            ["choco", "install", package, "-y"],
            ["scoop", "install", package],
        ]:
            if shutil.which(mgr[0]):
                return run(mgr, timeout=120).returncode == 0
        return False
    else:
        # Linux: try apt, dnf, yum, pacman
        for mgr, install_cmd in [
            ("apt", ["apt", "install", "-y", package]),
            ("dnf", ["dnf", "install", "-y", package]),
            ("yum", ["yum", "install", "-y", package]),
            ("pacman", ["pacman", "-S", "--noconfirm", package]),
        ]:
            if shutil.which(mgr):
                # Try without sudo first (root in Docker/containers), then with sudo
                if os.geteuid() == 0:
                    return run(install_cmd, timeout=120).returncode == 0
                else:
                    return run(["sudo"] + install_cmd, timeout=120).returncode == 0
        return False


def ensure_python():
    """Ensure Python 3 is available. Returns the python command to use."""
    py = python_cmd()
    if py:
        return py

    # Try to install Python
    if IS_TERMUX:
        install_system_package("python")
    elif IS_MACOS:
        install_system_package("python3")
    elif IS_WINDOWS and not IS_LINUX:
        install_system_package("Python.Python.3.12")

    return python_cmd() or "python3"


def ensure_pip():
    """Ensure pip is available. Returns the pip command list."""
    return pip_cmd()


def ensure_cloudflared():
    """Ensure cloudflared is installed. Returns True if available."""
    if shutil.which("cloudflared"):
        return True

    # Termux: no official cloudflared, but we can use the binary
    if IS_TERMUX:
        arch = ARCH
        if arch in ("aarch64", "arm64"):
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
        elif arch in ("armv7l", "armv7", "armhf"):
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm"
        else:
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"

        try:
            home = Path.home()
        except RuntimeError:
            home = Path(os.environ.get("HOME", os.environ.get("USERPROFILE", ".")))
        dest = home / ".local" / "bin" / "cloudflared"
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            run(["curl", "-fsSL", url, "-o", str(dest)], timeout=60)
            dest.chmod(0o755)
            # Add to PATH if needed
            local_bin = str(dest.parent)
            if local_bin not in os.environ.get("PATH", ""):
                os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"
            return True
        except Exception:
            return False

    elif IS_WINDOWS and not IS_LINUX:
        # Windows: download from GitHub releases
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        dest = Path.home() / "cloudflared.exe"
        try:
            run(["curl", "-fsSL", url, "-o", str(dest)], timeout=60)
            return True
        except Exception:
            try:
                import urllib.request
                urllib.request.urlretrieve(url, str(dest))
                return True
            except Exception:
                return False

    elif IS_MACOS:
        if shutil.which("brew"):
            return run(["brew", "install", "cloudflared"], timeout=120).returncode == 0

    else:
        # Linux
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
        if ARCH in ("aarch64", "arm64"):
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
        dest = Path.home() / ".local" / "bin" / "cloudflared"
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            run(["curl", "-fsSL", url, "-o", str(dest)], timeout=60)
            dest.chmod(0o755)
            local_bin = str(dest.parent)
            if local_bin not in os.environ.get("PATH", ""):
                os.environ["PATH"] = f"{local_bin}:{os.environ.get('PATH', '')}"
            return True
        except Exception:
            return False

    return False


# ═══════════════════════════════════════════════════════════════
#  Process management
# ═══════════════════════════════════════════════════════════════

def start_background_process(cmd, cwd=None, env=None, stdout_file=None, stderr_file=None):
    """Start a process in the background. Returns PID."""
    kwargs = {
        "cwd": cwd,
        "env": env,
        "start_new_session": not IS_WINDOWS,  # detach from terminal
    }

    if stdout_file:
        kwargs["stdout"] = open(stdout_file, "a") if isinstance(stdout_file, (str, Path)) else stdout_file
    if stderr_file:
        kwargs["stderr"] = open(stderr_file, "a") if isinstance(stderr_file, (str, Path)) else stderr_file

    if IS_WINDOWS and not IS_LINUX:
        # Windows: use CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        kwargs.pop("start_new_session", None)

    proc = subprocess.Popen(cmd, **kwargs)
    return proc.pid


def open_browser(url):
    """Open a URL in the default browser. Cross-platform."""
    import webbrowser
    try:
        webbrowser.open(url)
        return True
    except Exception:
        pass

    if IS_WINDOWS and not IS_LINUX:
        try:
            subprocess.Popen(["cmd", "/c", "start", url], shell=True)
            return True
        except Exception:
            pass
    elif IS_MACOS:
        try:
            subprocess.Popen(["open", url])
            return True
        except Exception:
            pass
    else:
        try:
            subprocess.Popen(["xdg-open", url])
            return True
        except Exception:
            pass
        try:
            subprocess.Popen(["termux-open-url", url])
            return True
        except Exception:
            pass

    return False


# ═══════════════════════════════════════════════════════════════
#  PATH management
# ═══════════════════════════════════════════════════════════════

def get_install_dirs():
    """Get platform-specific install directories."""
    home = Path.home()

    if IS_TERMUX:
        return {
            "home": home / "porter",
            "bin": home / ".local" / "bin",
            "config": home / ".porter",
            "data": home / ".porter",
        }
    elif IS_WINDOWS and not IS_LINUX:
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return {
            "home": home / "porter",
            "bin": appdata / "Python" / "Scripts",
            "config": home / ".porter",
            "data": home / ".porter",
        }
    else:
        return {
            "home": home / "porter",
            "bin": home / ".local" / "bin",
            "config": home / ".porter",
            "data": home / ".porter",
        }


def add_to_path(directory):
    """Add a directory to PATH for the current session and persist it."""
    directory = str(directory)
    sep = ";" if (IS_WINDOWS and not IS_LINUX) else ":"

    # Current session
    if directory not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{directory}{sep}{os.environ.get('PATH', '')}"

    # Persist
    if IS_WINDOWS and not IS_LINUX:
        # PowerShell: use [Environment]::SetEnvironmentVariable
        try:
            subprocess.run([
                "powershell", "-Command",
                f'[Environment]::SetEnvironmentVariable("Path", "{directory};$env:Path", "User")'
            ], timeout=10)
        except Exception:
            pass
    else:
        # Shell: add to .bashrc / .zshrc / .profile
        shell = os.environ.get("SHELL", "")
        if "zsh" in shell:
            rc_file = home / ".zshrc"
        elif "fish" in shell:
            rc_file = home / ".config" / "fish" / "config.fish"
        elif "csh" in shell or "tcsh" in shell:
            rc_file = home / ".cshrc"
        elif "dash" in shell or "ash" in shell:
            rc_file = home / ".profile"
        else:
            rc_file = home / ".bashrc"

        # Fish uses different syntax
        if "fish" in shell:
            export_line = f"fish_add_path {directory}"
        else:
            export_line = f'export PATH="{directory}:$PATH"'

        if IS_TERMUX:
            rc_file = home / ".bashrc"

        try:
            existing = rc_file.read_text() if rc_file.exists() else ""
            if directory not in existing:
                with open(rc_file, "a") as f:
                    f.write(f"\n# Porter CLI\n{export_line}\n")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
#  Info
# ═══════════════════════════════════════════════════════════════

def platform_info():
    """Return a dict of platform information."""
    return {
        "os": OS_NAME,
        "arch": ARCH,
        "python": python_cmd(),
        "is_termux": IS_TERMUX,
        "is_windows": IS_WINDOWS,
        "is_macos": IS_MACOS,
        "is_linux": IS_LINUX,
        "has_ss": shutil.which("ss") is not None,
        "has_lsof": shutil.which("lsof") is not None,
        "has_netstat": shutil.which("netstat") is not None,
        "has_brew": shutil.which("brew") is not None,
        "has_cloudflared": shutil.which("cloudflared") is not None,
    }
