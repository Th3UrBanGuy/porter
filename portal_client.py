"""
Porter Connector client.

Talks to the Porter Connector portal (Next.js on Vercel) so that
headless devices can obtain Cloudflare credentials without a browser:

    GET  /api/v1/ping                    -> unauthenticated liveness/handshake probe
    POST /api/v1/keys/login              -> exchange email/username + password for an API key
    GET  /api/v1/connections             -> list the account's Cloudflare connections
    GET  /api/v1/connections/<id>/token  -> pull the token payload (tokens.json format)

Transport policy
----------------
* HTTPS with certificate verification (TLS 1.2+) is always preferred for
  remote portals.
* Loopback and private/LAN targets may use plain HTTP; when a TLS handshake
  fails because the server simply does not speak TLS, the client falls back
  to HTTP automatically there.
* For public hosts, cleartext HTTP is refused unless explicitly requested
  (scheme in URL or PORTER_ALLOW_HTTP=1) so credentials are never sent in
  the clear by accident.
* A /api/v1/ping handshake confirms reachability and portal identity before
  credentials are exchanged, and detects local clock skew.
* Transient failures (connect/reset/timeout/429/5xx) are retried with
  exponential backoff + jitter; authoritative 4xx answers fail fast.

Env knobs
---------
PORTER_TIMEOUT        total read timeout seconds      (default 15)
PORTER_RETRIES        attempts per transport failure  (default 3)
PORTER_CA_BUNDLE      CA file for self-signed portals (default system CAs)
PORTER_TLS_INSECURE   "1" disables certificate verification (not recommended)
PORTER_ALLOW_HTTP     "1" permits cleartext HTTP to public hosts

The API key is stored in config.json (`portal_api_key`); passwords are never
persisted and secrets are never logged.
"""

import ipaddress
import logging
import os
import random
import ssl
import threading
import time
import urllib.parse

import httpx

log = logging.getLogger("portal")

# Accepted /api/v1/ping service identities. "porter-broker" is the legacy
# marker kept for compatibility with already-deployed portals.
SERVICE_MARKERS = ("porter-connector", "porter-broker")
SKEW_WARN_SECS = 120
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER = 30.0


class PortalError(Exception):
    """Base error for all Connector Portal communication problems."""


class PortalUnreachable(PortalError):
    """Could not establish a working channel to any candidate endpoint."""


class PortalAuthError(PortalError):
    """Portal rejected our credentials or API key."""


def _env_flag(name):
    return str(os.environ.get(name, "")).strip().lower() in ("1", "true", "yes")


def _timeout():
    total = float(os.environ.get("PORTER_TIMEOUT") or 15)
    return httpx.Timeout(total, connect=min(6.0, max(1.0, total / 2)))


def _probe_timeout():
    return httpx.Timeout(6.0, connect=3.0)


def _retries():
    try:
        return max(1, int(os.environ.get("PORTER_RETRIES") or 3))
    except ValueError:
        return 3


# --------------------------------------------------------------------------
# URL helpers / policy
# --------------------------------------------------------------------------

def _host_of(base):
    try:
        host = urllib.parse.urlsplit("//" + str(base).split("://", -1)[-1]).hostname or ""
    except ValueError:
        host = ""
    return host.strip("[]").lower()


def _classify(host):
    """-> 'loopback' | 'private' | 'public' | 'unknown'"""
    if not host:
        return "unknown"
    if host in LOCAL_HOSTS or host.endswith(".localhost") or host.endswith(".local"):
        return "loopback" if not host.endswith(".local") else "private"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "public"
    if ip.is_loopback:
        return "loopback"
    if ip.is_private or ip.is_link_local:
        return "private"
    return "public"


def _allow_http(cls):
    if cls in ("loopback", "private"):
        return True
    return _env_flag("PORTER_ALLOW_HTTP")


def _mk_base(scheme, host, port):
    disp = f"[{host}]" if ":" in host else host
    return f"{scheme}://{disp}{':' + str(port) if port else ''}"


def _candidates(raw):
    """
    Ordered candidate origin URLs for a user-supplied portal address.

    Explicit scheme first, then the alternate scheme where policy allows,
    then a localhost <-> 127.0.0.1 swap for IPv4-stack quirks.
    """
    raw = (raw or "").strip().rstrip("/")
    if not raw:
        raise PortalError("Connector Portal URL is required")

    explicit = None
    rest = raw
    if "://" in raw:
        explicit, _, rest = raw.partition("://")
        explicit = explicit.lower()
        if explicit not in ("http", "https"):
            raise PortalError(f"Unsupported URL scheme '{explicit}://'")

    netloc = rest.split("/", 1)[0]
    host = _host_of(netloc)
    cls = _classify(host)
    port = urllib.parse.urlsplit(f"//{netloc}").port

    bases = []

    def add(scheme):
        b = _mk_base(scheme, host, port)
        if b not in bases:
            bases.append(b)

    if explicit:
        add(explicit)
        alt = "https" if explicit == "http" else "http"
        if alt == "http" and (cls != "public" or _env_flag("PORTER_ALLOW_HTTP")):
            add(alt)
        elif alt == "http":
            # Public + no opt-in: cleartext stays out of the candidate list.
            pass
        else:
            add(alt)
    else:
        if cls == "loopback":
            add("http")
            add("https")
        elif _allow_http(cls):
            add("https")
            add("http")
        else:
            add("https")

    if host in ("localhost", "127.0.0.1"):
        swap_host = "127.0.0.1" if host == "localhost" else "localhost"
        extra = [_mk_base(s, swap_host, port) for s in ("http", "https")]
        for b in extra:
            if b not in bases and (_host_of(b) != "localhost" or True):
                # honour the same policy for swapped candidates
                if b.startswith("https://") or _allow_http(_classify(swap_host)):
                    bases.append(b)

    return bases


def normalize_base_url(url):
    """
    Canonical base URL for `url`. Prefers a previously negotiated origin for
    the same input so saved config keeps the working scheme.
    """
    raw = (url or "").strip()
    resolved = _RESOLVED_CACHE.get(raw.lower().rstrip("/"))
    if resolved:
        return resolved
    cands = _candidates(url)
    return cands[0]


# --------------------------------------------------------------------------
# TLS
# --------------------------------------------------------------------------

def _ssl_context():
    ca = os.environ.get("PORTER_CA_BUNDLE") or None
    ctx = ssl.create_default_context(cafile=ca)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    if _env_flag("PORTER_TLS_INSECURE"):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        log.warning(
            "TLS certificate verification DISABLED via PORTER_TLS_INSECURE — "
            "use only against trusted networks."
        )
    return ctx


# --------------------------------------------------------------------------
# Pooled clients (keep-alive), one per origin
# --------------------------------------------------------------------------

_clients = {}
_lock = threading.Lock()


def _origin_of(base):
    parts = urllib.parse.urlsplit(base)
    return f"{parts.scheme}://{parts.netloc}"


def _client_for(origin):
    with _lock:
        cli = _clients.get(origin)
        if cli is None:
            cli = httpx.Client(
                base_url=origin,
                timeout=_timeout(),
                verify=_ssl_context(),
                follow_redirects=False,
                headers={"User-Agent": "porter-portal-client/2.1"},
                limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
            )
            _clients[origin] = cli
        return cli


def _sleep_backoff(attempt, retry_after=None):
    delay = None
    if retry_after:
        try:
            delay = min(float(retry_after), MAX_RETRY_AFTER)
        except ValueError:
            delay = None
    if delay is None:
        delay = min(0.5 * (2 ** attempt) + random.uniform(0.05, 0.35), 8.0)
    time.sleep(delay)


def _is_tlsless_error(exc):
    msg = str(exc)
    return "WRONG_VERSION_NUMBER" in msg or ("SSL" in msg and "CERTIFICATE" not in msg.upper())


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------

class PortalClient:
    """
    Negotiates a working origin once (ping handshake), then reuses a pooled
    keep-alive connection for all API calls, retrying transient failures.
    """

    def __init__(self, base_url):
        self.raw_input = (base_url or "").strip()
        self.base_url = None
        self.server_info = None
        self._failed_candidates = []

    # -- negotiation ------------------------------------------------------

    def resolve(self):
        if self.base_url:
            return self.base_url

        key = self.raw_input.lower().rstrip("/")
        cached = _RESOLVED_CACHE.get(key)
        if cached:
            self._bind(cached)
            return cached

        last_err = "no candidates"
        for cand in _candidates(self.raw_input):
            ok, info = self._probe(cand)
            if ok:
                self._bind(cand)
                _remember(self.raw_input, cand)
                if info:
                    self.server_info = info
                    self._check_skew(info)
                return cand
            last_err = info or last_err
        raise PortalUnreachable(f"Cannot reach Connector Portal ({last_err})")

    def _bind(self, base):
        self.base_url = base.rstrip("/")
        if self.base_url.startswith("http://") and _classify(_host_of(self.base_url)) == "public":
            log.warning(
                "Using cleartext HTTP to a PUBLIC host (%s) — credentials will "
                "travel unencrypted. Prefer HTTPS.",
                self.base_url,
            )

    def _check_skew(self, info):
        server_ms = info.get("time")
        if isinstance(server_ms, (int, float)):
            skew = abs(server_ms / 1000.0 - time.time())
            if skew > SKEW_WARN_SECS:
                log.warning(
                    "Clock skew vs portal is %.0fs — token expiry checks may misbehave.",
                    skew,
                )

    def _probe(self, cand):
        """
        One ping attempt against a candidate origin.
        Returns (True, info_dict_or_None) if the origin answers at all — even
        an older portal without /api/v1/ping (404) proves the transport works.
        Returns (False, reason) otherwise.
        """
        try:
            resp = _client_for(cand).request(
                "GET", "/api/v1/ping", timeout=_probe_timeout()
            )
        except httpx.TransportError as e:
            if cand.startswith("https://") and _is_tlsless_error(e):
                host = _host_of(cand)
                if not _allow_http(_classify(host)):
                    return False, f"{cand}: no TLS server (HTTP fallback disabled)"
                log.info("%s does not speak TLS — falling back to HTTP", cand)
            return False, f"{cand}: {e}"
        except httpx.HTTPError as e:
            return False, f"{cand}: {e}"

        if resp.status_code >= 500:
            return False, f"{cand}: server error {resp.status_code}"

        if resp.status_code == 200:
            try:
                data = resp.json()
            except ValueError:
                data = None
            if isinstance(data, dict) and data.get("service"):
                if data["service"] not in SERVICE_MARKERS:
                    return (
                        False,
                        f"{cand}: expected service={'/'.join(SERVICE_MARKERS)!r}, got {data['service']!r}",
                    )
                return True, data

        # Reachable but no usable marker (older portal, proxy, etc.)
        return True, None

    # -- core request loop --------------------------------------------------

    def request(self, method, path, *, json_body=None, api_key=None, auth_required=True):
        """
        Send `method path` to the negotiated origin with retries + fallbacks.
        Returns the final httpx.Response (any status).
        """
        if auth_required and not api_key:
            raise PortalAuthError("No API key available — run portal login again")

        origins = [self.base_url] if self.base_url else []
        for cand in _candidates(self.raw_input):
            o = _origin_of(cand)
            if o not in origins:
                origins.append(o)

        headers = {"Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if api_key:
            headers["X-API-Key"] = api_key

        last_transport_err = None
        for origin in origins:
            client = _client_for(origin)
            for attempt in range(_retries()):
                try:
                    resp = client.request(
                        method,
                        path,
                        json=json_body,
                        headers=headers,
                        timeout=_timeout(),
                    )
                except httpx.TransportError as e:
                    last_transport_err = e
                    if origin.startswith("https://") and _is_tlsless_error(e):
                        break  # stop hammering this origin, try next candidate
                    if attempt < _retries() - 1:
                        _sleep_backoff(attempt)
                    continue
                except httpx.HTTPError as e:
                    last_transport_err = e
                    continue

                if resp.status_code in RETRYABLE_STATUS and attempt < _retries() - 1:
                    _sleep_backoff(attempt, resp.headers.get("Retry-After"))
                    continue
                return self._finalize(resp)

        if last_transport_err is not None:
            raise PortalUnreachable(f"Cannot reach Connector Portal at {self.base_url or self.raw_input}: {last_transport_err}")
        raise PortalUnreachable(f"Cannot reach Connector Portal at {self.base_url or self.raw_input}")

    @staticmethod
    def _finalize(resp):
        """
        Turn proxy/tunnel gates into actionable errors before callers look
        at status codes (e.g. GitHub Codespaces 'private port' interstitials).
        """
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("location", "")
            www_auth = resp.headers.get("www-authenticate", "")
            if "tunnel" in www_auth.lower() or "github" in loc.lower():
                raise PortalError(
                    "The portal URL is behind an authenticating tunnel "
                    "(GitHub Codespace?). Make the forwarded port Public, or "
                    "use a URL reachable without browser sign-in."
                )
            raise PortalError(
                f"Unexpected redirect from Connector Portal ({resp.status_code}) to {loc or '?'}"
            )
        return resp

    # -- API operations -----------------------------------------------------

    def exchange_credentials(self, identifier, password):
        """Handshake first, then exchange email/username + password for a device API key."""
        try:
            self.resolve()
        except PortalUnreachable as e:
            raise PortalError(str(e))

        resp = self.request(
            "POST",
            "/api/v1/keys/login",
            json_body={"identifier": identifier, "password": password},
            auth_required=False,
        )
        try:
            data = resp.json()
        except ValueError:
            raise PortalError(f"Connector Portal returned invalid response ({resp.status_code})")

        if resp.status_code == 401:
            raise PortalError("Invalid email/username or password")
        if resp.status_code == 422:
            raise PortalError(data.get("error", "Invalid request"))
        if resp.status_code == 423:
            raise PortalError(data.get("error", "Account locked"))
        if resp.status_code == 429:
            raise PortalError("Too many attempts — slow down and retry shortly")
        if resp.status_code != 200:
            raise PortalError(data.get("error", f"Key exchange failed ({resp.status_code})"))

        api_key = data.get("api_key")
        if not api_key:
            raise PortalError("Connector Portal did not return an API key")
        return api_key

    def list_connections(self, api_key=None):
        """List Cloudflare connections registered in the portal."""
        resp = self.request("GET", "/api/v1/connections", api_key=api_key)
        if resp.status_code == 401:
            raise PortalAuthError("Connector Portal rejected the API key — run portal login again")
        if resp.status_code != 200:
            raise PortalError(f"Could not list connections ({resp.status_code})")
        try:
            data = resp.json()
        except ValueError:
            raise PortalError("Connector Portal returned invalid JSON")
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

    def pull_token(self, api_key, connection_id):
        """
        Pull the decrypted token payload for one connection.
        Returns dict shaped like tokens.json: {client_info, tokens}.
        """
        connection_id = urllib.parse.quote(str(connection_id), safe="")
        resp = self.request(
            "GET", f"/api/v1/connections/{connection_id}/token", api_key=api_key
        )
        if resp.status_code == 401:
            raise PortalAuthError("Connector Portal rejected the API key — run portal login again")
        if resp.status_code == 404:
            raise PortalError("Connection not found in the Connector Portal — it may have been removed")
        if resp.status_code != 200:
            raise PortalError(f"Token pull failed ({resp.status_code})")
        try:
            payload = resp.json()
        except ValueError:
            raise PortalError("Connector Portal returned invalid JSON")

        tokens = payload.get("tokens")
        if not isinstance(tokens, dict) or not tokens.get("refresh_token"):
            raise PortalError("Connector payload has no usable refresh token")
        return payload

    def health(self):
        """Return portal identity info, resolving/negotiating if needed."""
        if self.server_info is None:
            self.resolve()
        return self.server_info


# --------------------------------------------------------------------------
# Module-level cache + backward-compatible functions
# --------------------------------------------------------------------------

_clients_by_input = {}
_RESOLVED_CACHE = {}
_cache_lock = threading.Lock()


def _remember(raw_input, resolved):
    with _cache_lock:
        _RESOLVED_CACHE[raw_input.strip().lower().rstrip("/")] = resolved.rstrip("/")
        _RESOLVED_CACHE[resolved.rstrip("/").lower()] = resolved.rstrip("/")


def get_client(base_url):
    key = (base_url or "").strip().lower().rstrip("/")
    with _lock:
        cli = _clients_by_input.get(key)
        if cli is None:
            cli = PortalClient(base_url)
            _clients_by_input[key] = cli
        return cli


def exchange_credentials(base_url, identifier, password):
    """Exchange email/username + password for a device API key."""
    return get_client(base_url).exchange_credentials(identifier, password)


def list_connections(base_url, api_key):
    """List Cloudflare connections registered in the portal."""
    return get_client(base_url).list_connections(api_key)


def pull_token(base_url, api_key, connection_id):
    """Pull the decrypted token payload for one connection."""
    return get_client(base_url).pull_token(api_key, connection_id)


def save_portal_settings(cfg, base_url, api_key, connection_id):
    cfg["portal_url"] = normalize_base_url(get_client(base_url).base_url or base_url)
    cfg["portal_api_key"] = api_key
    cfg["portal_connection_id"] = connection_id
