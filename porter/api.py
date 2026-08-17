"""
API client for communicating with Porter server.
"""

import json
import sys
from urllib.parse import urljoin

try:
    import httpx
except ImportError:
    print("Error: httpx is required. Install with: pip install httpx", file=sys.stderr)
    sys.exit(1)

from porter.config import get_server_url, get_api_key, get_passcode


class PorterAPI:
    def __init__(self, base_url=None):
        self.base_url = (base_url or get_server_url()).rstrip("/")
        self.api_key = get_api_key()
        self.passcode = get_passcode()
        self.client = httpx.Client(timeout=30)

    def _get_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        elif self.passcode:
            headers["X-Passcode"] = self.passcode
        return headers

    def _url(self, path):
        return f"{self.base_url}{path}"

    def get(self, path):
        try:
            resp = self.client.get(self._url(path), headers=self._get_headers())
            return self._handle_response(resp)
        except httpx.ConnectError:
            print(f"Error: Cannot connect to {self.base_url}", file=sys.stderr)
            print("Is the Porter server running? Start with: python3 app.py", file=sys.stderr)
            sys.exit(1)

    def post(self, path, data=None):
        try:
            resp = self.client.post(
                self._url(path),
                headers=self._get_headers(),
                json=data,
            )
            return self._handle_response(resp)
        except httpx.ConnectError:
            print(f"Error: Cannot connect to {self.base_url}", file=sys.stderr)
            print("Is the Porter server running? Start with: python3 app.py", file=sys.stderr)
            sys.exit(1)

    def delete(self, path):
        try:
            resp = self.client.delete(self._url(path), headers=self._get_headers())
            return self._handle_response(resp)
        except httpx.ConnectError:
            print(f"Error: Cannot connect to {self.base_url}", file=sys.stderr)
            print("Is the Porter server running? Start with: python3 app.py", file=sys.stderr)
            sys.exit(1)

    def _handle_response(self, resp):
        if resp.status_code == 401:
            print("Error: Authentication failed. Check your API key or passcode.", file=sys.stderr)
            sys.exit(1)
        if resp.status_code >= 400:
            try:
                data = resp.json()
                msg = data.get("error", data.get("message", resp.text))
            except Exception:
                msg = resp.text
            print(f"Error ({resp.status_code}): {msg}", file=sys.stderr)
            sys.exit(1)
        try:
            return resp.json()
        except Exception:
            return {"success": True}

    def close(self):
        self.client.close()
