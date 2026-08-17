"""
Cloudflare OAuth flow for CLI.

Handles authentication with Cloudflare via OAuth 2.1 + PKCE,
all from the terminal. Auto-detects ports, handles WSL,
and provides robust callback handling.
"""

import hashlib
import json
import os
import secrets
import socket
import sys
import time
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs

try:
    import httpx
except ImportError:
    httpx = None

from porter.config import load_config, save_config
from porter import output as out


def _require_httpx():
    global httpx
    if httpx is None:
        import subprocess
        out.error("httpx is not installed. Installing...")
        try:
            from porter.platform import pip_install_cmd
            cmd = pip_install_cmd() + ["httpx", "--quiet"]
            subprocess.run(cmd, check=True)
            import httpx as _httpx
            httpx = _httpx
        except Exception:
            out.die("Could not install httpx. Run: pip install httpx")


CF_MCP_BASE = "https://mcp.cloudflare.com"
CF_MCP_URL = f"{CF_MCP_BASE}/mcp"
TOKENS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tokens.json")
TIMEOUT = 300  # 5 minutes to authorize


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return _b64url(digest)


def _find_free_port(start=7265, end=7300):
    """Find an available port in range."""
    for port in range(start, end):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("localhost", port))
            sock.close()
            return port
        except OSError:
            continue
    return None


def _is_port_available(port):
    """Check if a specific port is available."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("localhost", port))
        sock.close()
        return True
    except OSError:
        return False


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to capture OAuth callback."""

    auth_code = None
    auth_state = None
    auth_error = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            OAuthCallbackHandler.auth_state = params.get("state", [None])[0]
            self._send_html(200, """
                <html><head><title>Porter - Connected</title></head>
                <body style="font-family:system-ui;text-align:center;padding:60px;background:#0a0a0f;color:#e0e0e8">
                <div style="max-width:400px;margin:0 auto">
                <div style="font-size:48px;margin-bottom:16px">&#10004;</div>
                <h1 style="font-size:24px;margin-bottom:8px">Connected!</h1>
                <p style="color:#8888a0;margin-bottom:24px">Cloudflare authorization successful.<br>You can close this tab.</p>
                <p style="color:#505068;font-size:12px">This tab will close automatically.</p>
                <script>setTimeout(() => window.close(), 2000);</script>
                </div></body></html>
            """)
        elif "error" in params:
            OAuthCallbackHandler.auth_error = params.get("error", ["unknown"])[0]
            desc = params.get("error_description", [""])[0]
            self._send_html(400, f"""
                <html><head><title>Porter - Error</title></head>
                <body style="font-family:system-ui;text-align:center;padding:60px;background:#0a0a0f;color:#e0e0e8">
                <div style="max-width:400px;margin:0 auto">
                <div style="font-size:48px;margin-bottom:16px">&#10008;</div>
                <h1 style="font-size:24px;margin-bottom:8px;color:#ef4444">Authorization Failed</h1>
                <p style="color:#8888a0">{OAuthCallbackHandler.auth_error}</p>
                <p style="color:#505068;font-size:12px;margin-top:8px">{desc}</p>
                </div></body></html>
            """)
        elif parsed.path == "/callback" or parsed.path.startswith("/callback"):
            # Got callback but no code — might be a bad request
            self._send_html(400, """
                <html><head><title>Porter - Error</title></head>
                <body style="font-family:system-ui;text-align:center;padding:60px;background:#0a0a0f;color:#e0e0e8">
                <div style="max-width:400px;margin:0 auto">
                <div style="font-size:48px;margin-bottom:16px">&#10008;</div>
                <h1 style="font-size:24px;margin-bottom:8px;color:#ef4444">Bad Request</h1>
                <p style="color:#8888a0">Missing authorization code.</p>
                </div></body></html>
            """)
        else:
            # Serve a landing page for any other path
            self._send_html(200, """
                <html><head><title>Porter OAuth</title></head>
                <body style="font-family:system-ui;text-align:center;padding:60px;background:#0a0a0f;color:#e0e0e8">
                <div style="max-width:400px;margin:0 auto">
                <h1 style="font-size:20px">Porter - OAuth Server</h1>
                <p style="color:#8888a0;font-size:14px">Waiting for Cloudflare authorization...</p>
                </div></body></html>
            """)

    def _send_html(self, code, html):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass  # Suppress HTTP server logs


class CloudflareCLI:
    """CLI-based Cloudflare OAuth flow."""

    def __init__(self):
        self.tokens_file = TOKENS_FILE
        self._metadata = None
        self._client_info = None

    def _load_tokens(self):
        if os.path.exists(self.tokens_file):
            with open(self.tokens_file) as f:
                return json.load(f)
        return {}

    def _save_tokens(self, data):
        os.makedirs(os.path.dirname(self.tokens_file), exist_ok=True)
        with open(self.tokens_file, "w") as f:
            json.dump(data, f, indent=2)

    def _discover_metadata(self):
        if self._metadata:
            return self._metadata
        _require_httpx()
        url = f"{CF_MCP_BASE}/.well-known/oauth-authorization-server"
        try:
            resp = httpx.get(url, timeout=10)
            if resp.status_code == 200:
                self._metadata = resp.json()
                return self._metadata
        except Exception:
            pass
        self._metadata = {
            "authorization_endpoint": f"{CF_MCP_BASE}/authorize",
            "token_endpoint": f"{CF_MCP_BASE}/token",
            "registration_endpoint": f"{CF_MCP_BASE}/register",
        }
        return self._metadata

    def _register_client(self, redirect_uri):
        """Register a new OAuth client with the given redirect URI."""
        _require_httpx()
        metadata = self._discover_metadata()
        reg_endpoint = metadata.get("registration_endpoint", f"{CF_MCP_BASE}/register")
        payload = {
            "client_name": "Porter CLI",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
        resp = httpx.post(reg_endpoint, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            return resp.json()
        raise Exception(f"Client registration failed: {resp.status_code} {resp.text}")

    def _save_token(self, token_data):
        data = self._load_tokens()
        data["access_token"] = token_data["access_token"]
        data["refresh_token"] = token_data.get("refresh_token", data.get("refresh_token"))
        data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
        data["token_type"] = token_data.get("token_type", "Bearer")
        self._save_tokens(data)

        # Also update Porter server's tokens.json
        self._update_server_tokens(token_data)

    def _update_server_tokens(self, token_data):
        """Update the Porter server's tokens.json with the new tokens."""
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        server_tokens_file = os.path.join(server_dir, "tokens.json")
        try:
            if os.path.exists(server_tokens_file):
                with open(server_tokens_file) as f:
                    server_tokens = json.load(f)
            else:
                server_tokens = {}

            server_tokens["tokens"] = {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": time.time() + token_data.get("expires_in", 3600),
                "token_type": token_data.get("token_type", "Bearer"),
            }
            if self._client_info:
                server_tokens["client_info"] = self._client_info

            with open(server_tokens_file, "w") as f:
                json.dump(server_tokens, f, indent=2)
        except Exception as e:
            out.warning(f"Could not update server tokens: {e}")

    def connect(self):
        """Run the full OAuth flow from the terminal."""
        _require_httpx()
        out.header("Cloudflare Authentication")
        print()

        # Check if already connected
        tokens = self._load_tokens()
        if tokens.get("access_token"):
            expires_at = tokens.get("expires_at", 0)
            if expires_at > time.time():
                remaining = int((expires_at - time.time()) / 60)
                out.success(f"Already connected (token valid for {remaining} minutes)")
                print()
                choice = input("  Reconnect? [y/N]: ").strip().lower()
                if choice != "y":
                    return True
            else:
                out.info("Token expired, refreshing...")

        # Ask user: local browser or remote/VPS?
        print()
        out.info("How are you authenticating?")
        print(f"  {out.c('1', 'cyan')}) Browser on this machine (auto callback)")
        print(f"  {out.c('2', 'cyan')}) Browser on another device / VPS (paste code)")
        print()
        choice = input("  Choice [1]: ").strip() or "1"

        if choice == "2":
            return self._connect_manual()
        return self._connect_auto()

    def _connect_auto(self):
        """Automatic OAuth flow with localhost callback."""
        _require_httpx()

        # Find an available port
        port = _find_free_port()
        if not port:
            out.error("No available port found (7265-7300)")
            out.info("Close other Porter CLI instances or free up ports")
            return False

        redirect_uri = f"http://localhost:{port}/callback"

        # Register client with this specific port
        try:
            client_info = self._register_client(redirect_uri)
            self._client_info = client_info
            out.success(f"Client registered (port {port})")
        except Exception as e:
            out.error(f"Client registration failed: {e}")
            return False

        # Generate auth URL
        metadata = self._discover_metadata()
        code_verifier = _b64url(secrets.token_bytes(32))
        code_challenge = _pkce_challenge(code_verifier)
        state = secrets.token_hex(16)

        params = {
            "response_type": "code",
            "client_id": client_info["client_id"],
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        auth_endpoint = metadata.get("authorization_endpoint", f"{CF_MCP_BASE}/authorize")
        auth_url = f"{auth_endpoint}?{urlencode(params)}"

        # Start local server BEFORE showing the URL
        OAuthCallbackHandler.auth_code = None
        OAuthCallbackHandler.auth_state = None
        OAuthCallbackHandler.auth_error = None

        server = HTTPServer(("127.0.0.1", port), OAuthCallbackHandler)
        server.timeout = 1

        print()
        out.info("Open this URL in your browser:")
        print()
        print(f"  {out.c(auth_url, 'cyan')}")
        print()

        # Try to open browser
        try:
            import webbrowser
            webbrowser.open(auth_url)
            out.success("Browser opened")
        except Exception:
            out.info("Copy the URL above and open in your browser")

        print()
        out.info(f"Waiting for authorization... (timeout: {TIMEOUT}s)")
        print()

        # Wait for callback
        start_time = time.time()
        last_dot = 0
        while time.time() - start_time < TIMEOUT:
            server.handle_request()

            if OAuthCallbackHandler.auth_code:
                break

            if OAuthCallbackHandler.auth_error:
                out.error(f"Authorization error: {OAuthCallbackHandler.auth_error}")
                server.server_close()
                return False

            elapsed = int(time.time() - start_time)
            if elapsed - last_dot >= 5:
                last_dot = elapsed
                remaining = TIMEOUT - elapsed
                sys.stdout.write(f"\r  {out.c('...', 'dim')} {remaining}s remaining  ")
                sys.stdout.flush()

        server.server_close()

        sys.stdout.write("\r" + " " * 50 + "\r")
        sys.stdout.flush()

        if not OAuthCallbackHandler.auth_code:
            out.error(f"Timeout after {TIMEOUT}s — no callback received")
            print()
            out.info("Tip: If on a VPS, use option 2 (paste code)")
            out.info("Try again: porter cf connect")
            return False

        if OAuthCallbackHandler.auth_state != state:
            out.error("State mismatch — possible CSRF attack")
            return False

        return self._exchange_code(OAuthCallbackHandler.auth_code, redirect_uri, client_info, code_verifier, metadata)

    def _connect_manual(self):
        """Manual paste-based OAuth flow for VPS/headless systems."""
        _require_httpx()

        # Use a dummy redirect URI for manual flow
        redirect_uri = "http://localhost:0/callback"

        # Register client
        try:
            client_info = self._register_client(redirect_uri)
            self._client_info = client_info
            out.success("Client registered")
        except Exception as e:
            out.error(f"Client registration failed: {e}")
            return False

        # Generate auth URL
        metadata = self._discover_metadata()
        code_verifier = _b64url(secrets.token_bytes(32))
        code_challenge = _pkce_challenge(code_verifier)
        state = secrets.token_hex(16)

        params = {
            "response_type": "code",
            "client_id": client_info["client_id"],
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        auth_endpoint = metadata.get("authorization_endpoint", f"{CF_MCP_BASE}/authorize")
        auth_url = f"{auth_endpoint}?{urlencode(params)}"

        print()
        out.info("Step 1: Open this URL in your browser:")
        print()
        print(f"  {out.c(auth_url, 'cyan')}")
        print()

        try:
            import webbrowser
            webbrowser.open(auth_url)
            out.success("Browser opened")
        except Exception:
            out.info("Copy the URL above and open in your browser")

        print()
        out.info("Step 2: After authorizing, you'll see a redirect URL like:")
        print(f"  {out.c('http://localhost:0/callback?code=XXXXX&state=YYYYY', 'dim')}")
        print()
        out.info("Copy the FULL URL from the browser address bar and paste it below:")
        print()

        redirect_url = input("  Paste redirect URL: ").strip()

        if not redirect_url:
            out.error("No URL provided")
            return False

        # Extract code from the redirect URL
        code = None
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(redirect_url)
        qs = parse_qs(parsed.query)

        if "code" in qs:
            code = qs["code"][0]
        elif "?" in redirect_url and "code=" in redirect_url:
            # Handle malformed URLs
            _, query = redirect_url.split("?", 1)
            for part in query.split("&"):
                if part.startswith("code="):
                    code = part[5:]
                    break

        if not code:
            out.error("Could not extract authorization code from URL")
            out.info("Make sure you pasted the full redirect URL")
            return False

        out.success("Authorization code extracted")

        return self._exchange_code(code, redirect_uri, client_info, code_verifier, metadata)

    def _exchange_code(self, code, redirect_uri, client_info, code_verifier, metadata):
        """Exchange authorization code for token."""
        _require_httpx()
        try:
            token_endpoint = metadata.get("token_endpoint", f"{CF_MCP_BASE}/token")
            payload = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_info["client_id"],
                "code_verifier": code_verifier,
            }
            resp = httpx.post(token_endpoint, data=payload, timeout=15)
            if resp.status_code == 200:
                token_data = resp.json()
                self._save_token(token_data)
                out.success("Authentication successful!")
                print()
                return True
            else:
                out.error(f"Token exchange failed: {resp.status_code}")
                try:
                    err = resp.json()
                    out.error(f"  {err.get('error', '')} {err.get('error_description', '')}")
                except Exception:
                    out.error(f"  {resp.text[:200]}")
                return False
        except Exception as e:
            out.error(f"Token exchange error: {e}")
            return False

    def disconnect(self):
        """Disconnect from Cloudflare."""
        if os.path.exists(self.tokens_file):
            os.remove(self.tokens_file)
            out.success("Disconnected from Cloudflare")
        else:
            out.info("Not connected")

        # Also remove server tokens
        server_tokens_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tokens.json"
        )
        if os.path.exists(server_tokens_file):
            os.remove(server_tokens_file)

    def status(self):
        """Check Cloudflare connection status."""
        tokens = self._load_tokens()
        if not tokens.get("access_token"):
            out.info("Not connected to Cloudflare")
            return False

        expires_at = tokens.get("expires_at", 0)
        if expires_at > time.time():
            remaining = int((expires_at - time.time()) / 60)
            out.success(f"Connected to Cloudflare (token valid for {remaining} minutes)")
            return True
        elif tokens.get("refresh_token"):
            out.info("Token expired, can refresh")
            return True
        else:
            out.warning("Token expired, please reconnect")
            return False

    def refresh(self):
        """Refresh the OAuth token."""
        _require_httpx()
        tokens = self._load_tokens()
        if not tokens.get("refresh_token"):
            out.error("No refresh token, please reconnect")
            return False

        metadata = self._discover_metadata()
        token_endpoint = metadata.get("token_endpoint", f"{CF_MCP_BASE}/token")

        try:
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": tokens.get("client_id"),
            }
            resp = httpx.post(token_endpoint, data=payload, timeout=10)
            if resp.status_code == 200:
                token_data = resp.json()
                self._save_token(token_data)
                out.success("Token refreshed")
                return True
            else:
                out.error(f"Refresh failed: {resp.status_code}")
                return False
        except Exception as e:
            out.error(f"Refresh error: {e}")
            return False
