"""Hosting service — control panel API integration (Hosting Mode).

When ``connection_type == 'hosting'`` ServerAlly talks to a control panel's REST
API instead of opening a shell. Each panel has its own auth scheme and endpoints,
so this module provides a small adapter per panel behind a uniform dispatch.

Supported panels (``server.panel_type``):
- ``cyberpanel`` — cloud-style JSON API (default port 8090, HTTPS)
- ``cpanel``     — UAPI with API-token auth (default port 2083, HTTPS)
- ``plesk``      — REST API v2 with Basic auth (default port 8443, HTTPS)
- ``directadmin``— legacy CMD_API_* with Basic auth (default port 2222, HTTPS)

All calls are read-only or panel-mediated writes (create site / DB / email,
issue SSL). No raw shell commands are run — that is the whole point of Hosting
Mode for shared hosting.

NOTE: panel APIs vary by version. The endpoints below follow each vendor's
documented API; validate against your specific panel version before relying on
the write operations in production.
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import parse_qs

import requests
from requests.auth import HTTPBasicAuth

from app.config import settings
from app.models.server import Server
from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)

# Panels often use self-signed certificates; disable noisy warnings.
requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

_TIMEOUT = 20
DEFAULT_PORTS = {"cyberpanel": 8090, "cpanel": 2083, "plesk": 8443, "directadmin": 2222}


class HostingError(Exception):
    """Raised when a panel API call fails or is unsupported."""


# ── Adapters ────────────────────────────────────────────────────────────────

class _Adapter:
    """Base adapter — subclasses implement the operations a panel supports."""

    def __init__(self, host: str, port: int, username: str, secret: str):
        self.host = host
        self.port = port
        self.username = username
        self.secret = secret

    def _base(self, scheme: str = "https") -> str:
        return f"{scheme}://{self.host}:{self.port}"

    # Operations (override what the panel supports)
    def test_connection(self) -> dict: raise HostingError("test not supported")
    def list_websites(self) -> list[dict]: raise HostingError("Listing websites is not supported for this panel.")
    def create_website(self, body: dict) -> dict: raise HostingError("Creating websites is not supported for this panel.")
    def delete_website(self, domain: str) -> dict: raise HostingError("Deleting websites is not supported for this panel.")
    def issue_ssl(self, domain: str) -> dict: raise HostingError("Issuing SSL is not supported for this panel.")
    def list_databases(self) -> list[dict]: raise HostingError("Listing databases is not supported for this panel.")
    def create_database(self, body: dict) -> dict: raise HostingError("Creating databases is not supported for this panel.")
    def list_email(self, domain: str | None) -> list[dict]: raise HostingError("Listing email is not supported for this panel.")
    def create_email(self, body: dict) -> dict: raise HostingError("Creating email is not supported for this panel.")


class CyberPanelAdapter(_Adapter):
    """CyberPanel remote/cloud JSON API. Each request posts adminUser/adminPass.

    IMPORTANT (validated live 2026-07-04 against CyberPanel on Ubuntu 24.04):
    CyberPanel's adminUser/adminPass HTTP API (``/api/*``) is a CLOUD/REMOTE
    MANAGEMENT surface only — it exposes ``verifyConn``, ``loginAPI``, user
    creation/deletion, packages, ``remoteTransfer``, ``cyberPanelVersion``,
    firewall rules and the ai-scanner. It does NOT expose website listing/
    creation, database creation, or SSL issuance — those live in the
    ``websiteFunctions`` app as session+CSRF web endpoints, not this API.

    So website/DB/SSL operations are NOT available over this API by design. The
    reliable automation path for them is the ``cyberpanel`` CLI over SSH (see
    docs/HOSTING-CYBERPANEL.md, H1). We keep the API adapter for what it CAN do
    (verify the connection) and fail the rest with an honest message rather than
    hitting non-existent endpoints (which return HTTP 404)."""

    # Managed via the cyberpanel CLI over SSH (H1), not this HTTP API.
    _CLI_ONLY = (
        "CyberPanel manages this over SSH (the cyberpanel CLI), not its web API. "
        "Connect this server over SSH and use Ally to run it — panel-API website "
        "management isn't exposed by CyberPanel."
    )

    def _post(self, action: str, params: dict | None = None) -> dict:
        url = f"{self._base()}/api/{action}"
        payload = {"adminUser": self.username, "adminPass": self.secret, **(params or {})}
        try:
            resp = requests.post(url, json=payload, verify=settings.HOSTING_TLS_VERIFY, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            raise HostingError(f"Could not reach CyberPanel: {exc}")
        if resp.status_code == 404:
            raise HostingError(f"CyberPanel has no API endpoint '{action}' (HTTP 404).")
        if resp.status_code >= 400:
            raise HostingError(f"CyberPanel returned HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise HostingError("CyberPanel returned a non-JSON response (check host/port).")
        return data

    def test_connection(self) -> dict:
        # verifyConn is the real endpoint (NOT verifyLogin) — returns {"verifyConn": 1}.
        data = self._post("verifyConn")
        ok = bool(data.get("verifyConn") in (1, "1", True))
        if not ok:
            raise HostingError(data.get("error_message") or "CyberPanel login failed (check admin user / password).")
        return {"ok": True}

    def list_websites(self) -> list[dict]:
        # No adminUser/adminPass API endpoint exists for this in CyberPanel.
        raise HostingError(self._CLI_ONLY)

    def create_website(self, body: dict) -> dict:
        raise HostingError(self._CLI_ONLY)

    def delete_website(self, domain: str) -> dict:
        raise HostingError(self._CLI_ONLY)

    def issue_ssl(self, domain: str) -> dict:
        raise HostingError(self._CLI_ONLY)

    def create_database(self, body: dict) -> dict:
        raise HostingError(self._CLI_ONLY)


class CpanelAdapter(_Adapter):
    """cPanel UAPI with API-token auth (Authorization: cpanel user:token)."""

    def _uapi(self, module: str, func: str, params: dict | None = None) -> dict:
        url = f"{self._base()}/execute/{module}/{func}"
        headers = {"Authorization": f"cpanel {self.username}:{self.secret}"}
        try:
            resp = requests.get(url, headers=headers, params=params or {}, verify=settings.HOSTING_TLS_VERIFY, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            raise HostingError(f"Could not reach cPanel: {exc}")
        # Live cpsrvd returns 403 (not 401) for a bad/forbidden API token — treat both as auth.
        if resp.status_code in (401, 403):
            raise HostingError("cPanel denied the request (check the username and API token, and that the token has access).")
        if resp.status_code >= 400:
            raise HostingError(f"cPanel returned HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise HostingError("cPanel returned a non-JSON response (check host/port).")
        errors = data.get("errors")
        if errors:
            raise HostingError("; ".join(errors) if isinstance(errors, list) else str(errors))
        return data

    def test_connection(self) -> dict:
        self._uapi("DomainInfo", "list_domains")
        return {"ok": True}

    def list_websites(self) -> list[dict]:
        data = self._uapi("DomainInfo", "list_domains")
        result = data.get("data") or {}
        sites: list[dict] = []
        main = result.get("main_domain")
        if main:
            sites.append({"domain": main, "state": "active", "type": "main"})
        for d in result.get("addon_domains", []) or []:
            sites.append({"domain": d, "state": "active", "type": "addon"})
        for d in result.get("sub_domains", []) or []:
            sites.append({"domain": d, "state": "active", "type": "subdomain"})
        return sites

    def list_databases(self) -> list[dict]:
        data = self._uapi("Mysql", "list_databases")
        return [{"db_name": d.get("database"), "size": d.get("disk_usage")} for d in (data.get("data") or [])]

    def create_database(self, body: dict) -> dict:
        self._uapi("Mysql", "create_database", {"name": body["db_name"]})
        return {"status": "created", "db_name": body["db_name"]}

    def list_email(self, domain: str | None) -> list[dict]:
        params = {"domain": domain} if domain else {}
        data = self._uapi("Email", "list_pops", params)
        return [{"email": e.get("email"), "domain": e.get("domain")} for e in (data.get("data") or [])]

    def create_email(self, body: dict) -> dict:
        self._uapi("Email", "add_pop", {
            "email": body["user"], "password": body["password"], "domain": body["domain"],
        })
        return {"status": "created", "email": f"{body['user']}@{body['domain']}"}


class PleskAdapter(_Adapter):
    """Plesk REST API v2 with Basic auth (admin:password)."""

    def _req(self, method: str, path: str, json_body: dict | None = None) -> dict | list:
        url = f"{self._base()}/api/v2{path}"
        try:
            resp = requests.request(
                method, url, json=json_body, verify=settings.HOSTING_TLS_VERIFY, timeout=_TIMEOUT,
                auth=HTTPBasicAuth(self.username, self.secret),
                headers={"Accept": "application/json"},
            )
        except requests.RequestException as exc:
            raise HostingError(f"Could not reach Plesk: {exc}")
        if resp.status_code == 401:
            raise HostingError("Plesk authentication failed (check admin credentials).")
        if resp.status_code >= 400:
            raise HostingError(f"Plesk returned HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            return resp.json()
        except ValueError:
            raise HostingError("Plesk returned a non-JSON response (check host/port).")

    def test_connection(self) -> dict:
        self._req("GET", "/server")
        return {"ok": True}

    def list_websites(self) -> list[dict]:
        data = self._req("GET", "/domains")
        items = data if isinstance(data, list) else data.get("data", [])
        return [{"domain": d.get("name"), "state": d.get("hosting_type") or "active", "id": d.get("id")} for d in items]

    def create_website(self, body: dict) -> dict:
        self._req("POST", "/domains", {
            "name": body["domain"],
            "hosting_type": "virtual",
        })
        return {"status": "created", "domain": body["domain"]}


class DirectAdminAdapter(_Adapter):
    """DirectAdmin legacy API (``/CMD_API_*``, default port 2222, HTTP Basic auth).

    Responses are URL-encoded ``key=value`` (the most version-compatible format,
    parsed with ``parse_qs``); list results come back as repeated ``list[]`` keys,
    and a command failure is signalled by ``error=1`` in the body (HTTP 200). Auth
    uses the panel username + password, or a DirectAdmin login key as the password.

    Covers the same surface as the cPanel adapter (connect + list sites, list/create
    databases, list/create email). NOTE: endpoint shape follows DirectAdmin's
    documented legacy API — validate against your DA version before relying on the
    write operations (no live DA panel was available at build time)."""

    def _api(self, cmd: str, params: dict | None = None, method: str = "GET") -> dict:
        url = f"{self._base()}/CMD_API_{cmd}"
        try:
            resp = requests.request(
                method, url,
                params=params if method == "GET" else None,
                data=params if method != "GET" else None,
                verify=settings.HOSTING_TLS_VERIFY, timeout=_TIMEOUT,
                auth=HTTPBasicAuth(self.username, self.secret),
            )
        except requests.RequestException as exc:
            raise HostingError(f"Could not reach DirectAdmin: {exc}")
        if resp.status_code == 401:
            raise HostingError("DirectAdmin authentication failed (check username / password or login key).")
        if resp.status_code >= 400:
            raise HostingError(f"DirectAdmin returned HTTP {resp.status_code}")
        # A valid API reply is URL-encoded; an HTML page means we hit the login/UI
        # (wrong port, or credentials rejected without a 401).
        if resp.text.lstrip().startswith("<"):
            raise HostingError("DirectAdmin returned a non-API (HTML) response — check host, port, and credentials.")
        parsed = parse_qs(resp.text)
        if parsed.get("error", ["0"])[0] not in ("0", ""):
            msg = parsed.get("text", [""])[0] or parsed.get("details", [""])[0] or "DirectAdmin command failed"
            raise HostingError(msg.replace("_", " "))
        return parsed

    @staticmethod
    def _items(parsed: dict) -> list[str]:
        return parsed.get("list[]") or parsed.get("list", [])

    def test_connection(self) -> dict:
        self._api("SHOW_DOMAINS")
        return {"ok": True}

    def list_websites(self) -> list[dict]:
        return [{"domain": d, "state": "active"} for d in self._items(self._api("SHOW_DOMAINS"))]

    def list_databases(self) -> list[dict]:
        return [{"db_name": d} for d in self._items(self._api("DATABASES", {"action": "list"}))]

    def create_database(self, body: dict) -> dict:
        name = body["db_name"]
        pw = body.get("db_password") or ""
        self._api("DATABASES", {
            "action": "create", "name": name,
            "user": body.get("db_user") or name, "passwd": pw, "passwd2": pw,
        }, method="POST")
        return {"status": "created", "db_name": name}

    def list_email(self, domain: str | None) -> list[dict]:
        if not domain:
            raise HostingError("DirectAdmin needs a domain to list its email accounts.")
        users = self._items(self._api("POP", {"action": "list", "domain": domain}))
        return [{"email": f"{u}@{domain}", "domain": domain} for u in users]

    def create_email(self, body: dict) -> dict:
        pw = body["password"]
        self._api("POP", {
            "action": "create", "domain": body["domain"], "user": body["user"],
            "passwd": pw, "passwd2": pw, "quota": 0, "limit": 0,
        }, method="POST")
        return {"status": "created", "email": f"{body['user']}@{body['domain']}"}


_ADAPTERS = {
    "cyberpanel": CyberPanelAdapter,
    "cpanel": CpanelAdapter,
    "plesk": PleskAdapter,
    "directadmin": DirectAdminAdapter,
}


# ── Dispatch ────────────────────────────────────────────────────────────────

def _adapter(server: Server) -> _Adapter:
    panel = (server.panel_type or "").lower()
    cls = _ADAPTERS.get(panel)
    if cls is None:
        raise HostingError(f"Unsupported or missing panel_type: {panel or '(none)'}")
    secret = decrypt(server.encrypted_cred)
    port = server.port or DEFAULT_PORTS.get(panel, 443)
    return cls(server.host, port, server.username, secret)


def _cli_server(server: Server) -> bool:
    """True when hosting ops should run via the ``cyberpanel`` CLI over SSH — i.e.
    a CyberPanel server reached over SSH (H1). CyberPanel's HTTP API can't do
    website/DB/SSL, so an SSH-backed CyberPanel server drives the CLI instead."""
    return (server.panel_type or "").lower() == "cyberpanel" and server.connection_type == "ssh"


async def _run(fn, *args):
    """Run a blocking adapter call off the event loop."""
    return await asyncio.to_thread(fn, *args)


async def test_connection(server: Server) -> dict:
    """Verify panel credentials. Returns {'ok', 'latency_ms', 'error'}."""
    import time
    t0 = time.monotonic()
    try:
        await _run(_adapter(server).test_connection)
        return {"ok": True, "latency_ms": int((time.monotonic() - t0) * 1000), "error": None}
    except HostingError as exc:
        return {"ok": False, "latency_ms": 0, "error": str(exc)}


async def list_websites(server: Server) -> list[dict]:
    if _cli_server(server):
        from app.services import cyberpanel_cli
        return await cyberpanel_cli.list_websites(server)
    return await _run(_adapter(server).list_websites)


async def create_website(server: Server, body: dict) -> dict:
    if _cli_server(server):
        from app.services import cyberpanel_cli
        return await cyberpanel_cli.create_website(server, body)
    return await _run(_adapter(server).create_website, body)


async def delete_website(server: Server, domain: str) -> dict:
    if _cli_server(server):
        from app.services import cyberpanel_cli
        return await cyberpanel_cli.delete_website(server, domain)
    return await _run(_adapter(server).delete_website, domain)


async def issue_ssl(server: Server, domain: str) -> dict:
    if _cli_server(server):
        from app.services import cyberpanel_cli
        return await cyberpanel_cli.issue_ssl(server, domain)
    return await _run(_adapter(server).issue_ssl, domain)


async def list_databases(server: Server, domain: str | None = None) -> list[dict]:
    if _cli_server(server):
        # CyberPanel's listDatabasesJson is scoped per-website — it errors without
        # --databaseWebsite, so a missing domain must not silently read as "no databases".
        from app.services import cyberpanel_cli
        return await cyberpanel_cli.list_databases(server, domain)
    return await _run(_adapter(server).list_databases)


async def create_database(server: Server, body: dict) -> dict:
    if _cli_server(server):
        from app.services import cyberpanel_cli
        return await cyberpanel_cli.create_database(server, body)
    return await _run(_adapter(server).create_database, body)


async def list_email(server: Server, domain: str | None = None) -> list[dict]:
    return await _run(_adapter(server).list_email, domain)


async def create_email(server: Server, body: dict) -> dict:
    return await _run(_adapter(server).create_email, body)
