# Implementation Plan: API System + CLI + Documentation

## Overview

Add API key authentication, a CLI package (`porter` command), fix the Danger Zone HTML bug, and update documentation.

---

## Phase 1: API Key System

### 1.1 API Key Model
- Store API keys in `config.json` under `api_keys` object
- Each key has: `key` (prefix `pk_` + 32-char hex), `name`, `created_at`, `last_used`
- Generate with `secrets.token_hex(16)` → prefix with `pk_`

### 1.2 New File: `api_keys.py`
```python
# Functions:
# - generate_api_key(name) -> dict
# - validate_api_key(key) -> bool
# - list_api_keys() -> list
# - delete_api_key(key_id) -> bool
# - rotate_api_key(key_id) -> dict
```

### 1.3 API Key Endpoints (app.py)
| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/keys` | List all API keys |
| `POST` | `/api/keys` | Create new API key |
| `DELETE` | `/api/keys/<key_id>` | Delete API key |
| `POST` | `/api/keys/<key_id>/rotate` | Rotate API key |

### 1.4 Auth Middleware Update
Update `@passcode_required` decorator to also accept:
- `X-API-Key` header → validate against stored keys
- Update `last_used` timestamp on successful auth

---

## Phase 2: CLI Package

### 2.1 Package Structure
```
porter/
├── __init__.py          # Version, metadata
├── __main__.py          # Entry point: python -m porter
├── cli.py               # Main CLI logic (argparse)
├── api.py               # API client (httpx)
├── config.py            # Config management
├── output.py            # Formatted output (tables, colors)
setup.py                 # Package setup with entry_points
```

### 2.2 CLI Commands
| Command | Description | API Endpoint |
|---------|-------------|--------------|
| `porter status` | Show system status | `GET /api/tunnel/health` |
| `porter tunnels` | List all tunnels | `GET /api/tunnels` |
| `porter tunnel create <subdomain> <port>` | Create tunnel | `POST /api/tunnel/create` |
| `porter tunnel stop <subdomain>` | Stop tunnel | `POST /api/tunnel/stop/<key>` |
| `porter tunnel restart` | Restart cloudflared | `POST /api/tunnel/restart` |
| `porter domains` | List domains | `GET /api/domains` |
| `porter setup` | Initial setup wizard | Interactive |
| `porter keys list` | List API keys | `GET /api/keys` |
| `porter keys create <name>` | Create API key | `POST /api/keys` |
| `porter keys delete <key_id>` | Delete API key | `DELETE /api/keys/<id>` |

### 2.3 CLI Auth
- First run: prompt for server URL and passcode
- Store in `~/.porter/config.json`
- Or use `PORTER_URL` and `PORTER_API_KEY` env vars
- Pass via `X-API-Key` or `X-Passcode` header

### 2.4 Entry Point
```python
# setup.py
entry_points={
    'console_scripts': [
        'porter=porter.cli:main',
    ],
}
```

---

## Phase 3: Fix Danger Zone

### 3.1 HTML Fix
**File:** `templates/setup.html` lines 181-182
```html
<!-- BEFORE (duplicate) -->
<h3>Danger Zone</h3>
<h3>Danger Zone</h3>

<!-- AFTER (fixed) -->
<h3>Danger Zone</h3>
```

---

## Phase 4: Documentation Updates

### 4.1 README.md Updates
- Add API Keys section (setup, usage, examples)
- Add CLI section (installation, commands, examples)
- Update API reference with key-based auth
- Add quick start for CLI

### 4.2 docs.html Updates
- Add API Keys section
- Add CLI documentation section
- Update API reference with key auth examples

### 4.3 Public UI Updates
- Add API Keys management section in Settings page
- Add CLI download/install instructions in docs

---

## Phase 5: Settings UI Update

### 5.1 API Keys Section in setup.html
Add new section after Protocol settings, before Danger Zone:
- List existing API keys (masked)
- Create new key form
- Delete key button
- Copy key to clipboard

---

## Implementation Order

1. Create `api_keys.py` module
2. Update `app.py` auth middleware + API key routes
3. Fix `setup.html` Danger Zone duplicate
4. Add API Keys section to `setup.html`
5. Create `porter/` CLI package
6. Create `setup.py` for package installation
7. Update `README.md` with new features
8. Update `docs.html` with CLI and API key docs
9. Test all features

---

## Files to Create
- `api_keys.py` - API key management module
- `porter/__init__.py` - Package init
- `porter/__main__.py` - Entry point
- `porter/cli.py` - CLI logic
- `porter/api.py` - API client
- `porter/config.py` - Config management
- `porter/output.py` - Formatted output
- `setup.py` - Package setup

## Files to Modify
- `app.py` - Auth middleware + API key routes
- `templates/setup.html` - Fix Danger Zone + add API keys UI
- `README.md` - Documentation updates
- `templates/docs.html` - Documentation updates
- `config.json` - Add api_keys field (handled by code)
