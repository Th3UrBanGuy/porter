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

- **OAuth 2.1 + PKCE** — No API tokens. One-click Cloudflare authorization.
- **MCP Integration** — All API calls go through Cloudflare's MCP server.
- **One-Click Deploy** — Port + subdomain → live URL.
- **Real-Time Progress** — SSE-powered step-by-step progress tracking.
- **Auto Port Detection** — Scans for running services.
- **Passcode Protection** — SHA-256 hashed passcode security.
- **Multi-Domain** — Supports multiple Cloudflare zones.
- **PWA Support** — Install as a native app on mobile/desktop.
- **Light/Dark Theme** — Modern UI with glass morphism.
- **Mobile Optimized** — Responsive design with touch-friendly controls.

---

## Quick Start

### Prerequisites

- Python 3.10+
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) installed
- A Cloudflare account with a domain

### Install

```bash
# Clone
git clone https://github.com/Th3UrBanGuy/porter.git
cd porter

# Install dependencies
pip install -r requirements.txt

# Ensure cloudflared is installed
which cloudflared || {
  curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
}

# Start
python3 app.py
```

### First-Time Setup

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
| `GET` | `/api/domains` | List Cloudflare zones |
| `POST` | `/api/domains/active` | Switch active domain |

---

## File Structure

```
porter/
├── app.py                    # Flask backend (routes, SSE, tunnel mgmt)
├── cloudflare_client.py      # OAuth 2.1 + PKCE, MCP orchestration
├── config.json               # Portal config (auto-created)
├── tokens.json               # OAuth tokens (auto-created)
├── tunnels.json              # Active tunnel tracking
├── requirements.txt          # flask>=3.0, httpx>=0.25
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
- **OAuth** — Tokens scoped to MCP server, auto-refresh
- **Sessions** — Flask session cookies
- **MCP** — API calls proxied through Cloudflare (no direct token exposure)

### Best Practices

1. Use a reverse proxy (nginx/caddy) with TLS
2. Restrict firewall access to port 7262
3. Use a strong passcode
4. Set restrictive file permissions: `chmod 600 config.json tokens.json`

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
