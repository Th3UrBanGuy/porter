"""
Cloudflare OAuth + MCP client.

Uses OAuth 2.1 with PKCE for authentication, then makes MCP tool calls
to the Cloudflare MCP server to manage DNS, tunnels, and Zero Trust.
"""

import hashlib
import json
import os
import secrets
import time
import base64
import re as _re
from urllib.parse import urlencode

import httpx


TOKENS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tokens.json")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

CF_MCP_BASE = "https://mcp.cloudflare.com"
CF_MCP_URL = f"{CF_MCP_BASE}/mcp"

def _get_redirect_uri():
    """Build redirect URI using port 7262."""
    return "http://localhost:7262/auth/callback"


REDIRECT_URI = _get_redirect_uri()


def _load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def _save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return _b64url(digest)


class TokenStorage:
    def __init__(self, path=TOKENS_FILE):
        self.path = path
        self._data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            with open(self.path) as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get_tokens(self):
        return self._data.get("tokens")

    def set_tokens(self, tokens):
        self._data["tokens"] = tokens
        self._save()

    def get_client_info(self):
        return self._data.get("client_info")

    def set_client_info(self, info):
        self._data["client_info"] = info
        self._save()

    def is_authenticated(self):
        tokens = self.get_tokens()
        if not tokens:
            return False
        if tokens.get("expires_at", 0) > time.time():
            return True
        return bool(tokens.get("refresh_token"))


class CloudflareOAuth:
    def __init__(self, storage=None):
        self.storage = storage or TokenStorage()
        self.client_info = None
        self._metadata = None

    def _discover_metadata(self):
        if self._metadata:
            return self._metadata
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

    def _register_client(self):
        stored = self.storage.get_client_info()
        if stored and stored.get("client_id"):
            return stored
        metadata = self._discover_metadata()
        reg_endpoint = metadata.get("registration_endpoint", f"{CF_MCP_BASE}/register")
        payload = {
            "client_name": "Cloudflare Tunnel Portal",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
        resp = httpx.post(reg_endpoint, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            client_info = resp.json()
            self.storage.set_client_info(client_info)
            self.client_info = client_info
            return client_info
        raise Exception(f"Client registration failed: {resp.status_code} {resp.text}")

    def generate_auth_url(self):
        metadata = self._discover_metadata()
        client_info = self._register_client()
        code_verifier = _b64url(secrets.token_bytes(32))
        code_challenge = _pkce_challenge(code_verifier)
        state = secrets.token_hex(16)
        self.storage._data["oauth_state"] = state
        self.storage._data["code_verifier"] = code_verifier
        self.storage._save()
        params = {
            "response_type": "code",
            "client_id": client_info["client_id"],
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        auth_endpoint = metadata.get("authorization_endpoint", f"{CF_MCP_BASE}/authorize")
        return f"{auth_endpoint}?{urlencode(params)}"

    def exchange_code(self, code, state):
        stored_state = self.storage._data.get("oauth_state")
        if stored_state and state != stored_state:
            raise Exception("State mismatch")
        code_verifier = self.storage._data.get("code_verifier")
        metadata = self._discover_metadata()
        client_info = self.storage.get_client_info()
        token_endpoint = metadata.get("token_endpoint", f"{CF_MCP_BASE}/token")
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_info["client_id"],
            "code_verifier": code_verifier,
        }
        resp = httpx.post(token_endpoint, data=payload, timeout=10)
        if resp.status_code == 200:
            token_data = resp.json()
            token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
            self.storage.set_tokens(token_data)
            self.storage._data.pop("oauth_state", None)
            self.storage._data.pop("code_verifier", None)
            self.storage._save()
            return token_data
        raise Exception(f"Token exchange failed: {resp.status_code} {resp.text}")

    def refresh_token(self):
        tokens = self.storage.get_tokens()
        if not tokens or not tokens.get("refresh_token"):
            raise Exception("No refresh token")
        metadata = self._discover_metadata()
        client_info = self.storage.get_client_info()
        token_endpoint = metadata.get("token_endpoint", f"{CF_MCP_BASE}/token")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": client_info["client_id"],
        }
        resp = httpx.post(token_endpoint, data=payload, timeout=10)
        if resp.status_code == 200:
            token_data = resp.json()
            token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
            if "refresh_token" not in token_data:
                token_data["refresh_token"] = tokens["refresh_token"]
            self.storage.set_tokens(token_data)
            return token_data
        raise Exception(f"Token refresh failed: {resp.status_code} {resp.text}")

    def get_valid_token(self):
        tokens = self.storage.get_tokens()
        if not tokens:
            return None
        if tokens.get("expires_at", 0) > time.time() + 60:
            return tokens["access_token"]
        if tokens.get("refresh_token"):
            try:
                refreshed = self.refresh_token()
                return refreshed["access_token"]
            except Exception:
                pass
        return None

    def is_authenticated(self):
        return self.storage.is_authenticated()


class CloudflareAPI:
    """Makes MCP tool calls to the Cloudflare MCP server."""

    def __init__(self, oauth=None):
        self.oauth = oauth or CloudflareOAuth()
        self.config = _load_config()
        self._request_id = 0

    def _next_id(self):
        self._request_id += 1
        return self._request_id

    def _mcp_call(self, tool_name, arguments):
        import logging
        log = logging.getLogger("portal")
        token = self.oauth.get_valid_token()
        if not token:
            raise Exception("Not authenticated - please connect to Cloudflare first")

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

        log.info(f"MCP call: {tool_name}")
        resp = httpx.post(CF_MCP_URL, json=payload, headers=headers, timeout=60)
        log.info(f"MCP response status: {resp.status_code}, content-type: {resp.headers.get('content-type', '')}")

        if resp.status_code == 401:
            try:
                self.oauth.refresh_token()
                token = self.oauth.get_valid_token()
                headers["Authorization"] = f"Bearer {token}"
                resp = httpx.post(CF_MCP_URL, json=payload, headers=headers, timeout=60)
            except Exception:
                raise Exception("Authentication expired")

        content_type = resp.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            log.info(f"MCP SSE raw: {resp.text[:500]}")
            return self._parse_sse_response(resp.text)

        if resp.status_code == 200:
            data = resp.json()
            log.info(f"MCP JSON: {json.dumps(data, default=str)[:500]}")
            if "result" in data:
                return self._extract_mcp_result(data["result"])
            if "error" in data:
                raise Exception(f"MCP error: {data['error']}")

        raise Exception(f"MCP call failed: {resp.status_code} {resp.text[:500]}")

    def _parse_sse_response(self, text):
        for line in text.split("\n"):
            if line.startswith("data: "):
                data_str = line[6:].strip()
                if data_str:
                    try:
                        data = json.loads(data_str)
                        if "result" in data:
                            return self._extract_mcp_result(data["result"])
                        if "error" in data:
                            raise Exception(f"MCP error: {data['error']}")
                    except json.JSONDecodeError:
                        continue
        raise Exception("No valid response in SSE stream")

    def _extract_mcp_result(self, result):
        if isinstance(result, dict):
            content = result.get("content", [])
            if content:
                texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                full_text = "\n".join(texts)
                try:
                    return json.loads(full_text)
                except (json.JSONDecodeError, TypeError):
                    return full_text
            return result
        return result

    def _execute_code(self, code):
        import logging
        log = logging.getLogger("portal")
        log.info(f"MCP execute code: {code[:200]}...")
        result = self._mcp_call("execute", {"code": code})
        log.info(f"MCP execute result: {json.dumps(result, default=str)[:500]}")
        if isinstance(result, str) and result.startswith("Error:"):
            raise Exception(result)
        return result

    def _search_endpoints(self, code):
        result = self._mcp_call("search", {"code": code})
        return result

    def get_account_id(self):
        code = """
async () => {
    const response = await cloudflare.request({
        method: "GET",
        path: `/accounts?per_page=1`
    });
    return response.result;
}"""
        result = self._execute_code(code)
        if isinstance(result, list) and result:
            return result[0].get("id")
        if isinstance(result, dict) and result.get("id"):
            return result["id"]
        raise Exception("No Cloudflare account found")

    def get_zone_id(self, domain=None):
        domain = domain or self.config.get("domain", "kalandar.me")
        code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "GET",
        path: `/zones?name={domain}`
    }});
    return response.result;
}}"""
        result = self._execute_code(code)
        if isinstance(result, list) and result:
            return result[0].get("id")
        if isinstance(result, dict) and result.get("id"):
            return result["id"]
        raise Exception(f"Zone not found for {domain}")

    def list_zones(self):
        """Fetch all zones (domains) from the connected Cloudflare account."""
        code = """
async () => {
    const response = await cloudflare.request({
        method: "GET",
        path: `/zones?per_page=50`
    });
    return response.result;
}"""
        result = self._execute_code(code)
        if isinstance(result, list):
            return [{"id": z.get("id"), "name": z.get("name"), "status": z.get("status")} for z in result]
        return []

    def list_dns_records(self, zone_id=None, subdomain=None, domain=None):
        zone_id = zone_id or self.get_zone_id(domain)
        domain = domain or self.config.get("domain", "kalandar.me")
        name_filter = f"{subdomain}.{domain}" if subdomain else ""
        code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "GET",
        path: `/zones/{zone_id}/dns_records?per_page=100{('&name=' + name_filter) if name_filter else ''}`
    }});
    return response.result;
}}"""
        result = self._execute_code(code)
        return result if isinstance(result, list) else []

    def create_dns_record(self, name, content, record_type="CNAME", zone_id=None, proxied=True):
        zone_id = zone_id or self.get_zone_id()
        payload_json = json.dumps({
            "type": record_type,
            "name": name,
            "content": content,
            "proxied": proxied,
        })
        code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "POST",
        path: `/zones/{zone_id}/dns_records`,
        body: {payload_json}
    }});
    return response.result;
}}"""
        result = self._execute_code(code)
        if isinstance(result, dict):
            return result
        raise Exception(f"DNS create failed: {result}")

    def delete_dns_record(self, record_id, zone_id=None):
        zone_id = zone_id or self.get_zone_id()
        code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "DELETE",
        path: `/zones/{zone_id}/dns_records/{record_id}`
    }});
    return response;
}}"""
        self._execute_code(code)
        return True

    def create_tunnel(self, name, account_id=None):
        account_id = account_id or self.config.get("account_id")
        if not account_id:
            account_id = self.get_account_id()
            cfg = _load_config()
            cfg["account_id"] = account_id
            _save_config(cfg)
            self.config = cfg

        secret = base64.b64encode(secrets.token_bytes(32)).decode()
        code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "POST",
        path: `/accounts/{account_id}/cfd_tunnel`,
        body: {{
            name: "{name}",
            tunnel_secret: "{secret}",
            config_src: "cloudflare"
        }}
    }});
    return response.result;
}}"""
        result = self._execute_code(code)
        if isinstance(result, dict) and result.get("id"):
            cfg = _load_config()
            cfg["tunnel_id"] = result["id"]
            _save_config(cfg)
            self.config = cfg
            return result
        raise Exception(f"Tunnel create failed: {result}")

    def get_tunnel_token(self, tunnel_id, account_id=None):
        account_id = account_id or self.config.get("account_id") or self.get_account_id()
        code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "GET",
        path: `/accounts/{account_id}/cfd_tunnel/{tunnel_id}/token`
    }});
    return response.result;
}}"""
        result = self._execute_code(code)
        if result:
            return result if isinstance(result, str) else result.get("token", result)
        raise Exception("Failed to get tunnel token")

    def add_tunnel_hostname(self, tunnel_id, hostname, service, account_id=None):
        account_id = account_id or self.config.get("account_id") or self.get_account_id()

        get_code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "GET",
        path: `/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`
    }});
    return response.result;
}}"""
        existing = self._execute_code(get_code)
        existing_ingress = []
        if isinstance(existing, dict):
            config = existing.get("config") or {}
            existing_ingress = config.get("ingress") or []

        hostname_rules = [r for r in existing_ingress if r.get("hostname")]
        catch_all = [r for r in existing_ingress if r.get("service") == "http_status:404"]

        hostname_rules.append({
            "hostname": hostname,
            "service": service,
            "originRequest": {},
        })

        ingress = hostname_rules + (catch_all or [{"service": "http_status:404"}])
        config_json = json.dumps({"config": {"ingress": ingress}})

        put_code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "PUT",
        path: `/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`,
        body: {config_json}
    }});
    return response;
}}"""
        result = self._execute_code(put_code)
        if isinstance(result, str) and result.startswith("Error:"):
            raise Exception(f"Add hostname failed: {result}")
        return True

    def remove_tunnel_hostname(self, tunnel_id, hostname, account_id=None):
        account_id = account_id or self.config.get("account_id") or self.get_account_id()

        get_code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "GET",
        path: `/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`
    }});
    return response.result;
}}"""
        existing = self._execute_code(get_code)
        if not isinstance(existing, dict):
            return True

        config = existing.get("config", {})
        ingress = config.get("ingress", [])
        filtered = [r for r in ingress if r.get("hostname") != hostname]

        if len(filtered) == len(ingress):
            return True

        if not any(r.get("service") == "http_status:404" for r in filtered):
            filtered.append({"service": "http_status:404"})

        config_json = json.dumps({"config": {"ingress": filtered}})
        put_code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "PUT",
        path: `/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations`,
        body: {config_json}
    }});
    return response;
}}"""
        result = self._execute_code(put_code)
        if isinstance(result, str) and result.startswith("Error:"):
            raise Exception(f"Remove hostname failed: {result}")
        return True

    def list_tunnels(self, account_id=None):
        account_id = account_id or self.config.get("account_id") or self.get_account_id()
        code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "GET",
        path: `/accounts/{account_id}/cfd_tunnel?per_page=50`
    }});
    return response.result;
}}"""
        result = self._execute_code(code)
        return result if isinstance(result, list) else []

    def delete_tunnel(self, tunnel_id, account_id=None):
        account_id = account_id or self.config.get("account_id") or self.get_account_id()
        code = f"""
async () => {{
    const response = await cloudflare.request({{
        method: "DELETE",
        path: `/accounts/{account_id}/cfd_tunnel/{tunnel_id}`
    }});
    return response;
}}"""
        self._execute_code(code)
        return True
