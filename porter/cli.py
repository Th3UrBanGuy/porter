"""
Porter CLI — Unified command-line interface for Cloudflare Tunnel Portal.

Every feature of Porter accessible through a single program via subcommands.
Cross-platform: Linux, macOS, Windows, Termux.
"""

import argparse
import json
import os
import time
import subprocess
import sys
import getpass
from pathlib import Path

from porter import __version__
from porter.api import PorterAPI
from porter.config import (
    is_configured, get_server_url, set_server_url,
    set_api_key, set_passcode, load_config, save_config,
)
from porter.platform import (
    OS_NAME, IS_WINDOWS, IS_LINUX, IS_TERMUX,
    python_cmd, open_browser, list_listening_ports,
    find_pid_by_port, is_pid_running, platform_info,
)
from porter import output as out

# Primary Porter Connector portal — used when no custom portal link is set.
DEFAULT_PORTAL_URL = "https://porter-connector.vercel.app"


# ═══════════════════════════════════════════════════════════════
#  Help text
# ═══════════════════════════════════════════════════════════════

HELP = f"""\
{out.c('porter', 'bold')} {out.c(f'v{__version__}', 'dim')} — Cloudflare Tunnel Portal  {out.c(f'[{OS_NAME}]', 'dim')}

{out.c('USAGE', 'cyan')}
    porter <group> <command> [args]  [flags]

{out.c('QUICK START', 'cyan')}
    porter login                      Link device to the Connector Portal
    porter gui                        Open the web dashboard in browser

{out.c('SERVER', 'cyan')}
    porter server start               Start the server
    porter server stop                Stop the server
    porter server restart             Restart the server
    porter server status              Check if server is running
    porter server logs [n]            Show last n lines of logs
    porter server logs --follow       Tail logs in real time
    porter server deps                Install Python dependencies

{out.c('CLOUDFLARE', 'cyan')}
    porter cf connect                 Connect Cloudflare account (OAuth)
    porter cf status                  Check Cloudflare connection
    porter cf disconnect              Disconnect from Cloudflare
    porter cf refresh                 Refresh OAuth token
    porter cf portal-login [url]      Link device to the Connector Portal
    porter cf portal-status           Show portal connection status
    porter cf connections             List Connector Portal connections
    porter cf use <id>                Switch active connector connection
    porter cf sync                    Re-pull + verify active account
    porter cf accounts                List accounts stored on device
    porter cf forget <id>             Remove an account from device

{out.c('TUNNELS', 'cyan')}
    porter tunnels                    List all active tunnels
    porter tunnel create <sub> <port> Expose localhost:<port> on <sub>
    porter tunnel stop <subdomain>    Stop a tunnel
    porter tunnel restart             Restart cloudflared

{out.c('SHORT URL', 'cyan')}
    porter shorturl <url>             Shorten a URL (via is.gd)

{out.c('DOMAINS', 'cyan')}
    porter domains                    List Cloudflare zones
    porter domain active              Show/set active domain

{out.c('PORTS', 'cyan')}
    porter ports                      List listening ports
    porter ports check <port>         Check if a port is in use
    porter ports pid <port>           Get PID using a port

{out.c('API KEYS', 'cyan')}
    porter keys                       List all API keys
    porter keys create <name>         Create a new API key
    porter keys delete <id>           Delete an API key

{out.c('CONFIG', 'cyan')}
    porter config                     Show current config
    porter config set <key> <value>   Set a config value
    porter config get <key>           Get a config value
    porter config unset <key>         Remove a config key

{out.c('SETUP', 'cyan')}
    porter setup                      Run interactive setup wizard
    porter install                    Full install (deps + CLI + config)
    porter platform                   Show platform info

{out.c('FLAGS', 'cyan')}
    --url <url>          Server URL  (overrides config)
    --api-key <key>      API key     (overrides config)
    --passcode <code>    Passcode    (overrides config)
    --json               Raw JSON output
    --quiet, -q          Minimal output
    --help, -h           Show this help
    --version, -v        Show version

{out.c('EXAMPLES', 'cyan')}
    porter login                              Link device to portal
    porter gui                                Open dashboard in browser
    porter cf connect                         First-time Cloudflare setup
    porter tunnel create panel 7262           panel.domain -> localhost:7262
    porter tunnel create api 8080 --protocol quic
    porter shorturl https://sub.domain.com    Shorten a tunnel URL
    porter keys create github-action          CI/CD key
    porter config set server https://vps:7262 Remote server
    porter server start                       Start the portal
    porter server logs --follow               Watch logs
    porter platform                           Show platform info
"""


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════

def _api(args):
    """Build API client from global flags."""
    api = PorterAPI(base_url=args.url if hasattr(args, "url") else None)
    if hasattr(args, "api_key") and args.api_key:
        api.api_key = args.api_key
    elif hasattr(args, "passcode") and args.passcode:
        api.passcode = args.passcode
    return api


def _die(msg):
    out.error(msg)
    sys.exit(1)


def _require(args, fields, usage):
    for f in fields:
        if not getattr(args, f, None):
            out.error(f"Missing argument: {f}")
            out.info(f"Usage: {usage}")
            print()
            sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  Commands: gui
# ═══════════════════════════════════════════════════════════════

def cmd_gui(args):
    """Open the Porter web dashboard in the default browser."""
    from porter.server import get_port, _read_pid, _is_running

    port = get_port()
    pid = _read_pid()
    url = f"http://localhost:{port}"

    if not _is_running(pid):
        out.info("Server not running, starting...")
        from porter.server import start
        start(port=port, mode="dev" if hasattr(args, "dev") and args.dev else "prod")
        import time
        time.sleep(2)

    out.info(f"Opening {url} in browser...")
    if open_browser(url):
        out.success("Dashboard opened")
    else:
        out.warning("Could not open browser automatically")
        out.info(f"Open manually: {url}")


# ═══════════════════════════════════════════════════════════════
#  Commands: login (top-level alias for portal-login)
# ═══════════════════════════════════════════════════════════════

def cmd_login(args):
    """Link device to the Tectonic Connector Portal (alias for cf portal-login)."""
    _cf_portal_login(args)


# ═══════════════════════════════════════════════════════════════
#  Commands: server
# ═══════════════════════════════════════════════════════════════

def cmd_server(args):
    action = args.server_action

    if action == "start":
        from porter.server import start
        start(mode=args.mode, workers=args.workers, force=args.force)

    elif action == "stop":
        from porter.server import stop
        stop()

    elif action == "restart":
        from porter.server import restart
        restart(mode=args.mode, workers=args.workers)

    elif action == "status":
        from porter.server import status
        status()

    elif action == "logs":
        from porter.server import logs
        lines = args.lines if hasattr(args, "lines") and args.lines else 50
        logs(lines=lines, follow=args.follow, which=args.which)

    elif action == "deps":
        from porter.server import install_deps
        install_deps()

    else:
        _server_help()


def _server_help():
    out.error("Missing server action")
    print()
    out.info("Usage: porter server <action>")
    print()
    out.info("Actions:")
    out.bullet("porter server start              Start the server")
    out.bullet("porter server stop               Stop the server")
    out.bullet("porter server restart            Restart the server")
    out.bullet("porter server status             Check if running")
    out.bullet("porter server logs [n]           Show last n lines")
    out.bullet("porter server logs --follow      Tail logs")
    out.bullet("porter server deps               Install dependencies")
    print()
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  Commands: cloudflare
# ═══════════════════════════════════════════════════════════════

def cmd_cf(args):
    action = args.cf_action

    if action == "connect":
        from porter.cloudflare import CloudflareCLI
        cf = CloudflareCLI()
        ok = cf.connect()
        sys.exit(0 if ok else 1)

    elif action == "status":
        from porter.cloudflare import CloudflareCLI
        cf = CloudflareCLI()
        cf.status()

    elif action == "disconnect":
        from porter.cloudflare import CloudflareCLI
        cf = CloudflareCLI()
        cf.disconnect()

    elif action == "refresh":
        from porter.cloudflare import CloudflareCLI
        cf = CloudflareCLI()
        ok = cf.refresh()
        sys.exit(0 if ok else 1)

    elif action == "portal-login":
        _cf_portal_login(args)

    elif action == "connections":
        _cf_portal_connections()

    elif action == "use":
        _cf_portal_use(getattr(args, "cf_value", None))

    elif action == "sync":
        _cf_portal_sync()

    elif action == "accounts":
        _cf_portal_accounts()

    elif action == "forget":
        _cf_portal_forget(getattr(args, "cf_value", None))

    elif action in ("portal-status", "portal-status"):
        _cf_portal_status()

    else:
        _cf_help()


def _paths():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return (
        os.path.join(root, "config.json"),
        os.path.join(root, "tokens.json"),
    )


def _read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def _write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _require_connector_libs():
    try:
        import httpx  # noqa: F401
    except ImportError as e:
        out.error(f"Missing dependency: {e}")
        out.info("Run: pip install httpx")
        sys.exit(1)

    # Import portal_client from project root
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        import portal_client
        return portal_client
    except ImportError as e:
        out.error(f"Cannot import portal_client: {e}")
        out.info("Ensure portal_client.py is in the Porter project root")
        sys.exit(1)


def _write_tokens_payload(payload):
    """Merge a connector payload ({client_info, tokens}) into tokens.json."""
    _, tokens_file = _paths()
    data = _read_json(tokens_file, default={})
    tokens = payload.get("tokens") or {}
    client_info = payload.get("client_info")
    if isinstance(client_info, dict) and client_info.get("client_id"):
        tokens.setdefault("client_id", client_info["client_id"])
        if not (isinstance(data.get("client_info"), dict)
                and data["client_info"].get("client_id")):
            data["client_info"] = client_info
    data["tokens"] = tokens
    _write_json(tokens_file, data)


def _add_portal_accounts(pc, url, api_key, conns, chosen_ids, cfg):
    """
    Pull, store and verify every selected connection; the first one becomes
    the active account. Each account is checked with exactly one forced
    token refresh so a broken link is visible immediately.
    """
    from cloudflare_client import (
        upsert_account,
        activate_account,
        verify_payload,
        save_config_entry,
    )
    results = []
    for cid in chosen_ids:
        conn = next((c for c in conns if c["id"] == cid), None)
        if conn is None:
            continue
        label = conn.get("cf_account_name") or conn.get("label") or cid[:8]
        try:
            payload = pc.pull_token(url, api_key, cid)
        except pc.PortalError as e:
            results.append({"id": cid, "label": label, "ok": False, "detail": str(e)[:140]})
            out.error(f"{label} — pull failed: {str(e)[:100]}")
            continue

        ok, detail = verify_payload(payload)
        upsert_account(
            cid,
            label=conn.get("label", ""),
            account_name=conn.get("cf_account_name", ""),
            payload=payload,
            verify={"ok": ok, "detail": detail, "ts": int(time.time())},
            cfg=cfg,
        )
        results.append({"id": cid, "label": label, "ok": ok, "detail": detail})
        if ok:
            out.success(f"{label} — verified ({detail})")
        else:
            out.error(f"{label} — verification FAILED: {detail}")

    # First verified becomes active; fall back to first selected.
    ok_ids = [r["id"] for r in results if r["ok"]]
    active_id = ok_ids[0] if ok_ids else chosen_ids[0]
    activate_account(active_id, base_url=url, api_key=api_key, cfg=cfg)
    save_config_entry(cfg, url, api_key, active_id)
    return results


def _parse_account_selection(pick, conns):
    """Parse '1,3' / '*' / '' into a list of connection ids."""
    pick = (pick or "").strip().lower()
    if pick in ("*", "all", "a"):
        idxs = list(range(len(conns)))
    elif not pick:
        idxs = [0]
    else:
        idxs = []
        for tok in pick.replace(" ", "").split(","):
            if tok.isdigit() and 1 <= int(tok) <= len(conns):
                i = int(tok) - 1
                if i not in idxs:
                    idxs.append(i)
        if not idxs:
            idxs = [0]
    return [conns[i]["id"] for i in idxs]


def _cf_portal_login(args):
    pc = _require_connector_libs()
    config_file, _ = _paths()
    cfg = _read_json(config_file)
    # Priority: saved URL -> primary Tectonic Connector Portal.
    default_url = cfg.get("portal_url", "") or DEFAULT_PORTAL_URL

    out.header("Tectonic Connector Portal login")
    url = (getattr(args, "cf_value", None) or "").strip()
    if not url:
        url = input(f"Connector Portal URL [{default_url}]: ").strip() or default_url
    if not url:
        out.error("Connector Portal URL is required")
        sys.exit(1)
    identifier = input("Email or username: ").strip()
    password = getpass.getpass("Password: ")
    if not identifier or not password:
        out.error("Credentials required")
        sys.exit(1)

    try:
        api_key = pc.exchange_credentials(url, identifier, password)
        out.success("Authenticated — device API key issued")

        conns = pc.list_connections(url, api_key)
        if not conns:
            out.error("No Cloudflare connections in that portal.")
            out.info("Connect one in the Tectonic Connector Portal dashboard, then run this again.")
            sys.exit(1)

        print()
        for i, c in enumerate(conns, 1):
            label = c.get("cf_account_name") or c.get("label")
            out.bullet(f"{i}. {label}  {out.dim(c['id'])}")

        if len(conns) == 1:
            chosen_ids = [conns[0]["id"]]
        else:
            pick = input(f"\nAdd which accounts? [1] (e.g. 1,3 or * for all): ").strip()
            chosen_ids = _parse_account_selection(pick, conns)

        results = _add_portal_accounts(pc, url, api_key, conns, chosen_ids, cfg)
        added = len(results)
        failed = len([r for r in results if not r["ok"]])
        active_label = results[0]["label"] if results else "?"
        summary = f"Added {added} account{'s' if added != 1 else ''} via Porter Connector — active: {active_label}"
        if failed:
            out.warning(summary + f" ({failed} failed)")
        else:
            out.success(summary)
        out.info("Restart the portal server (porter server restart) to pick up credentials.")
    except pc.PortalError as e:
        out.error(str(e))
        sys.exit(1)


def _cf_portal_accounts():
    """List Cloudflare accounts stored locally on this device."""
    from cloudflare_client import load_accounts
    config_file, _ = _paths()
    cfg = _read_json(config_file)
    active = cfg.get("portal_connection_id")
    accounts = load_accounts()
    print()
    if not accounts:
        out.info("No accounts stored on this device. Add one: porter cf portal-login")
        return
    for a in sorted(accounts.values(), key=lambda x: x.get("added_at") or 0):
        marker = "*active*" if a["id"] == active else ""
        lv = a.get("last_verify")
        if lv:
            badge = out.c("verified", "green") if lv.get("ok") else out.c("verify failed", "red")
            extra = f"  ({badge})"
        else:
            extra = ""
        name = a.get("account_name") or a.get("label") or a["id"][:8]
        out.table_row(name, out.dim(a["id"][:8]), (marker + extra).strip())
    if not accounts:
        pass


def _cf_portal_forget(value):
    """Forget a stored account on this device (id or unique prefix)."""
    if not value:
        out.error("Usage: porter cf forget <connection-id-or-prefix>")
        sys.exit(1)
    from cloudflare_client import load_accounts, forget_account
    accounts = load_accounts()
    matches = [cid for cid in accounts if cid == value or cid.startswith(value)]
    if not matches:
        out.error(f"No stored account matches '{value}'")
        sys.exit(1)
    if len(matches) > 1:
        out.error("Ambiguous prefix — be more specific:")
        for m in matches:
            out.bullet(out.dim(m))
        sys.exit(1)
    cfg = _read_json(_paths()[0])
    was_active = cfg.get("portal_connection_id") == matches[0]
    forget_account(matches[0])
    nxt = _read_json(_paths()[0]).get("portal_connection_id")
    out.success(f"Forgot account {matches[0][:8]}")
    if was_active and nxt:
        entry = accounts.get(nxt) or {}
        out.info(f"Active account switched to {(entry.get('account_name') or entry.get('label') or nxt[:8])}")


def _cf_portal_connections():
    pc = _require_connector_libs()
    config_file, _ = _paths()
    cfg = _read_json(config_file)
    url = cfg.get("portal_url") or DEFAULT_PORTAL_URL
    api_key = cfg.get("portal_api_key")
    active = cfg.get("portal_connection_id")
    if not (url and api_key):
        out.error("Not linked to a Connector Portal. Run: porter cf portal-login")
        sys.exit(1)
    try:
        conns = pc.list_connections(url, api_key)
    except pc.PortalError as e:
        out.error(str(e))
        sys.exit(1)
    from cloudflare_client import load_accounts
    stored = load_accounts()
    print()
    for c in conns:
        parts = []
        if c["id"] == active:
            parts.append("*active*")
        elif c["id"] in stored:
            parts.append("+stored")
        out.table_row(c.get("cf_account_name") or c.get("label"), out.dim(c["id"]), " ".join(parts))
    if not conns:
        out.info("No connections found in that portal.")


def _cf_portal_use(connection_id):
    pc = _require_connector_libs()
    if not connection_id:
        out.error("Usage: porter cf use <connection-id>")
        sys.exit(1)
    config_file, _ = _paths()
    cfg = _read_json(config_file)
    url = cfg.get("portal_url") or DEFAULT_PORTAL_URL
    api_key = cfg.get("portal_api_key")
    if not api_key:
        out.error("Not linked to a Connector Portal. Run: porter cf portal-login")
        sys.exit(1)
    from cloudflare_client import (
        load_accounts,
        activate_account,
        upsert_account,
        save_config_entry,
        verify_connection,
    )
    label = connection_id[:8]
    try:
        conns = pc.list_connections(url, api_key)
        # Accept full id or unique prefix.
        matches = [c for c in conns if c["id"] == connection_id or c["id"].startswith(connection_id)]
        chosen = matches[0] if len(matches) == 1 else None
        if chosen is None:
            if len(matches) > 1:
                out.error("Ambiguous prefix — be more specific:")
                for m in matches:
                    out.bullet(out.dim(m["id"]))
            else:
                out.error(f"Connection {connection_id} not found in that portal")
            sys.exit(1)
        connection_id = chosen["id"]
        payload = pc.pull_token(url, api_key, connection_id)
        upsert_account(
            connection_id,
            label=chosen.get("label", ""),
            account_name=chosen.get("cf_account_name", ""),
            payload=payload,
            cfg=cfg,
        )
        label = chosen.get("cf_account_name") or chosen.get("label") or label
    except pc.PortalError as e:
        # Offline? Fall back to the locally stored copy of this account.
        stored = load_accounts().get(connection_id)
        if not (stored and stored.get("tokens")):
            out.error(str(e))
            sys.exit(1)
        out.warning(f"Portal unreachable ({str(e)[:60]}) — using stored credentials")

    if activate_account(connection_id, base_url=url, api_key=api_key):
        ok, detail = verify_connection()
        if ok:
            out.success(f"Switched to {label} — verified ({detail})")
        else:
            out.error(f"Switched to {label} — verification FAILED: {detail}")
            sys.exit(1)
    else:
        out.error("No stored credentials for that account")


def _cf_portal_sync():
    pc = _require_connector_libs()
    config_file, _ = _paths()
    cfg = _read_json(config_file)
    url = cfg.get("portal_url") or DEFAULT_PORTAL_URL
    api_key = cfg.get("portal_api_key")
    conn_id = cfg.get("portal_connection_id")
    if not (api_key and conn_id):
        out.error("Not linked to a Connector Portal. Run: porter cf portal-login")
        sys.exit(1)
    from cloudflare_client import upsert_account, save_config_entry, verify_connection
    try:
        payload = pc.pull_token(url, api_key, conn_id)
        _write_tokens_payload(payload)
        upsert_account(conn_id, payload=payload, cfg=cfg)
        save_config_entry(cfg, url, api_key, conn_id)
        ok, detail = verify_connection()
        if ok:
            out.success(f"Re-pulled Cloudflare credentials — verified ({detail})")
        else:
            out.error(f"Re-pulled credentials but verification FAILED: {detail}")
            sys.exit(1)
    except pc.PortalError as e:
        out.error(str(e))
        sys.exit(1)


def _cf_portal_status():
    """Show portal connection status."""
    config_file, _ = _paths()
    cfg = _read_json(config_file)
    url = cfg.get("portal_url") or DEFAULT_PORTAL_URL
    api_key = cfg.get("portal_api_key")
    conn_id = cfg.get("portal_connection_id")

    out.header("Portal Connection Status")
    out.table_row("Portal URL", url)

    if api_key:
        masked = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        out.table_row("API Key", masked)
    else:
        out.table_row("API Key", f"{out.c('not set', 'yellow')}")

    if conn_id:
        out.table_row("Active Account", conn_id[:12] + "...")
    else:
        out.table_row("Active Account", f"{out.c('none', 'yellow')}")

    # Check stored accounts
    from cloudflare_client import load_accounts
    accounts = load_accounts()
    out.table_row("Stored Accounts", str(len(accounts)))

    if accounts:
        print()
        for a in sorted(accounts.values(), key=lambda x: x.get("added_at") or 0):
            marker = " *active*" if a["id"] == conn_id else ""
            lv = a.get("last_verify")
            if lv:
                badge = out.c("verified", "green") if lv.get("ok") else out.c("failed", "red")
                extra = f"  ({badge})"
            else:
                extra = ""
            name = a.get("account_name") or a.get("label") or a["id"][:8]
            out.table_row(f"  {name}", out.dim(a["id"][:8]), (marker + extra).strip())

    # Check if we can reach the portal
    print()
    pc = _require_connector_libs()
    try:
        conns = pc.list_connections(url, api_key)
        out.success(f"Portal reachable ({len(conns)} connection{'s' if len(conns) != 1 else ''})")
    except pc.PortalError as e:
        out.warning(f"Portal unreachable: {str(e)[:80]}")
    except Exception as e:
        out.warning(f"Portal check failed: {str(e)[:80]}")

    print()


def _cf_help():
    out.error("Missing cloudflare action")
    print()
    out.info("Usage: porter cf <action>")
    print()
    out.info("Actions:")
    out.bullet("porter cf connect                Connect Cloudflare account (OAuth)")
    out.bullet("porter cf status                 Check Cloudflare connection status")
    out.bullet("porter cf disconnect             Disconnect from Cloudflare")
    out.bullet("porter cf refresh                Refresh OAuth token")
    out.bullet("porter cf portal-login [url]     Link device to the Connector Portal")
    out.bullet("porter cf portal-status           Show portal connection status")
    out.bullet("porter cf connections            List Connector Portal connections")
    out.bullet("porter cf use <connection-id>    Switch active connector connection")
    out.bullet("porter cf sync                   Force re-pull active connector connection")
    out.bullet("porter cf accounts               List accounts stored on this device")
    out.bullet("porter cf forget <id>            Forget a stored account (id or prefix)")
    print()
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  Commands: tunnels
# ═══════════════════════════════════════════════════════════════

def cmd_tunnels(args):
    """List all tunnels."""
    api = _api(args)
    data = api.get("/api/tunnels")

    if isinstance(data, list):
        tunnels = data
    elif isinstance(data, dict):
        tunnels = data.get("tunnels", {})
    else:
        tunnels = []

    out.header("Active Tunnels")

    if not tunnels:
        out.info("No active tunnels")
        print()
        return

    count = len(tunnels) if isinstance(tunnels, list) else len(tunnels)
    out.subheader(f"{count} tunnel(s)")

    items = tunnels if isinstance(tunnels, list) else tunnels.values()
    for t in items:
        url = t.get("url", "N/A")
        sub = t.get("subdomain", "?")
        port = t.get("port", "?")
        domain = t.get("domain", "")
        healthy = t.get("healthy", False)
        s = out.OK if healthy else out.ERR
        out.table_row(f"  {sub}.{domain}", f"{s} -> localhost:{port}")

    print()
    api.close()


def cmd_tunnel(args):
    action = args.tunnel_action

    if action == "create":
        _tunnel_create(args)
    elif action == "stop":
        _tunnel_stop(args)
    elif action == "restart":
        _tunnel_restart(args)
    else:
        _tunnel_help()


def _tunnel_create(args):
    sub = args.subdomain
    port = args.port

    if not sub or not port:
        out.error("Missing subdomain or port")
        out.info("Usage: porter tunnel create <subdomain> <port> [--protocol http2|quic]")
        print()
        sys.exit(1)

    try:
        port = int(port)
    except ValueError:
        _die(f"Invalid port: {port} (must be a number)")

    protocol = getattr(args, "protocol", "http2") or "http2"
    if protocol not in ("http2", "quic", "auto"):
        _die(f"Invalid protocol: {protocol} (use http2, quic, or auto)")

    api = _api(args)
    out.header(f"Creating Tunnel: {sub}")

    domains = api.get("/api/domains")
    active = ""
    if isinstance(domains, dict):
        active = domains.get("active", "")
        zones = domains.get("zones", [])
        if not active and zones:
            active = zones[0].get("name", "")
    if not active:
        domain_list = domains.get("domains", []) if isinstance(domains, dict) else []
        if domain_list:
            active = domain_list[0].get("name", "") if isinstance(domain_list[0], dict) else domain_list[0]

    if not active:
        _die("No domains found. Run: porter cf connect")

    out.info(f"Domain:    {active}")
    out.info(f"Subdomain: {sub}")
    out.info(f"Port:      {port}")
    out.info(f"Protocol:  {protocol}")
    out.info("Creating tunnel...")

    result = api.post("/api/tunnel/create", {
        "subdomain": sub,
        "port": port,
        "domain": active,
        "protocol": protocol,
    })

    if result.get("success") or result.get("url"):
        url = result.get("url", f"https://{sub}.{active}")
        out.success(f"Tunnel live: {url}")
    else:
        msg = result.get("error", result.get("message", "Unknown error"))
        out.error(f"Failed: {msg}")
        sys.exit(1)

    api.close()


def _tunnel_stop(args):
    sub = args.subdomain
    if not sub:
        out.error("Missing subdomain")
        out.info("Usage: porter tunnel stop <subdomain>")
        print()
        sys.exit(1)

    api = _api(args)
    out.header(f"Stopping Tunnel: {sub}")

    domains = api.get("/api/domains")
    active = ""
    if isinstance(domains, dict):
        active = domains.get("active", "")
    tunnel_key = f"{active}/{sub}" if active else sub

    result = api.post(f"/api/tunnel/stop/{tunnel_key}")

    if result.get("success"):
        out.success(f"Tunnel stopped: {sub}")
    else:
        msg = result.get("error", "Not found")
        out.error(f"Failed: {msg}")

    api.close()


def _tunnel_restart(args):
    api = _api(args)
    out.header("Restarting cloudflared")
    result = api.post("/api/tunnel/restart")

    if result.get("success"):
        proto = result.get("protocol", "unknown")
        out.success(f"cloudflared restarted (protocol={proto})")
    else:
        msg = result.get("error", "Unknown error")
        out.error(f"Failed: {msg}")

    api.close()


def _tunnel_help():
    out.error("Missing tunnel action")
    print()
    out.info("Usage: porter tunnel <action>")
    print()
    out.info("Actions:")
    out.bullet("porter tunnel create <sub> <port>  Expose a local service")
    out.bullet("porter tunnel stop <subdomain>      Stop a tunnel")
    out.bullet("porter tunnel restart               Restart cloudflared")
    print()
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  Commands: shorturl
# ═══════════════════════════════════════════════════════════════

def cmd_shorturl(args):
    """Shorten a URL using is.gd (free, no API key required)."""
    url = getattr(args, "url", None)
    if not url:
        out.error("Missing URL")
        out.info("Usage: porter shorturl <url>")
        print()
        sys.exit(1)

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    out.info(f"Shortening: {url}")

    try:
        import httpx
        from urllib.parse import quote

        api_url = f"https://is.gd/create.php?format=json&url={quote(url, safe='')}"
        resp = httpx.get(api_url, timeout=10, headers={"User-Agent": "Porter-CLI/2.0"})
        data = resp.json()
        short_url = data.get("shorturl")
        if short_url:
            out.success(f"Short URL: {short_url}")
            # Try to copy to clipboard
            try:
                import subprocess
                if sys.platform == "darwin":
                    subprocess.run(["pbcopy"], input=short_url.encode(), check=True)
                elif sys.platform.startswith("linux"):
                    subprocess.run(["xclip", "-selection", "clipboard"], input=short_url.encode(), check=True)
                out.info("Copied to clipboard")
            except Exception:
                pass
        else:
            out.error("Shortening failed")
            sys.exit(1)
    except ImportError:
        out.error("httpx is required: pip install httpx")
        sys.exit(1)
    except Exception as e:
        out.error(f"Failed: {e}")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  Commands: domains
# ═══════════════════════════════════════════════════════════════

def cmd_domains(args):
    api = _api(args)
    data = api.get("/api/domains")

    out.header("Cloudflare Domains")

    domains = []
    active_name = ""
    if isinstance(data, dict):
        active_name = data.get("active", "")
        for z in data.get("zones", []):
            if isinstance(z, dict):
                name = z.get("name", "")
                domains.append({
                    "name": name,
                    "active": name == active_name,
                    "status": z.get("status", ""),
                })
        if not domains:
            for d in data.get("domains", []):
                if isinstance(d, str):
                    domains.append({"name": d, "active": d == active_name})
                elif isinstance(d, dict):
                    name = d.get("name", "")
                    domains.append({"name": name, "active": d.get("active", name == active_name)})
    elif isinstance(data, list):
        for d in data:
            if isinstance(d, str):
                domains.append({"name": d, "active": False})
            elif isinstance(d, dict):
                name = d.get("name", "")
                domains.append({"name": name, "active": d.get("active", False)})

    if not domains:
        out.info("No domains found. Run: porter cf connect")
        print()
        api.close()
        return

    for d in domains:
        name = d.get("name", "")
        active = d.get("active", False)
        status = f" {out.OK} active" if active else ""
        out.table_row(f"  {name}", status)

    print()
    api.close()


def cmd_domain(args):
    action = args.domain_action

    if action == "active":
        api = _api(args)
        data = api.get("/api/domains")
        active = data.get("active", "") if isinstance(data, dict) else ""

        if hasattr(args, "domain_name") and args.domain_name:
            result = api.post("/api/domains/active", {"domain": args.domain_name})
            if result.get("success"):
                out.success(f"Active domain: {args.domain_name}")
            else:
                out.error("Failed to set active domain")
        else:
            if active:
                out.success(f"Active domain: {active}")
            else:
                out.info("No active domain set")
        api.close()
    else:
        out.error(f"Unknown domain action: {action}")
        out.info("Usage: porter domain active [domain-name]")
        print()
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  Commands: ports (cross-platform)
# ═══════════════════════════════════════════════════════════════

def cmd_ports(args):
    if hasattr(args, "port_action") and args.port_action:
        action = args.port_action
        if action == "check":
            _port_check(args.port_number)
        elif action == "pid":
            _port_pid(args.port_number)
        else:
            _ports_help()
        return

    out.header("Listening Ports")

    ports = list_listening_ports()
    if not ports:
        out.info("No listening ports found")
        print()
        return

    seen = set()
    count = 0
    for port, proto, pid in ports:
        key = (port, proto)
        if key in seen:
            continue
        seen.add(key)
        pid_str = f"  PID={pid}" if pid else ""
        out.table_row(f"  :{port}", f"{proto.upper()}{pid_str}")
        count += 1

    if count == 0:
        out.info("No listening ports found")

    print()


def _port_check(port):
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", int(port)))
        sock.close()
        if result == 0:
            out.warning(f"Port {port} is in use")
        else:
            out.success(f"Port {port} is available")
    except Exception as e:
        out.error(f"Could not check port: {e}")


def _port_pid(port):
    pid = find_pid_by_port(int(port))
    if pid:
        out.info(f"Port {port} -> PID {pid}")
        # Try to get process name
        if IS_WINDOWS and not IS_LINUX:
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, timeout=5,
                )
                parts = result.stdout.strip().split(",")
                if parts:
                    proc_name = parts[0].strip('"')
                    out.info(f"Process: {proc_name}")
            except Exception:
                pass
        else:
            # Try /proc first (Linux), fall back to ps (macOS/BSD)
            try:
                with open(f"/proc/{pid}/comm") as f:
                    out.info(f"Process: {f.read().strip()}")
            except (FileNotFoundError, PermissionError):
                try:
                    result = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "comm="],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.stdout.strip():
                        out.info(f"Process: {result.stdout.strip()}")
                except Exception:
                    pass
    else:
        out.info(f"Port {port} is not in use")


def _ports_help():
    out.error("Missing ports action")
    print()
    out.info("Usage: porter ports [action]")
    print()
    out.info("Actions:")
    out.bullet("porter ports                    List all listening ports")
    out.bullet("porter ports check <port>       Check if a port is in use")
    out.bullet("porter ports pid <port>         Get PID using a port")
    print()
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  Commands: keys
# ═══════════════════════════════════════════════════════════════

def cmd_keys(args):
    action = args.key_action

    if not action or action in ("list", "ls"):
        _keys_list(args)
    elif action == "create":
        _keys_create(args)
    elif action in ("delete", "rm"):
        _keys_delete_raw(args)
    else:
        _keys_help()


def _keys_list(args):
    api = _api(args)
    data = api.get("/api/keys")
    keys = data.get("keys", []) if isinstance(data, dict) else []

    out.header("API Keys")

    if not keys:
        out.info("No API keys")
        out.info("Create one: porter keys create <name>")
        print()
        api.close()
        return

    for k in keys:
        name = k.get("name", "")
        prefix = k.get("key_prefix", "")
        created = k.get("created_at", "")
        last_used = k.get("last_used", "never")
        out.table_row(f"  {name}", f"{prefix}  created={created}  last_used={last_used}")

    print()
    api.close()


def _keys_create(args):
    name = args.name
    if not name:
        out.error("Missing key name")
        out.info("Usage: porter keys create <name>")
        print()
        sys.exit(1)

    api = _api(args)
    out.header(f"Creating API Key: {name}")
    result = api.post("/api/keys", {"name": name})

    if result.get("success"):
        out.print_key(result)
    else:
        msg = result.get("error", "Unknown error")
        out.error(f"Failed: {msg}")

    api.close()


def _keys_delete_raw(args):
    key_id = args.name
    if not key_id:
        out.error("Missing key ID")
        out.info("Usage: porter keys delete <key_id>")
        print()
        sys.exit(1)

    api = _api(args)
    out.header(f"Deleting API Key: {key_id}")
    result = api.delete(f"/api/keys/{key_id}")

    if result.get("success"):
        out.success("API key deleted")
    else:
        msg = result.get("error", "Not found")
        out.error(f"Failed: {msg}")

    api.close()


def _keys_help():
    out.error("Missing keys action")
    print()
    out.info("Usage: porter keys <action>")
    print()
    out.info("Actions:")
    out.bullet("porter keys                     List all API keys")
    out.bullet("porter keys create <name>       Create a new API key")
    out.bullet("porter keys delete <key_id>     Delete an API key")
    print()
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  Commands: config
# ═══════════════════════════════════════════════════════════════

def cmd_config(args):
    if hasattr(args, "config_action") and args.config_action:
        action = args.config_action
    elif hasattr(args, "subcmd") and args.subcmd:
        action = args.subcmd
    else:
        _config_show()
        return

    if action in ("show", "list", "ls"):
        _config_show()
    elif action == "set":
        _config_set(args)
    elif action == "get":
        _config_get(args)
    elif action in ("unset", "remove", "rm"):
        _config_unset(args)
    elif action == "init":
        _config_init()
    else:
        _config_help()


def _config_show():
    cfg = load_config()

    out.header("Configuration")
    out.table_row("File", str(out.dim("~/.porter/config.json")))
    out.table_row("Platform", OS_NAME)
    print()

    if not cfg:
        out.info("No configuration found")
        out.info("Run: porter setup")
        print()
        return

    display = {}
    for k, v in cfg.items():
        if k in ("passcode", "api_key") and v:
            display[k] = f"{str(v)[:6]}...{str(v)[-3:]}"
        else:
            display[k] = v

    for k, v in display.items():
        out.table_row(f"  {k}", str(v))

    print()


def _config_set(args):
    key = args.config_key
    value = args.config_value

    if not key or not value:
        out.error("Missing key or value")
        out.info("Usage: porter config set <key> <value>")
        print()
        out.info("Keys:")
        out.bullet("server     Server URL")
        out.bullet("passcode   Passcode")
        out.bullet("api_key    API key")
        out.bullet("domain     Active domain")
        out.bullet("port       Server port")
        print()
        sys.exit(1)

    cfg = load_config()
    key_map = {
        "server": "server_url",
        "url": "server_url",
        "passcode": "passcode",
        "api_key": "api_key",
        "key": "api_key",
        "domain": "domain",
        "port": "port",
    }
    full_key = key_map.get(key, key)
    cfg[full_key] = value
    save_config(cfg)
    out.success(f"{full_key} = {value}")


def _config_get(args):
    key = args.config_key
    if not key:
        _config_show()
        return

    cfg = load_config()
    key_map = {
        "server": "server_url",
        "url": "server_url",
        "passcode": "passcode",
        "api_key": "api_key",
        "key": "api_key",
        "domain": "domain",
        "port": "port",
    }
    full_key = key_map.get(key, key)
    value = cfg.get(full_key)

    if value is not None:
        print(value)
    else:
        out.info(f"{full_key} not set")


def _config_unset(args):
    key = args.config_key
    if not key:
        out.error("Missing key")
        out.info("Usage: porter config unset <key>")
        print()
        sys.exit(1)

    cfg = load_config()
    key_map = {
        "server": "server_url",
        "url": "server_url",
        "passcode": "passcode",
        "api_key": "api_key",
        "key": "api_key",
        "domain": "domain",
    }
    full_key = key_map.get(key, key)
    if full_key in cfg:
        del cfg[full_key]
        save_config(cfg)
        out.success(f"Removed {full_key}")
    else:
        out.info(f"{full_key} not set")


def _config_init():
    cfg = load_config()
    if cfg:
        out.info("Config already exists")
        choice = input("  Overwrite? [y/N]: ").strip().lower()
        if choice != "y":
            return

    import hashlib
    passcode = input("  Passcode [123456]: ").strip() or "123456"
    passcode_hash = hashlib.sha256(passcode.encode()).hexdigest()

    new_cfg = {
        "port": 7262,
        "passcode_hash": passcode_hash,
        "domain": "",
        "subdomain": "",
        "tunnel_token": "",
        "account_id": "",
        "tunnel_id": "",
    }
    save_config(new_cfg)
    out.success("Config initialized")
    out.info("Next: porter cf connect")


def _config_help():
    out.error("Missing config action")
    print()
    out.info("Usage: porter config [action]")
    print()
    out.info("Actions:")
    out.bullet("porter config                    Show all config")
    out.bullet("porter config set <key> <value>  Set a config value")
    out.bullet("porter config get <key>          Get a config value")
    out.bullet("porter config unset <key>        Remove a config key")
    out.bullet("porter config init               Initialize fresh config")
    print()
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  Commands: setup
# ═══════════════════════════════════════════════════════════════

def cmd_setup(args):
    out.header("Porter Setup Wizard")
    print()

    cfg = load_config()

    # Step 1: Config
    if not cfg.get("server_url"):
        out.info("Step 1: Server URL")
        url = input("  Server URL [http://localhost:7262]: ").strip()
        if not url:
            url = "http://localhost:7262"
        set_server_url(url)
        out.success(f"Server: {url}")
        print()
    else:
        out.success(f"Server already configured: {cfg.get('server_url')}")

    # Step 2: Auth
    if not cfg.get("api_key") and not cfg.get("passcode"):
        out.info("Step 2: Authentication")
        out.info("  1) API Key (recommended)")
        out.info("  2) Passcode")
        choice = input("  Choice [1]: ").strip() or "1"
        print()

        if choice == "1":
            key = input("  API Key: ").strip()
            if key:
                set_api_key(key)
                out.success("API key saved")
        else:
            pwd = getpass.getpass("  Passcode: ")
            if pwd:
                set_passcode(pwd)
                out.success("Passcode saved")
        print()

    # Step 3: Cloudflare / Portal
    out.info("Step 3: Connect Cloudflare")
    out.info("  1) OAuth (browser-based, local machine)")
    out.info("  2) Tectonic Connector Portal (headless/VPS)")
    out.info("  3) Skip")
    choice = input("  Choice [1]: ").strip() or "1"
    print()

    if choice == "1":
        try:
            from porter.cloudflare import CloudflareCLI
            cf = CloudflareCLI()
            cf.connect()
        except ImportError:
            out.error("httpx required: pip install httpx")
    elif choice == "2":
        _cf_portal_login(argparse.Namespace(cf_value=None))
    else:
        out.info("Skipped. Run 'porter login' or 'porter cf connect' later.")
    print()

    # Step 4: First tunnel
    out.info("Step 4: Create your first tunnel")
    choice = input("  Create a tunnel now? [y/N]: ").strip().lower()
    if choice == "y":
        sub = input("  Subdomain [panel]: ").strip() or "panel"
        port = input("  Port [7262]: ").strip() or "7262"
        print()
        try:
            api = _api(argparse.Namespace(url=None, api_key=None, passcode=None))
            result = api.post("/api/tunnel/create", {
                "subdomain": sub,
                "port": int(port),
                "domain": cfg.get("domain", ""),
                "protocol": "http2",
            })
            if result.get("success") or result.get("url"):
                url = result.get("url", f"https://{sub}.{cfg.get('domain', '')}")
                out.success(f"Tunnel live: {url}")
            else:
                out.error("Tunnel creation failed -- check Cloudflare connection")
            api.close()
        except Exception as e:
            out.error(f"Failed: {e}")

    print()
    out.success("Setup complete!")
    out.info("porter --help  to see all commands")
    print()


# ═══════════════════════════════════════════════════════════════
#  Commands: install
# ═══════════════════════════════════════════════════════════════

def cmd_install(args):
    out.header("Porter Installer")
    print()

    # Platform info
    from porter.platform import ensure_python, ensure_pip, ensure_cloudflared
    info = platform_info()
    out.info(f"Platform: {info['os']}/{info['arch']}")
    out.info(f"Python: {info['python']}")
    print()

    # 1. Check Python
    py = ensure_python()
    out.success(f"Python: {py}")

    # 2. Install deps
    out.info("Installing dependencies...")
    from porter.server import install_deps
    install_deps()
    print()

    # 3. Check cloudflared
    if ensure_cloudflared():
        out.success("cloudflared installed")
    else:
        out.warning("cloudflared not found")
        out.info("Install manually: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
    print()

    # 4. Init config
    from porter.config import load_config as _lc
    cfg = _lc()
    if not cfg:
        out.info("Initializing config...")
        cmd_setup(argparse.Namespace())
    else:
        out.success("Config exists")
    print()

    # 5. Check server
    from porter.server import _read_pid, _is_running, get_port
    pid = _read_pid()
    port = get_port()
    if _is_running(pid):
        out.success(f"Server running on port {port}")
    else:
        out.info("Server not running")
        choice = input("  Start server now? [Y/n]: ").strip().lower()
        if choice != "n":
            from porter.server import start
            start(port=port)

    print()
    out.success("Installation complete!")
    print()


# ═══════════════════════════════════════════════════════════════
#  Commands: platform
# ═══════════════════════════════════════════════════════════════

def cmd_platform(args):
    """Show platform information."""
    info = platform_info()

    out.header("Platform Info")

    out.table_row("OS", info["os"])
    out.table_row("Arch", info["arch"])
    out.table_row("Python", info["python"])
    out.table_row("Termux", str(info["is_termux"]))
    out.table_row("Windows", str(info["is_windows"]))
    out.table_row("macOS", str(info["is_macos"]))
    out.table_row("Linux", str(info["is_linux"]))
    print()

    out.subheader("Available Tools")
    out.table_row("ss", out.OK if info["has_ss"] else out.ERR)
    out.table_row("lsof", out.OK if info["has_lsof"] else out.ERR)
    out.table_row("netstat", out.OK if info["has_netstat"] else out.ERR)
    out.table_row("brew", out.OK if info["has_brew"] else out.ERR)
    out.table_row("cloudflared", out.OK if info["has_cloudflared"] else out.ERR)
    print()


# ═══════════════════════════════════════════════════════════════
#  Top-level status
# ═══════════════════════════════════════════════════════════════

def cmd_status(args):
    api = _api(args)
    data = api.get("/api/tunnel/health")

    out.header("System Status")

    cloudflared = data.get("cloudflared", {})
    running = cloudflared.get("running", False)
    healthy = cloudflared.get("healthy", False)
    pid = cloudflared.get("pid")
    protocol = data.get("protocol", "unknown")
    failures = cloudflared.get("consecutive_failures", 0)

    out.table_row("Cloudflared", f"{out.OK if running else out.ERR} {'Running' if running else 'Stopped'}")
    out.table_row("Health", f"{out.OK if healthy else out.ERR} {'Healthy' if healthy else 'Unhealthy'}")
    out.table_row("PID", str(pid) if pid else "N/A")
    out.table_row("Protocol", protocol)
    out.table_row("Platform", OS_NAME)
    if failures > 0:
        out.table_row("Failures", f"{out.c(str(failures), 'yellow')}")

    tunnels = data.get("tunnels", {})
    count = len(tunnels) if isinstance(tunnels, (dict, list)) else 0
    out.table_row("Tunnels", str(count))

    if count > 0:
        out.subheader("Tunnels")
        if isinstance(tunnels, dict):
            for key, info in tunnels.items():
                if not isinstance(info, dict):
                    continue
                sub = key.split("/")[-1] if "/" in key else key
                domain = key.split("/")[0] if "/" in key else ""
                url = info.get("url", "N/A")
                port = info.get("port", "?")
                h = info.get("healthy", False)
                s = out.OK if h else out.ERR
                out.table_row(f"  {sub}.{domain}", f"{s} {url} -> :{port}")
        elif isinstance(tunnels, list):
            for info in tunnels:
                if not isinstance(info, dict):
                    continue
                sub = info.get("subdomain", "?")
                url = info.get("url", "N/A")
                port = info.get("port", "?")
                h = info.get("healthy", False)
                s = out.OK if h else out.ERR
                out.table_row(f"  {sub}", f"{s} {url} -> :{port}")

    print()
    api.close()


# ═══════════════════════════════════════════════════════════════
#  Main parser
# ═══════════════════════════════════════════════════════════════

def main():
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

    if len(sys.argv) == 1:
        print(HELP)
        sys.exit(0)

    parser = argparse.ArgumentParser(
        prog="porter",
        description="Porter — Cloudflare Tunnel Portal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("--version", "-v", action="version", version=f"porter {__version__}")
    parser.add_argument("--help", "-h", action="store_true", dest="help")
    parser.add_argument("--url", help=argparse.SUPPRESS)
    parser.add_argument("--api-key", help=argparse.SUPPRESS)
    parser.add_argument("--passcode", help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--quiet", "-q", action="store_true", help=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="command")

    # -- gui --
    p_gui = sub.add_parser("gui", add_help=False)
    p_gui.add_argument("--dev", action="store_true", help=argparse.SUPPRESS)

    # -- login (top-level alias for portal-login) --
    p_login = sub.add_parser("login", add_help=False)
    p_login.add_argument("cf_value", nargs="?", help=argparse.SUPPRESS)

    # -- shorturl --
    p_shorturl = sub.add_parser("shorturl", add_help=False)
    p_shorturl.add_argument("url", nargs="?", help=argparse.SUPPRESS)

    # -- server --
    p_server = sub.add_parser("server", add_help=False)
    p_server.add_argument("server_action", nargs="?", help=argparse.SUPPRESS)
    p_server.add_argument("server_args", nargs="*", help=argparse.SUPPRESS)
    p_server.add_argument("--mode", choices=["prod", "dev"], default="prod", help=argparse.SUPPRESS)
    p_server.add_argument("--workers", type=int, default=2, help=argparse.SUPPRESS)
    p_server.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    p_server.add_argument("--follow", "-f", action="store_true", dest="follow", help=argparse.SUPPRESS)
    p_server.add_argument("--lines", "-n", type=int, default=50, help=argparse.SUPPRESS)
    p_server.add_argument("--which", "-w", default="portal", help=argparse.SUPPRESS)

    # -- cf (cloudflare) --
    p_cf = sub.add_parser("cf", add_help=False)
    p_cf.add_argument("cf_action", nargs="?", help=argparse.SUPPRESS)
    p_cf.add_argument("cf_value", nargs="?", help=argparse.SUPPRESS)

    # -- cloudflare alias --
    p_cloudflare = sub.add_parser("cloudflare", add_help=False)
    p_cloudflare.add_argument("cf_action", nargs="?", help=argparse.SUPPRESS)
    p_cloudflare.add_argument("cf_value", nargs="?", help=argparse.SUPPRESS)

    # -- tunnels --
    p_tunnels = sub.add_parser("tunnels", add_help=False)

    # -- tunnel --
    p_tunnel = sub.add_parser("tunnel", add_help=False)
    p_tunnel.add_argument("tunnel_action", nargs="?", help=argparse.SUPPRESS)
    p_tunnel.add_argument("subdomain", nargs="?", help=argparse.SUPPRESS)
    p_tunnel.add_argument("port", nargs="?", help=argparse.SUPPRESS)
    p_tunnel.add_argument("--protocol", choices=["http2", "quic", "auto"], help=argparse.SUPPRESS)

    # -- domains --
    p_domains = sub.add_parser("domains", add_help=False)

    # -- domain --
    p_domain = sub.add_parser("domain", add_help=False)
    p_domain.add_argument("domain_action", nargs="?", help=argparse.SUPPRESS)
    p_domain.add_argument("domain_name", nargs="?", help=argparse.SUPPRESS)

    # -- ports --
    p_ports = sub.add_parser("ports", add_help=False)
    p_ports.add_argument("port_action", nargs="?", help=argparse.SUPPRESS)
    p_ports.add_argument("port_number", nargs="?", help=argparse.SUPPRESS)

    # -- keys --
    p_keys = sub.add_parser("keys", add_help=False)
    p_keys.add_argument("key_action", nargs="?", help=argparse.SUPPRESS)
    p_keys.add_argument("name", nargs="?", help=argparse.SUPPRESS)

    # -- config --
    p_config = sub.add_parser("config", add_help=False)
    p_config.add_argument("config_action", nargs="?", help=argparse.SUPPRESS)
    p_config.add_argument("config_key", nargs="?", help=argparse.SUPPRESS)
    p_config.add_argument("config_value", nargs="?", help=argparse.SUPPRESS)

    # -- setup --
    p_setup = sub.add_parser("setup", add_help=False)

    # -- install --
    p_install = sub.add_parser("install", add_help=False)

    # -- platform --
    p_platform = sub.add_parser("platform", add_help=False)

    # -- status (top-level) --
    p_status = sub.add_parser("status", add_help=False)

    # ── Pre-parse: extract global flags before argparse sees them ──
    raw = sys.argv[1:]
    global_flags = {}
    clean_argv = []
    i = 0
    while i < len(raw):
        if raw[i] == "--passcode" and i + 1 < len(raw):
            global_flags["passcode"] = raw[i + 1]; i += 2
        elif raw[i] == "--api-key" and i + 1 < len(raw):
            global_flags["api_key"] = raw[i + 1]; i += 2
        elif raw[i] == "--url" and i + 1 < len(raw):
            global_flags["url"] = raw[i + 1]; i += 2
        elif raw[i] == "--json":
            global_flags["json"] = True; i += 1
        elif raw[i] in ("-q", "--quiet"):
            global_flags["quiet"] = True; i += 1
        else:
            clean_argv.append(raw[i]); i += 1

    args = parser.parse_args(clean_argv)

    # Inject global flags
    for k, v in global_flags.items():
        setattr(args, k, v)

    if getattr(args, "help", False):
        print(HELP)
        sys.exit(0)

    cmd_map = {
        "gui": cmd_gui,
        "login": cmd_login,
        "shorturl": cmd_shorturl,
        "server": cmd_server,
        "cf": cmd_cf,
        "cloudflare": cmd_cf,
        "tunnels": cmd_tunnels,
        "tunnel": cmd_tunnel,
        "domains": cmd_domains,
        "domain": cmd_domain,
        "ports": cmd_ports,
        "keys": cmd_keys,
        "config": cmd_config,
        "setup": cmd_setup,
        "install": cmd_install,
        "platform": cmd_platform,
        "status": cmd_status,
    }

    handler = cmd_map.get(args.command)
    if handler:
        handler(args)
    else:
        print(HELP)
        sys.exit(1)


if __name__ == "__main__":
    main()
