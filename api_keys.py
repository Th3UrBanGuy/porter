"""
API Key management for Porter.
Handles generation, validation, and lifecycle of API keys.
"""

import json
import os
import secrets
import time
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

KEY_PREFIX = "pk_"
KEY_LENGTH = 32


def _load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def _save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def generate_api_key(name):
    """Generate a new API key with the given name."""
    cfg = _load_config()
    if "api_keys" not in cfg:
        cfg["api_keys"] = {}

    key_id = secrets.token_hex(8)
    raw_key = secrets.token_hex(KEY_LENGTH)
    full_key = KEY_PREFIX + raw_key

    entry = {
        "name": name,
        "key_hash": _hash_key(full_key),
        "key_prefix": full_key[:12] + "...",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_used": None,
    }

    cfg["api_keys"][key_id] = entry
    _save_config(cfg)

    return {
        "id": key_id,
        "key": full_key,
        "name": name,
        "created_at": entry["created_at"],
    }


def validate_api_key(key):
    """Validate an API key. Returns True if valid."""
    if not key or not key.startswith(KEY_PREFIX):
        return False

    cfg = _load_config()
    api_keys = cfg.get("api_keys", {})
    key_hash = _hash_key(key)

    for kid, info in api_keys.items():
        if info.get("key_hash") == key_hash:
            info["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
            _save_config(cfg)
            return True

    return False


def list_api_keys():
    """List all API keys (without revealing full keys)."""
    cfg = _load_config()
    api_keys = cfg.get("api_keys", {})

    result = []
    for kid, info in api_keys.items():
        result.append({
            "id": kid,
            "name": info.get("name"),
            "key_prefix": info.get("key_prefix"),
            "created_at": info.get("created_at"),
            "last_used": info.get("last_used"),
        })
    return result


def delete_api_key(key_id):
    """Delete an API key by ID."""
    cfg = _load_config()
    api_keys = cfg.get("api_keys", {})

    if key_id in api_keys:
        del api_keys[key_id]
        cfg["api_keys"] = api_keys
        _save_config(cfg)
        return True
    return False


def rotate_api_key(key_id):
    """Rotate an API key, returning the new key."""
    cfg = _load_config()
    api_keys = cfg.get("api_keys", {})

    if key_id not in api_keys:
        return None

    old = api_keys[key_id]
    raw_key = secrets.token_hex(KEY_LENGTH)
    full_key = KEY_PREFIX + raw_key

    api_keys[key_id]["key_hash"] = _hash_key(full_key)
    api_keys[key_id]["key_prefix"] = full_key[:12] + "..."
    api_keys[key_id]["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    cfg["api_keys"] = api_keys
    _save_config(cfg)

    return {
        "id": key_id,
        "key": full_key,
        "name": old.get("name"),
        "created_at": api_keys[key_id]["created_at"],
    }


def _hash_key(key):
    """Hash an API key for secure storage."""
    import hashlib
    return hashlib.sha256(key.encode()).hexdigest()
