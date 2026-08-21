"""
Porter Broker client.

Talks to the token broker portal (porter-broker, Next.js on Vercel) so that
headless devices can obtain Cloudflare credentials without a browser:

    POST /api/v1/keys/login              -> exchange email/username + password for an API key
    GET  /api/v1/connections             -> list the account's Cloudflare connections
    GET  /api/v1/connections/<id>/token  -> pull the token payload (tokens.json format)

The API key is stored in config.json (`portal_api_key`); passwords are never
persisted.
"""

import json
import logging

import httpx

log = logging.getLogger("portal")

DEFAULT_TIMEOUT = 30.0


class PortalError(Exception):
    pass


def normalize_base_url(url):
    url = (url or "").strip().rstrip("/")
    if not url:
        raise PortalError("Portal URL is required")
    if "://" not in url:
        url = "https://" + url
    return url


def _headers(api_key=None):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        h["X-API-Key"] = api_key
    return h


def _request(method, url, **kwargs):
    try:
        resp = httpx.request(method, url, timeout=DEFAULT_TIMEOUT, **kwargs)
    except httpx.HTTPError as e:
        raise PortalError(f"Cannot reach broker at {url}: {e}")
    return resp


def exchange_credentials(base_url, identifier, password):
    """Exchange email/username + password for a device API key."""
    base = normalize_base_url(base_url)
    resp = _request(
        "POST",
        f"{base}/api/v1/keys/login",
        headers=_headers(),
        json={"identifier": identifier, "password": password},
    )
    try:
        data = resp.json()
    except ValueError:
        raise PortalError(f"Broker returned invalid response ({resp.status_code})")
    if resp.status_code == 401:
        raise PortalError("Invalid email/username or password")
    if resp.status_code == 423:
        raise PortalError(data.get("error", "Account locked"))
    if resp.status_code != 200:
        raise PortalError(data.get("error", f"Key exchange failed ({resp.status_code})"))
    api_key = data.get("api_key")
    if not api_key:
        raise PortalError("Broker did not return an API key")
    return api_key


def list_connections(base_url, api_key):
    """List Cloudflare connections registered on the broker."""
    base = normalize_base_url(base_url)
    resp = _request("GET", f"{base}/api/v1/connections", headers=_headers(api_key))
    if resp.status_code == 401:
        raise PortalError("Broker rejected the stored API key — log in again")
    if resp.status_code != 200:
        raise PortalError(f"Could not list connections ({resp.status_code})")
    try:
        data = resp.json()
    except ValueError:
        raise PortalError("Broker returned invalid JSON")
    conns = data.get("connections") or []
    return [
        {
            "id": c.get("id"),
            "label": c.get("label") or c.get("cf_account_name") or "cloudflare-account",
            "cf_account_id": c.get("cf_account_id"),
            "cf_account_name": c.get("cf_account_name"),
        }
        for c in conns
        if c.get("id")
    ]


def pull_token(base_url, api_key, connection_id):
    """
    Pull the decrypted token payload for one connection.
    Returns dict shaped like tokens.json: {client_info, tokens}.
    """
    base = normalize_base_url(base_url)
    resp = _request(
        "GET",
        f"{base}/api/v1/connections/{connection_id}/token",
        headers=_headers(api_key),
    )
    if resp.status_code == 401:
        raise PortalError("Broker rejected the stored API key — log in again")
    if resp.status_code == 404:
        raise PortalError("Connection not found on broker — it may have been removed")
    if resp.status_code != 200:
        raise PortalError(f"Token pull failed ({resp.status_code})")
    try:
        payload = resp.json()
    except ValueError:
        raise PortalError("Broker returned invalid JSON")

    tokens = payload.get("tokens")
    if not isinstance(tokens, dict) or not tokens.get("refresh_token"):
        raise PortalError("Broker payload has no usable refresh token")
    return payload


def save_portal_settings(cfg, base_url, api_key, connection_id):
    cfg["portal_url"] = normalize_base_url(base_url)
    cfg["portal_api_key"] = api_key
    cfg["portal_connection_id"] = connection_id
