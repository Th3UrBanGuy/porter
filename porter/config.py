"""
CLI configuration management.
Stores server URL and auth credentials in ~/.porter/config.json.
"""

import json
import os
from pathlib import Path

try:
    _home = Path.home()
except RuntimeError:
    _home = Path(os.environ.get("HOME", os.environ.get("USERPROFILE", ".")))

CONFIG_DIR = _home / ".porter"
CONFIG_FILE = CONFIG_DIR / "config.json"


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}
    return {}


def save_config(cfg):
    ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def get_server_url():
    cfg = load_config()
    return cfg.get("server_url", "http://localhost:7262")


def get_api_key():
    cfg = load_config()
    return cfg.get("api_key")


def get_passcode():
    cfg = load_config()
    return cfg.get("passcode")


def set_server_url(url):
    cfg = load_config()
    cfg["server_url"] = url.rstrip("/")
    save_config(cfg)


def set_api_key(key):
    cfg = load_config()
    cfg["api_key"] = key
    save_config(cfg)


def set_passcode(passcode):
    cfg = load_config()
    cfg["passcode"] = passcode
    save_config(cfg)


def is_configured():
    cfg = load_config()
    return bool(cfg.get("server_url"))
