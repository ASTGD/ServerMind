"""CyberPanel operations via the ``cyberpanel`` CLI over SSH (Hosting H1).

CyberPanel's adminUser/adminPass HTTP API does NOT expose website/database/SSL
management (see docs/HOSTING-CYBERPANEL.md — validated live). The reliable surface
is the ``cyberpanel`` CLI at ``/usr/bin/cyberpanel``, which we drive over the SSH
channel the server already has. Function names + flags below were read from the
live CLI (``/usr/local/CyberCP/cli/cyberPanel.py``) — not guessed:

    cyberpanel createWebsite --package Default --owner admin \
        --domainName X --email Y --php 8.1
    cyberpanel listWebsitesJson            # -> JSON array
    cyberpanel deleteWebsite --domainName X
    cyberpanel issueSSL --domainName X
    cyberpanel createDatabase --databaseWebsite X \
        --dbName N --dbUsername U --dbPassword P
    cyberpanel listDatabasesJson --databaseWebsite X

Each op is one SSH round trip. Arguments are shell-quoted. The CLI prints a JSON
status for writes; we surface a clear HostingError on failure.
"""
from __future__ import annotations

import json
import logging
import shlex

from app.models.server import Server
from app.services import connection_manager
from app.services.hosting_service import HostingError

logger = logging.getLogger(__name__)

CLI = "cyberpanel"


def _flags(pairs: dict[str, object]) -> str:
    """Render ``--key value`` flags, shell-quoted, skipping None/empty values."""
    parts: list[str] = []
    for key, value in pairs.items():
        if value is None or value == "":
            continue
        parts.append(f"--{key} {shlex.quote(str(value))}")
    return " ".join(parts)


async def _run(server: Server, function: str, pairs: dict[str, object] | None = None) -> str:
    """Run ``cyberpanel <function> [flags]`` over SSH; return stdout or raise."""
    cmd = f"{CLI} {shlex.quote(function)}"
    if pairs:
        cmd += " " + _flags(pairs)
    try:
        stdout, stderr, code = await connection_manager.execute(server, cmd)
    except Exception as exc:  # noqa: BLE001 — SSH/connection failure
        raise HostingError(f"Could not run the CyberPanel CLI over SSH: {exc}")
    if code != 0:
        detail = (stderr or stdout or "").strip().splitlines()
        raise HostingError(
            f"cyberpanel {function} failed: " + (detail[-1] if detail else f"exit {code}")
        )
    return stdout


def _parse_status(raw: str, ok_key: str) -> dict:
    """CyberPanel writes print a JSON status line, e.g. ``{"success": 1, ...}`` on
    success or ``{"success": 0, "errorMessage": "..."}`` on failure. Return the data
    on success; raise HostingError on failure.

    NOTE: CyberPanel reports a FAILURE as ``{"success": 0}`` — often with
    ``errorMessage: "None"`` (a silent failure). An explicit falsy status must raise,
    never be treated as success (that would report a non-existent website as created)."""
    for line in reversed(raw.strip().splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        # The status field is present under ok_key or the generic "success".
        status_val = data.get(ok_key, data.get("success"))
        if status_val is not None:
            if status_val in (1, "1", True):
                return data
            # Explicit failure — raise, even when the panel gives no message.
            msg = data.get("error_message") or data.get("errorMessage") or ""
            if str(msg).lower() in ("none", ""):
                msg = "the panel reported the operation did not succeed"
            raise HostingError(f"CyberPanel: {msg}")
        return data  # JSON with no status field — informational, treat as success
    # No JSON status line — CLI printed prose. Treat non-error prose as success.
    if "error" in raw.lower() or "fail" in raw.lower():
        raise HostingError(f"CyberPanel: {raw.strip().splitlines()[-1] if raw.strip() else 'failed'}")
    return {}


def _parse_json_list(raw: str) -> list:
    """listWebsitesJson / listDatabasesJson print a JSON array — usually bare
    (``[...]``), but listDatabasesJson has been observed printing it DOUBLE-encoded
    as a JSON string (``"[...]"``, quotes escaped) when a domain has databases.
    Try both forms; return the first array found, else []."""
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or line[0] not in "[\"":
            continue
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                continue
        if isinstance(data, list):
            return data
    return []


# ── Websites ──────────────────────────────────────────────────────────────────

async def list_websites(server: Server) -> list[dict]:
    raw = await _run(server, "listWebsitesJson")
    sites = []
    for w in _parse_json_list(raw):
        if not isinstance(w, dict):
            continue
        sites.append({
            "domain": w.get("domain") or w.get("domainName") or w.get("name", ""),
            "state": w.get("state") or w.get("status") or "active",
            "php": w.get("php") or w.get("phpSelection"),
            "admin": w.get("adminEmail") or w.get("admin"),
        })
    return sites


async def create_website(server: Server, body: dict) -> dict:
    domain = body["domain"]
    raw = await _run(server, "createWebsite", {
        "package": body.get("package", "Default"),
        "owner": body.get("owner", "admin"),
        "domainName": domain,
        "email": body.get("email", f"admin@{domain}"),
        "php": body.get("php", "8.1"),
    })
    _parse_status(raw, "createWebSiteStatus")
    # CyberPanel's createWebsite can print {"success": 1} while actually FAILING
    # (it logs "Websites matching query does not exist" and skips creation — seen live
    # when a create runs while another is finalizing). Trust the site list, not stdout:
    # confirm the domain is really there before reporting success.
    sites = await list_websites(server)
    if not any(s["domain"] == domain for s in sites):
        raise HostingError(
            f"CyberPanel reported success but '{domain}' was not actually created. "
            "This can happen when two sites are created at once — try again in a moment."
        )
    return {"status": "created", "domain": domain}


async def delete_website(server: Server, domain: str) -> dict:
    raw = await _run(server, "deleteWebsite", {"domainName": domain})
    _parse_status(raw, "websiteDeleteStatus")
    return {"status": "deleted", "domain": domain}


async def issue_ssl(server: Server, domain: str) -> dict:
    raw = await _run(server, "issueSSL", {"domainName": domain})
    _parse_status(raw, "SSL")
    return {"status": "issued", "domain": domain}


# ── Databases ─────────────────────────────────────────────────────────────────

async def list_databases(server: Server, domain: str | None = None) -> list[dict]:
    pairs = {"databaseWebsite": domain} if domain else None
    raw = await _run(server, "listDatabasesJson", pairs)
    dbs = []
    for d in _parse_json_list(raw):
        if not isinstance(d, dict):
            continue
        dbs.append({
            "db_name": d.get("dbName") or d.get("database") or d.get("name", ""),
            "db_user": d.get("dbUser") or d.get("user"),
        })
    return dbs


async def create_database(server: Server, body: dict) -> dict:
    raw = await _run(server, "createDatabase", {
        "databaseWebsite": body["domain"],
        "dbName": body["db_name"],
        "dbUsername": body["db_user"],
        "dbPassword": body["db_password"],
    })
    _parse_status(raw, "result")
    return {"status": "created", "db_name": body["db_name"]}
