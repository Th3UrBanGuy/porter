# Porter

> Self-hosted Cloudflare Tunnel portal. Expose any local service to the internet in seconds — no DNS config, no API tokens, no hassle.

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.x-green?logo=flask&logoColor=white)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-orange)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production-brightgreen)]()

![Porter Dashboard](https://img.shields.io/badge/Dashboard-Modern_UI-6366f1?style=for-the-badge)

---

## What is Porter?

Porter is a web app that lets you expose local services (web servers, APIs, dashboards, databases) to the internet using [Cloudflare Tunnels](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/). Enter a port, pick a subdomain, click **Launch** — done.

### Why?

| Without Porter | With Porter |
|---------------|-------------|
| Manual DNS CNAME setup | Automatic |
| Zero Trust dashboard navigation | One-click |
| cloudflared token management | Automatic |
| 10-15 minutes per service | 5 seconds |

---

## Features

- **Cross-Platform** — Linux, macOS, Windows, Termux (Android). One installer, one command.
- **OAuth 2.1 + PKCE** — No API tokens. One-click Cloudflare authorization.
- **MCP Integration** — All API calls go through Cloudflare's MCP server.
- **One-Click Deploy** — Port + subdomain → live URL.
- **GUI Command** — `porter gui` opens the dashboard in your browser instantly.
- **Real-Time Progress** — SSE-powered step-by-step progress tracking.
- **Auto Port Detection** — Scans for running services (cross-platform).
- **Passcode Protection** — SHA-256 hashed passcode security.
- **Multi-Domain** — Supports multiple Cloudflare zones.
- **PWA Support** — Install as a native app on mobile/desktop.
- **Light/Dark Theme** — Modern UI with glass morphism.
- **Mobile Optimized** — Responsive design with touch-friendly controls.

---

## Quick Start

### One-Line Install (Any Platform)

**Linux / macOS / Git Bash / WSL / Termux:**
```bash
curl -fsSL https://tinyurl.com/2ctqvyfp | bash
```

**Windows PowerShell (two-step, most reliable):**
```powershell
curl.exe -fsSL https://tinyurl.com/2ctqvyfp -o install.sh
bash install.sh
```

**Windows PowerShell (one-line):**
```powershell
curl.exe -fsSL https://tinyurl.com/2ctqvyfp | bash
```

Works on:
- **Linux** (Debian/Ubuntu, RHEL/Fedora, Arch)
- **macOS** (Homebrew)
- **Windows** (Git Bash, WSL, MSYS2, PowerShell)
- **Termux** (Android)

The installer auto-detects your platform, installs Python, pip, cloudflared, and all dependencies. No manual setup needed.

**Environment variables:**
```bash
PORTER_PORT=8080        # Custom port (default: 7262)
PORTER_PASSCODE=123456  # Custom passcode (default: auto-generated)
PORTER_DIR=/opt/porter  # Custom install directory (default: ~/.porter)
```

### Manual Install

```bash
# Clone
git clone https://github.com/Th3UrBanGuy/porter.git
cd porter

# Install dependencies
pip install -r requirements.txt

# Install CLI
pip install -e .

# Start
python3 app.py
```

### First-Time Setup

**Option 1: Via CLI (fully terminal-based)**
```bash
# Open the dashboard in your browser
porter gui

# Or connect Cloudflare from terminal
porter cloudflare connect

# Create your first tunnel
porter tunnel create panel 7262
```

**Option 2: Via Browser**
1. Open `http://YOUR_SERVER:7262`
2. Click **Connect Cloudflare** → authorize in browser
3. Set a passcode
4. Enter a subdomain + port → **Launch**

---

## How It Works

```
User enters subdomain + port
        │
        ▼
┌──────────────────────┐
│  Porter Backend      │
│  (Flask + Python)    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Cloudflare MCP      │  ← OAuth-authenticated API proxy
│  (mcp.cloudflare.com)│
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  Cloudflare Edge     │  ← DNS, SSL, DDoS protection
│  (Global CDN)        │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  cloudflared         │  ← Encrypted tunnel on your server
│  (Your VPS)          │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  localhost:PORT      │  ← Your service
└──────────────────────┘
```

### Tunnel Creation Steps

1. **DNS Cleanup** — Remove conflicting DNS records
2. **Tunnel Setup** — Create/update Cloudflare tunnel
3. **Hostname Config** — Map subdomain to local port
4. **DNS Record** — Create CNAME: `sub.domain → tunnel`
5. **Start cloudflared** — Launch encrypted tunnel

---

## Configuration

### config.json

```json
{
  "passcode_hash": "sha256_hash",
  "domain": "yourdomain.com",
  "domains": ["yourdomain.com", "another.com"],
  "account_id": "your_account_id",
  "tunnel_id": "tunnel_uuid"
}
```

### Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `7262` | Portal port (edit in `app.py`) |

---

## API Reference

### Pages

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Landing page / Dashboard |
| `GET/POST` | `/login` | Passcode login |
| `GET/POST` | `/setup` | Setup wizard |
| `GET` | `/docs` | Documentation |
| `GET` | `/logout` | Clear session |

### OAuth

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/auth/cloudflare` | Start OAuth flow |
| `GET` | `/auth/callback` | OAuth callback |
| `POST` | `/auth/disconnect` | Remove tokens |

### API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/ports/scan` | Scan for open ports |
| `GET` | `/api/tunnels` | List active tunnels |
| `POST` | `/api/tunnel/create` | Create tunnel (sync) |
| `POST` | `/api/tunnel/create/stream` | Create tunnel (SSE) |
| `POST` | `/api/tunnel/stop/<key>` | Stop tunnel |
| `GET` | `/api/tunnel/health` | Health check |
| `POST` | `/api/tunnel/restart` | Restart cloudflared |
| `GET` | `/api/domains` | List Cloudflare zones |
| `POST` | `/api/domains/active` | Switch active domain |
| `GET` | `/api/keys` | List API keys |
| `POST` | `/api/keys` | Create API key |
| `DELETE` | `/api/keys/<id>` | Delete API key |
| `POST` | `/api/keys/<id>/rotate` | Rotate API key |
| `GET` | `/api/status` | Public status (no auth) |

---

## File Structure

```
porter/
├── app.py                    # Flask backend (routes, SSE, tunnel mgmt)
├── api_keys.py               # API key management module
├── cloudflare_client.py      # OAuth 2.1 + PKCE, MCP orchestration
├── tunnel_manager.py         # Single-process cloudflared manager
├── installer                 # Universal installer (Linux/macOS/Windows/Termux)
├── setup.py                  # CLI package installation
├── config.json               # Portal config (auto-created)
├── tokens.json               # OAuth tokens (auto-created)
├── tunnels.json              # Active tunnel tracking
├── requirements.txt          # flask>=3.0, httpx>=0.25
├── porter/                   # Cross-platform CLI package
│   ├── __init__.py           # v2.0.0
│   ├── __main__.py           # Entry: python -m porter
│   ├── cli.py                # Unified CLI (all commands)
│   ├── platform.py           # OS detection & shell abstractions
│   ├── api.py                # HTTP client for server API
│   ├── cloudflare.py         # CLI-based OAuth flow
│   ├── config.py             # Config management (~/.porter/)
│   ├── output.py             # Colored/formatted output
│   └── server.py             # Server lifecycle (start/stop/logs)
├── static/
│   ├── manifest.json         # PWA manifest
│   ├── sw.js                 # Service worker
│   ├── icon-192.png          # App icon 192x192
│   ├── icon-512.png          # App icon 512x512
│   └── icon.svg              # SVG icon source
└── templates/
    ├── index.html            # Landing page
    ├── dashboard.html        # Main dashboard
    ├── login.html            # Login page
    ├── setup.html            # Setup wizard
    └── docs.html             # Documentation
```

---

## Security

- **Passcode** — SHA-256 hashed, stored in `config.json`
- **API Keys** — Generate scoped keys for CLI/script access (via `X-API-Key` header)
- **OAuth** — Tokens scoped to MCP server, auto-refresh
- **Sessions** — Flask session cookies
- **MCP** — API calls proxied through Cloudflare (no direct token exposure)

### Best Practices

1. Use a reverse proxy (nginx/caddy) with TLS
2. Restrict firewall access to port 7262
3. Use a strong passcode
4. Use API keys for programmatic access instead of passcodes
5. Set restrictive file permissions: `chmod 600 config.json tokens.json`

---

## CLI (Porter Command)

Porter includes a complete CLI for managing everything from the terminal — server, tunnels, Cloudflare, API keys, and configuration.

### Install CLI

```bash
# One-line installer (includes everything)
curl -fsSL https://tinyurl.com/2ctqvyfp | bash

# Windows PowerShell (two-step, most reliable)
curl.exe -fsSL https://tinyurl.com/2ctqvyfp -o install.sh
bash install.sh

# Or manual install
git clone https://github.com/Th3UrBanGuy/porter.git
cd porter
pip install -e .
```

### Usage

```bash
porter --help       # Show all commands
porter --version    # Show version
```

### Complete Command Reference

| Command | Description |
|---------|-------------|
| **GUI** | |
| `porter gui` | Open the web dashboard in your browser |
| `porter gui --dev` | Open in dev mode (Flask dev server) |
| **Server** | |
| `porter server start` | Start the server (prod mode, gunicorn) |
| `porter server start --mode dev` | Start in dev mode (Flask dev server) |
| `porter server stop` | Stop the server |
| `porter server restart` | Restart the server |
| `porter server status` | Check if server is running + cloudflared |
| `porter server logs` | Show last 50 lines of portal.log |
| `porter server logs -n 100` | Show last 100 lines |
| `porter server logs --follow` | Tail logs in real time |
| `porter server logs --which tunnel` | Show cloudflared logs |
| `porter server deps` | Install Python dependencies |
| **Cloudflare** | |
| `porter cf connect` | Connect Cloudflare account (OAuth) |
| `porter cf status` | Check Cloudflare connection |
| `porter cf disconnect` | Disconnect from Cloudflare |
| `porter cf refresh` | Refresh OAuth token |
| `porter cloudflare status` | Alias for `porter cf status` |
| **Tunnels** | |
| `porter tunnels` | List all active tunnels |
| `porter tunnel create <sub> <port>` | Expose localhost:port on sub.domain |
| `porter tunnel create <sub> <port> --protocol quic` | Use QUIC instead of HTTP/2 |
| `porter tunnel stop <subdomain>` | Stop a tunnel |
| `porter tunnel restart` | Restart cloudflared |
| **Domains** | |
| `porter domains` | List Cloudflare zones |
| `porter domain active` | Show active domain |
| `porter domain active <domain>` | Set active domain |
| **Ports** | |
| `porter ports` | List all listening ports |
| `porter ports check <port>` | Check if a port is in use |
| `porter ports pid <port>` | Get PID using a port |
| **API Keys** | |
| `porter keys` | List all API keys |
| `porter keys create <name>` | Create a new API key |
| `porter keys delete <key_id>` | Delete an API key |
| **Config** | |
| `porter config` | Show all config |
| `porter config set server <url>` | Set server URL |
| `porter config set passcode <code>` | Set passcode |
| `porter config set api_key <key>` | Set API key |
| `porter config get server` | Get a config value |
| `porter config unset server` | Remove a config key |
| `porter config init` | Initialize fresh config |
| **Setup** | |
| `porter setup` | Interactive setup wizard |
| `porter install` | Full install (deps + CLI + config) |
| `porter platform` | Show platform info (OS, arch, tools) |
| `porter status` | Full system status (cloudflared + tunnels) |
| **Flags** | |
| `--url <url>` | Override server URL |
| `--api-key <key>` | Override API key |
| `--passcode <code>` | Override passcode |
| `--json` | Raw JSON output |
| `-q, --quiet` | Minimal output |

### CLI Examples

```bash
# === First-time setup ===
porter cf connect              # Authorize Cloudflare (opens browser once)
porter tunnel create panel 7262  # panel.example.com -> localhost:7262

# === Daily usage ===
porter status                  # Full system status
porter tunnels                 # List all active tunnels
porter ports                   # See what's running locally

# === Create tunnels ===
porter tunnel create api 8080          # api.example.com -> localhost:8080
porter tunnel create db 5432           # db.example.com -> localhost:5432
porter tunnel create admin 9090 --protocol quic  # Use QUIC

# === Stop tunnels ===
porter tunnel stop api         # Stop the api tunnel
porter tunnel stop db          # Stop the db tunnel

# === Manage API keys (for CI/CD) ===
porter keys create github-action    # Create key for GitHub Actions
porter keys create cron-job         # Create key for cron jobs
porter keys                         # List all keys
porter keys delete <key_id>         # Delete a key

# === Configuration ===
porter config set server https://vps.example.com:7262  # Point to remote
porter config set passcode 123456                       # Set passcode
porter config get server                                # Check URL
porter config                                           # Show all

# === Server management ===
porter server start             # Start the portal
porter server start --mode dev  # Start in dev mode
porter server stop              # Stop the portal
porter server restart           # Restart
porter server logs --follow     # Watch logs live
porter server logs -n 200       # Show 200 log lines

# === Remote server ===
porter --url https://vps:7262 --api-key pk_... tunnels
porter --url https://vps:7262 tunnel create panel 7262
```

### CLI Configuration

Config stored in `~/.porter/config.json`:

```json
{
  "server_url": "http://localhost:7262",
  "api_key": "pk_...",
  "passcode": "123456"
}
```

Set once with `porter setup`, or manually:
```bash
porter config set server https://my-server:7262
porter config set api_key pk_abc123...
```

### CLI Configuration

The CLI stores its config in `~/.porter/config.json`:

```json
{
  "server_url": "http://localhost:7262",
  "api_key": "pk_...",
  "passcode": null
}
```

You can also set config via environment variables:

```bash
export PORTER_URL=http://localhost:7262
export PORTER_API_KEY=pk_...
```

---

## API Keys

API keys allow programmatic access without using the passcode directly.

### Create API Keys

**Via UI:** Settings page -> API Keys section

**Via CLI:**
```bash
porter keys create my-script
```

**Via API:**
```bash
curl -X POST http://localhost:7262/api/keys \
  -H "Content-Type: application/json" \
  -H "X-Passcode: your_passcode" \
  -d '{"name": "my-script"}'
```

### Use API Keys

```bash
# Via header
curl -H "X-API-Key: pk_..." http://localhost:7262/api/tunnels

# Via CLI
porter --api-key pk_... tunnels
```

### API Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/keys` | List all API keys |
| `POST` | `/api/keys` | Create new API key |
| `DELETE` | `/api/keys/<id>` | Delete API key |
| `POST` | `/api/keys/<id>/rotate` | Rotate API key |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Not connected" | Setup → Connect Cloudflare |
| Port not in dropdown | Start your service first, then refresh |
| Portal won't start | Check `lsof -i :7262` — kill existing process |
| Tunnel fails | Check `tail -f portal.log` |

### Logs

```bash
tail -f portal.log        # App logs
tail -f tunnel.log        # cloudflared output
ps aux | grep cloudflared  # Running tunnels
```

---

## Roadmap

- [ ] Hosted version (SaaS)
- [ ] Custom domain mapping
- [ ] Tunnel sharing & collaboration
- [ ] Usage analytics dashboard
- [ ] Webhook notifications
- [ ] Multi-user support with RBAC

---

## License

MIT

---

## Built by [Tect0nic](https://Tect0nic.com)
