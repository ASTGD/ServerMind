"""Hosting service — control panel API integration (Hosting Mode).

When ``connection_type == 'hosting'`` ServerMind talks to a control panel's REST
API instead of opening a shell. Each panel has its own auth scheme and endpoints,
so this module provides a small adapter per panel behind a uniform dispatch.

Supported panels (``server.panel_type``):
- ``cyberpanel`` — cloud-style JSON API (default port 8090, HTTPS)
- ``cpanel``     — UAPI with API-token auth (default port 2083, HTTPS)
- ``plesk``      — REST API v2 with Basic auth (default port 8443, HTTPS)

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

import requests
from requests.auth import HTTPBasicAuth

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
    """CyberPanel cloud-style JSON API. Each request posts adminUser/adminPass."""

    def _post(self, action: str, params: dict | None = None) -> dict:
        url = f"{self._base()}/api/{action}"
        payload = {"adminUser": self.username, "adminPass": self.secret, **(params or {})}
        try:
            resp = requests.post(url, json=payload, verify=False, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            raise HostingError(f"Could not reach CyberPanel: {exc}")
        if resp.status_code >= 400:
            raise HostingError(f"CyberPanel returned HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise HostingError("CyberPanel returned a non-JSON response (check host/port).")
        return data

    def test_connection(self) -> dict:
        data = self._post("verifyLogin")
        ok = bool(data.get("verifyLogin") in (1, "1", True) or data.get("status") in (1, "1", True))
        if not ok:
            raise HostingError(data.get("error_message") or "CyberPanel login failed.")
        return {"ok": True}

    def list_websites(self) -> list[dict]:
        data = self._post("fetchWebsites", {"page": 1})
        raw = data.get("data") or data.get("websites") or []
        if isinstance(raw, str):
            import json
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = []
        sites = []
        for w in raw:
            sites.append({
                "domain": w.get("domain") or w.get("domainName") or w.get("name", ""),
                "state": w.get("state") or w.get("status"),
                "php": w.get("php") or w.get("phpSelection"),
                "admin": w.get("adminEmail") or w.get("admin"),
            })
        return sites

    def create_website(self, body: dict) -> dict:
        self._post("createWebsite", {
            "domainName": body["domain"],
            "adminEmail": body.get("email", f"admin@{body['domain']}"),
            "packageName": body.get("package", "Default"),
            "websiteOwner": body.get("owner", self.username),
            "phpSelection": body.get("php", "PHP 8.1"),
        })
        return {"status": "created", "domain": body["domain"]}

    def delete_website(self, domain: str) -> dict:
        self._post("submitWebsiteDeletion", {"websiteName": domain})
        return {"status": "deleted", "domain": domain}

    def issue_ssl(self, domain: str) -> dict:
        self._post("issueSSL", {"virtualHost": domain})
        return {"status": "issued", "domain": domain}

    def create_database(self, body: dict) -> dict:
        self._post("createDatabase", {
            "databaseWebsite": body["domain"],
            "dbName": body["db_name"],
            "dbUsername": body["db_user"],
            "dbPassword": body["db_password"],
        })
        return {"status": "created", "db_name": body["db_name"]}


class CpanelAdapter(_Adapter):
    """cPanel UAPI with API-token auth (Authorization: cpanel user:token)."""

    def _uapi(self, module: str, func: str, params: dict | None = None) -> dict:
        url = f"{self._base()}/execute/{module}/{func}"
        headers = {"Authorization": f"cpanel {self.username}:{self.secret}"}
        try:
            resp = requests.get(url, headers=headers, params=params or {}, verify=False, timeout=_TIMEOUT)
        except requests.RequestException as exc:
            raise HostingError(f"Could not reach cPanel: {exc}")
        if resp.status_code == 401:
            raise HostingError("cPanel authentication failed (check username / API token).")
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
                method, url, json=json_body, verify=False, timeout=_TIMEOUT,
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


_ADAPTERS = {
    "cyberpanel": CyberPanelAdapter,
    "cpanel": CpanelAdapter,
    "plesk": PleskAdapter,
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
    return await _run(_adapter(server).list_websites)


async def create_website(server: Server, body: dict) -> dict:
    return await _run(_adapter(server).create_website, body)


async def delete_website(server: Server, domain: str) -> dict:
    return await _run(_adapter(server).delete_website, domain)


async def issue_ssl(server: Server, domain: str) -> dict:
    return await _run(_adapter(server).issue_ssl, domain)


async def list_databases(server: Server) -> list[dict]:
    return await _run(_adapter(server).list_databases)


async def create_database(server: Server, body: dict) -> dict:
    return await _run(_adapter(server).create_database, body)


async def list_email(server: Server, domain: str | None = None) -> list[dict]:
    return await _run(_adapter(server).list_email, domain)


async def create_email(server: Server, body: dict) -> dict:
    return await _run(_adapter(server).create_email, body)
