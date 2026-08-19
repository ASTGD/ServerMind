"""ServerAlly MCP server — Phase 0 spike (docs/MCP-SERVER-PLAN.md §9).

Lets a customer connect their *own* AI client and manage their ServerAlly assets
by conversation. The customer's AI calls our tools; their subscription pays for
the thinking; our AI cost is zero. This server is a thin adapter — no business
logic lives here.

Phase 0 is **authless + local-only**: it resolves a single dev user (env
``MCP_DEV_USER_EMAIL``, else the first user) so the real Rule-7 access path
(``team_service.accessible_servers``) is exercised end to end from a real client.
Phase 1 replaces ``_resolve_caller`` with an OAuth-bearer → User resolver; every
tool body below stays unchanged.

Design rules that hold from day one:
- **No business logic** — each tool is a thin adapter over an existing service.
- **Never returns a credential** — a strict field whitelist (``_server_public``);
  ``encrypted_cred`` and ``fingerprint`` are excluded by construction.
- **Deterministic** — no model call, 0 AI actions.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.alert import ServerMetric
from app.models.backup import Backup
from app.models.mission import Mission
from app.models.oauth import OAuthClient
from app.models.playbook import Playbook, PlaybookRun
from app.models.security_scan import SecurityScan
from app.models.server import Server
from app.models.threat_scan import ThreatScan
from app.models.user import User
from app.services import (
    audit_service,
    backup_service,
    connection_manager,
    file_service,
    fleet_service,
    hosting_service,
    mcp_activity_service,
    mission_service,
    safety_service,
    security_service,
    team_service,
    threat_service,
)
from app.services.hosting_service import HostingError
from app.services.playbook_service import os_matches, substitute_variables, supported_os_for
from app.services.secret_redact import redact_secrets
from app.services.secret_vars import encrypt_variables
from app.workers.playbook_tasks import run_playbook_task

logger = logging.getLogger(__name__)

# Stateless JSON over Streamable HTTP — simplest to scale/proxy and the right
# shape for the Phase-1 OAuth bearer flow. Served at exactly ``/mcp`` (inner path
# "/" here, mounted at "/mcp" in main.py).
mcp_server = FastMCP(
    "serverally_mcp",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    # DNS-rebinding protection defaults to ON (localhost-only allowed_hosts) whenever
    # transport_security is unset — which 421-rejects the proxied Host in production
    # (Caddy → nginx → backend forwards Host: serverally.firevps.net). That protection
    # guards browser-driven localhost servers; ours is a PUBLIC, bearer-token-gated
    # endpoint behind a trusted reverse proxy, so it's redundant here and only blocks
    # legitimate traffic. Disable it; the OAuth bearer requirement is the real gate.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


class ResponseFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


# ── Helpers ──────────────────────────────────────────────────────────────────

# The ONLY fields a tool may expose. A strict allowlist: ``encrypted_cred`` and
# ``fingerprint`` are never present here, so no tool can leak them (enforced by
# test in Phase 2, mirroring ``test_user_detail_never_exposes_a_credential``).
def _server_public(s: Server) -> dict:
    """Serialise a Server to a credential-free public dict."""
    os_str = " ".join(x for x in (s.os_type, s.os_version) if x) or "unknown"
    return {
        "id": str(s.id),
        "name": s.name,
        "host": s.host,
        "port": s.port,
        "username": s.username,
        "connection_type": s.connection_type,  # ssh | winrm | hosting | rdp
        "panel_type": s.panel_type,
        "category": s.category,
        "os": os_str,
        "arch": s.arch,
        "shell": s.shell,
        "status": s.status,
        "tags": list(s.tags or []),
        "last_seen": s.last_seen.isoformat() if s.last_seen else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def _resolve_caller(db) -> User | None:
    """Resolve the calling user.

    Phase 1: the authenticated OAuth bearer's ``subject`` (a ServerAlly user id) taken
    from the auth context the bearer middleware published. Every tool then scopes to this
    user's ``accessible_servers`` (Rule 7 across the boundary).

    When ``MCP_REQUIRE_AUTH`` is off (LOCAL DEV ONLY), there is no bearer, so fall back to
    the Phase-0 dev resolver: ``MCP_DEV_USER_EMAIL`` → the account owning the most servers
    → the first user.
    """
    from mcp.server.auth.middleware.auth_context import get_access_token

    token = get_access_token()
    if token is not None and token.subject:
        try:
            uid = uuid.UUID(str(token.subject))
        except ValueError:
            return None
        return (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()

    # No authenticated bearer. In enforced mode the /mcp guard already blocked the request
    # before it reached a tool, so this path is dev-only.
    if settings.MCP_REQUIRE_AUTH:
        return None

    email = os.environ.get("MCP_DEV_USER_EMAIL")
    if email:
        u = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if u is not None:
            return u
        logger.warning("MCP_DEV_USER_EMAIL=%s not found; falling back to top owner", email)

    # Prefer an account that actually owns servers, so the demo shows a real fleet.
    top = (await db.execute(
        select(User)
        .join(Server, Server.user_id == User.id)
        .group_by(User.id)
        .order_by(func.count(Server.id).desc())
    )).scalars().first()
    if top is not None:
        return top

    return (await db.execute(select(User).order_by(User.created_at))).scalars().first()


def _servers_markdown(servers: list[dict]) -> str:
    """Human-readable server list for display in the customer's AI client."""
    if not servers:
        return "No servers found for this account."
    lines = [f"# Your servers ({len(servers)})", ""]
    for s in servers:
        panel = f" / {s['panel_type']}" if s["panel_type"] else ""
        lines.append(f"## {s['name']} — {s['status']}")
        lines.append(f"- **Host**: {s['host']}:{s['port']}  ·  **User**: {s['username']}")
        lines.append(f"- **OS**: {s['os']} ({s['arch'] or 'arch unknown'})")
        lines.append(f"- **Connection**: {s['connection_type']}{panel}  ·  **Category**: {s['category'] or '—'}")
        if s["tags"]:
            lines.append(f"- **Tags**: {', '.join(s['tags'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp_server.tool(
    name="serverally_list_servers",
    annotations={
        "title": "List ServerAlly servers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def serverally_list_servers(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """List every server in the caller's ServerAlly account.

    Read-only. Returns all servers the account can access (owned plus servers a
    teammate has granted), scoped by ServerAlly's access rules (Rule 7). Never
    returns credentials — no passwords, SSH keys, or host fingerprints.

    Args:
        response_format (ResponseFormat): 'markdown' (default, human-readable) or
            'json' (machine-readable).

    Returns:
        str: In 'markdown' mode, a readable list of servers with host, OS, and
        status. In 'json' mode, a JSON object:

        {
          "count": int,
          "servers": [
            {
              "id": str, "name": str, "host": str, "port": int,
              "username": str, "connection_type": str, "panel_type": str|null,
              "category": str|null, "os": str, "arch": str|null, "shell": str,
              "status": str, "tags": [str], "last_seen": str|null,
              "created_at": str|null
            }
          ]
        }

        Never includes ``encrypted_cred`` or ``fingerprint``.

    Examples:
        - "What servers do I have?" → call with response_format='markdown'
        - "List my servers as JSON" → call with response_format='json'
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return "Error: no ServerAlly user found. Create an account first."
        servers = await team_service.accessible_servers(db, user)
        public = [_server_public(s) for s in servers]

    if response_format == ResponseFormat.JSON:
        return json.dumps({"count": len(public), "servers": public}, indent=2)
    return _servers_markdown(public)


# ── shared: server resolution + audit ─────────────────────────────────────────

_NO_USER = "Error: could not identify your ServerAlly account for this request."
_RO = {  # read-only tool annotations
    "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True,
}


async def _resolve_server(db, user: User, ref: str):
    """Resolve a server by NAME or id within the caller's accessible servers (Rule 7).
    Returns a ``team_service.Access`` (has .server + permissions) or None if not found /
    ambiguous."""
    ref = (ref or "").strip()
    try:
        uuid.UUID(ref)
        return await team_service.get_access(db, user, ref)
    except ValueError:
        pass
    servers = await team_service.accessible_servers(db, user)
    matches = [s for s in servers if s.name.lower() == ref.lower()] or [
        s for s in servers if s.name.lower().startswith(ref.lower())
    ]
    if len(matches) == 1:
        return await team_service.get_access(db, user, str(matches[0].id))
    return None


async def _unknown_server(db, user: User, ref: str) -> str:
    names = [s.name for s in await team_service.accessible_servers(db, user)]
    return f"Error: no unique server matches '{ref}'. Your servers: {', '.join(names) or '(none)'}."


async def _audit(db, user: User, tool: str, server_id=None) -> None:
    """Best-effort audit of an MCP tool call (docs/MCP-SERVER-PLAN.md §8). Never breaks a tool."""
    try:
        await audit_service.audit(
            db, user, f"mcp.{tool}",
            target_type="server" if server_id else None,
            target_id=str(server_id) if server_id else None,
        )
    except Exception:  # noqa: BLE001
        logger.debug("mcp audit failed for %s", tool, exc_info=True)


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


# ── credential-free serializers ───────────────────────────────────────────────

def _metric_public(m: ServerMetric | None) -> dict | None:
    if m is None:
        return None
    return {
        "cpu_percent": float(m.cpu_percent) if m.cpu_percent is not None else None,
        "ram_percent": float(m.ram_percent) if m.ram_percent is not None else None,
        "ram_used_mb": m.ram_used_mb, "ram_total_mb": m.ram_total_mb,
        "disk_percent": float(m.disk_percent) if m.disk_percent is not None else None,
        "disk_used_gb": float(m.disk_used_gb) if m.disk_used_gb is not None else None,
        "disk_total_gb": float(m.disk_total_gb) if m.disk_total_gb is not None else None,
        "load_1": float(m.load_1) if m.load_1 is not None else None,
        "load_5": float(m.load_5) if m.load_5 is not None else None,
        "load_15": float(m.load_15) if m.load_15 is not None else None,
        "uptime_seconds": m.uptime_seconds, "recorded_at": _iso(m.recorded_at),
    }


# Scan findings are already credential-free by the security/threat services' design; we
# still whitelist safe scalar keys so a future field change can never leak something.
_FINDING_KEYS = (
    "id", "severity", "title", "name", "status", "detail", "description",
    "evidence", "fix", "recommendation", "remediation",
)


def _scan_finding_public(f: dict) -> dict:
    return {k: f[k] for k in _FINDING_KEYS if k in f and isinstance(f[k], (str, int, float, bool))}


def _finding_public(f) -> dict:
    """A fleet Finding (dataclass) → the safe subset (drops internal penalty/action)."""
    return {"severity": f.severity, "title": f.title, "detail": f.detail}


def _mission_summary(m: Mission) -> dict:
    return {
        "id": str(m.id), "goal": m.goal, "status": m.status, "verified": m.verified,
        "server": m.server_name, "skill": m.skill_slug, "steps_used": m.steps_used,
        "summary": m.summary, "created_at": _iso(m.created_at),
    }


def _step_public(s: dict) -> dict:
    """A mission transcript step → scalars only, long strings (command output) truncated."""
    out: dict = {}
    for k, v in s.items():
        if isinstance(v, str):
            out[k] = v if len(v) <= 2000 else v[:2000] + f"… (+{len(v) - 2000} more chars)"
        elif isinstance(v, (int, float, bool)) or v is None:
            out[k] = v
    return out


def _load_json(text, default):
    try:
        return json.loads(text) if text else default
    except (ValueError, TypeError):
        return default


def _looks_binary(text: str) -> bool:
    """Robust binary check for file content.

    ``file_service`` decodes with a latin-1 fallback, which accepts ANY byte sequence — so
    its ``is_binary`` almost never fires (a real /bin/bash slipped through live). A NUL byte
    is a near-certain binary signal (text files don't contain it); a high control-char ratio
    catches the rest.
    """
    if "\x00" in text:
        return True
    sample = text[:4096]
    if not sample:
        return False
    ctrl = sum(1 for ch in sample if ord(ch) < 9 or 13 < ord(ch) < 32 or ord(ch) == 127 or 128 <= ord(ch) < 160)
    return ctrl / len(sample) > 0.15


# ── read tools (Phase 2) ──────────────────────────────────────────────────────

@mcp_server.tool(name="serverally_get_fleet_health", annotations={"title": "Fleet health", **_RO})
async def serverally_get_fleet_health(response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """What needs attention across the caller's WHOLE fleet.

    A health score (0-100) + A–F grade + ranked, plain-English findings per server.
    Deterministic — computed from data ServerAlly already stores (no SSH, no AI). Use this
    to answer "which of my servers need attention?". Read-only, credential-free.

    Returns (json): {"summary": {total, needs_attention, critical_findings, worst_grade},
    "servers": [{name, score, grade, status, headline, needs_attention,
    findings: [{severity, title, detail}]}]}.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        servers = await team_service.accessible_servers(db, user)
        fleet = await fleet_service.analyze_fleet(db, servers)
        summary = fleet_service.summarize(fleet)
        await _audit(db, user, "get_fleet_health")
        data = {
            "summary": summary,
            "servers": [
                {
                    "name": h.name, "score": h.score, "grade": h.grade, "status": h.status,
                    "headline": h.headline,
                    "needs_attention": h.score < 75 or any(f.severity in ("critical", "high") for f in h.findings),
                    "findings": [_finding_public(f) for f in h.findings],
                }
                for h in fleet
            ],
        }
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    s = data["summary"]
    lines = [f"# Fleet health — {s['needs_attention']} of {s['total']} need attention (worst grade {s['worst_grade']})", ""]
    for srv in sorted(data["servers"], key=lambda x: x["score"]):
        flag = "⚠️ " if srv["needs_attention"] else "✓ "
        lines.append(f"## {flag}{srv['name']} — {srv['grade']} ({srv['score']}/100) — {srv['headline']}")
        for f in srv["findings"]:
            lines.append(f"- **[{f['severity']}]** {f['title']} — {f['detail']}")
        lines.append("")
    return "\n".join(lines).rstrip()


@mcp_server.tool(name="serverally_get_server", annotations={"title": "Server detail", **_RO})
async def serverally_get_server(server: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """Detailed status of one server: identity + latest metrics + last security grade and
    threat verdict. Read-only, credential-free. ``server`` is a name or id.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc = await _resolve_server(db, user, server)
        if acc is None:
            return await _unknown_server(db, user, server)
        srv = acc.server
        metric = (await db.execute(
            select(ServerMetric).where(ServerMetric.server_id == srv.id)
            .order_by(ServerMetric.recorded_at.desc()).limit(1)
        )).scalar_one_or_none()
        sec = (await db.execute(
            select(SecurityScan).where(SecurityScan.server_id == srv.id, SecurityScan.status == "completed")
            .order_by(SecurityScan.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        threat = (await db.execute(
            select(ThreatScan).where(ThreatScan.server_id == srv.id, ThreatScan.status == "completed")
            .order_by(ThreatScan.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        await _audit(db, user, "get_server", srv.id)
        data = {
            **_server_public(srv),
            "your_role": acc.role,
            "latest_metrics": _metric_public(metric),
            "security": {"grade": sec.grade, "score": sec.score, "scanned_at": _iso(sec.created_at)} if sec else None,
            "threat": {"verdict": threat.verdict, "scanned_at": _iso(threat.created_at)} if threat else None,
        }
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    m = data["latest_metrics"]
    lines = [
        f"# {data['name']} — {data['status']}",
        f"- **Host**: {data['host']}:{data['port']} ({data['username']})  ·  **OS**: {data['os']} {data['arch'] or ''}",
        f"- **Connection**: {data['connection_type']}{(' / ' + data['panel_type']) if data['panel_type'] else ''}  ·  **Your role**: {data['your_role']}",
    ]
    if m:
        lines.append(f"- **Now**: CPU {m['cpu_percent']}%  ·  RAM {m['ram_percent']}%  ·  Disk {m['disk_percent']}%")
    if data["security"]:
        lines.append(f"- **Security**: grade {data['security']['grade']} ({data['security']['score']}/100)")
    if data["threat"]:
        lines.append(f"- **Threat scan**: {data['threat']['verdict']}")
    return "\n".join(lines)


@mcp_server.tool(name="serverally_get_metrics", annotations={"title": "Server metrics", **_RO})
async def serverally_get_metrics(
    server: str, hours: int = 0, response_format: ResponseFormat = ResponseFormat.MARKDOWN
) -> str:
    """Latest CPU/RAM/disk for a server, plus optional recent history.

    ``server`` is a name or id. ``hours`` > 0 includes history over that window (max 168 =
    7 days, newest first, capped at 200 samples). Read-only, credential-free.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc = await _resolve_server(db, user, server)
        if acc is None:
            return await _unknown_server(db, user, server)
        srv = acc.server
        latest = (await db.execute(
            select(ServerMetric).where(ServerMetric.server_id == srv.id)
            .order_by(ServerMetric.recorded_at.desc()).limit(1)
        )).scalar_one_or_none()
        history = []
        if hours and hours > 0:
            since = datetime.now(timezone.utc) - timedelta(hours=min(hours, 168))
            rows = (await db.execute(
                select(ServerMetric).where(ServerMetric.server_id == srv.id, ServerMetric.recorded_at >= since)
                .order_by(ServerMetric.recorded_at.desc()).limit(200)
            )).scalars().all()
            history = [_metric_public(r) for r in rows]
        await _audit(db, user, "get_metrics", srv.id)
        data = {"server": srv.name, "status": srv.status, "latest": _metric_public(latest), "history": history}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    lt = data["latest"]
    if lt is None:
        return f"No metrics recorded yet for {data['server']} (status: {data['status']})."
    out = [
        f"# {data['server']} metrics ({data['status']})",
        f"- **CPU**: {lt['cpu_percent']}%  ·  **RAM**: {lt['ram_percent']}% ({lt['ram_used_mb']}/{lt['ram_total_mb']} MB)  ·  **Disk**: {lt['disk_percent']}% ({lt['disk_used_gb']}/{lt['disk_total_gb']} GB)",
        f"- **Load**: {lt['load_1']} / {lt['load_5']} / {lt['load_15']}  ·  as of {lt['recorded_at']}",
    ]
    if data["history"]:
        out.append(f"\n{len(data['history'])} history samples over the requested window (use response_format='json' for the series).")
    return "\n".join(out)


def _scan_payload(scan, key: str) -> dict:
    findings = [_scan_finding_public(f) for f in _load_json(scan.findings, []) if isinstance(f, dict)]
    return {
        key: getattr(scan, key), "counts": {
            "critical": scan.critical_count, "high": scan.high_count, "medium": scan.medium_count,
            "low": scan.low_count, "info": scan.info_count, "pass": scan.pass_count,
        },
        "scanned_at": _iso(scan.created_at), "findings": findings,
    }


@mcp_server.tool(name="serverally_get_security_scan", annotations={"title": "Security scan", **_RO})
async def serverally_get_security_scan(server: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """The latest security audit for a server: A–F grade, score, severity counts, and the
    findings (each with a fix). ``server`` is a name or id. Read-only, credential-free.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc = await _resolve_server(db, user, server)
        if acc is None:
            return await _unknown_server(db, user, server)
        srv = acc.server
        scan = (await db.execute(
            select(SecurityScan).where(SecurityScan.server_id == srv.id, SecurityScan.status == "completed")
            .order_by(SecurityScan.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        await _audit(db, user, "get_security_scan", srv.id)
        if scan is None:
            return f"No security scan yet for {srv.name}. Ask ServerAlly to run one."
        data = {"server": srv.name, "grade": scan.grade, "score": scan.score, **_scan_payload(scan, "grade")}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    lines = [f"# {data['server']} security — grade {data['grade']} ({data['score']}/100)",
             f"Findings: {data['counts']}", ""]
    for f in data["findings"]:
        if f.get("status") == "pass":
            continue
        lines.append(f"- **[{f.get('severity', '?')}]** {f.get('title') or f.get('name', '')} — {f.get('detail') or f.get('description', '')}")
        if f.get("fix") or f.get("recommendation"):
            lines.append(f"  fix: `{f.get('fix') or f.get('recommendation')}`")
    return "\n".join(lines).rstrip()


@mcp_server.tool(name="serverally_get_threat_scan", annotations={"title": "Threat scan", **_RO})
async def serverally_get_threat_scan(server: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """The latest proactive threat/IOC scan for a server: a verdict
    (clean|suspicious|at_risk|compromised) + the evidence. ``server`` is a name or id.
    Read-only, credential-free.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc = await _resolve_server(db, user, server)
        if acc is None:
            return await _unknown_server(db, user, server)
        srv = acc.server
        scan = (await db.execute(
            select(ThreatScan).where(ThreatScan.server_id == srv.id, ThreatScan.status == "completed")
            .order_by(ThreatScan.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        await _audit(db, user, "get_threat_scan", srv.id)
        if scan is None:
            return f"No threat scan yet for {srv.name}. Ask ServerAlly to run one."
        data = {"server": srv.name, **_scan_payload(scan, "verdict")}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    lines = [f"# {data['server']} threat scan — {data['verdict']}", f"Findings: {data['counts']}", ""]
    for f in data["findings"]:
        lines.append(f"- **[{f.get('severity', '?')}]** {f.get('title') or f.get('name', '')} — {f.get('detail') or f.get('description') or f.get('evidence', '')}")
    return "\n".join(lines).rstrip()


@mcp_server.tool(name="serverally_list_playbooks", annotations={"title": "List playbooks", **_RO})
async def serverally_list_playbooks(
    os_family: str = "", category: str = "", response_format: ResponseFormat = ResponseFormat.MARKDOWN
) -> str:
    """The official ServerAlly playbook library (one-click scripts) the caller can run.

    Optional filters: ``os_family`` ('linux'|'windows') and ``category``. Read-only.
    Returns each playbook's slug, title, category, os_family, and description.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        rows = (await db.execute(
            select(Playbook).where(Playbook.is_official == True).order_by(Playbook.category, Playbook.title)  # noqa: E712
        )).scalars().all()
        await _audit(db, user, "list_playbooks")
        of = os_family.strip().lower()
        cat = category.strip().lower()
        items = [
            {"slug": p.slug, "title": p.title, "category": p.category, "os_family": p.os_family, "description": p.description}
            for p in rows
            if (not of or (p.os_family or "").lower() in (of, "both")) and (not cat or (p.category or "").lower() == cat)
        ]
        data = {"count": len(items), "playbooks": items}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    lines = [f"# Playbooks ({data['count']})", ""]
    by_cat: dict[str, list] = {}
    for p in data["playbooks"]:
        by_cat.setdefault(p["category"] or "other", []).append(p)
    for cat_name, ps in by_cat.items():
        lines.append(f"## {cat_name}")
        for p in ps:
            lines.append(f"- **{p['slug']}** ({p['os_family']}) — {p['title']}")
        lines.append("")
    return "\n".join(lines).rstrip()


@mcp_server.tool(name="serverally_list_missions", annotations={"title": "List missions", **_RO})
async def serverally_list_missions(
    server: str = "", limit: int = 20, response_format: ResponseFormat = ResponseFormat.MARKDOWN
) -> str:
    """The caller's recent Ally missions (agentic operations), newest first.

    Optional ``server`` (name or id) filters to one server. ``limit`` max 50. Read-only.
    Each: id, goal, status, verified, server, skill, steps_used, summary, created_at.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        sid = None
        if server.strip():
            acc = await _resolve_server(db, user, server)
            if acc is None:
                return await _unknown_server(db, user, server)
            sid = str(acc.server.id)
        missions = await mission_service.list_for_user(db, user, limit=max(1, min(limit, 50)), server_id=sid)
        await _audit(db, user, "list_missions")
        data = {"count": len(missions), "missions": [_mission_summary(m) for m in missions]}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    if not data["missions"]:
        return "No missions yet."
    lines = [f"# Missions ({data['count']})", ""]
    for m in data["missions"]:
        verified = "✓ verified" if m["verified"] else ("✗ unverified" if m["verified"] is False else "")
        lines.append(f"- **{m['status']}** {verified} — {m['goal']}  ({m['server'] or 'fleet'}, {m['steps_used']} steps)  ·  `{m['id']}`")
    return "\n".join(lines)


@mcp_server.tool(name="serverally_get_mission", annotations={"title": "Mission detail", **_RO})
async def serverally_get_mission(mission_id: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """Full detail of one mission: summary + outcome + the step-by-step transcript (command
    output truncated; last 40 steps). ``mission_id`` from list_missions. Read-only.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        m = await mission_service.get_for_user(db, user, mission_id)
        await _audit(db, user, "get_mission", m.server_id if m else None)
        if m is None:
            return "Error: mission not found (or it belongs to another account)."
        steps = _load_json(m.steps, [])
        transcript = [_step_public(s) for s in steps if isinstance(s, dict)][-40:]
        data = {**_mission_summary(m), "result": _load_json(m.result, None), "transcript": transcript}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    lines = [f"# Mission — {data['status']} — {data['goal']}",
             f"Server: {data['server'] or 'fleet'}  ·  Steps: {data['steps_used']}  ·  Verified: {data['verified']}"]
    if data.get("summary"):
        lines.append(f"\n**Summary:** {data['summary']}")
    res = data.get("result")
    if isinstance(res, dict):
        if res.get("headline"):
            lines.append(f"\n**Outcome:** {res['headline']}")
        for label, key in (("Found", "found"), ("Ally did", "did"), ("Left for you", "left")):
            items = res.get(key) or []
            if items:
                lines.append(f"\n{label}:")
                lines += [f"- {it}" for it in items]
    lines.append(f"\n_Transcript: {len(data['transcript'])} steps (use response_format='json' for full detail)._")
    return "\n".join(lines)


# ── live-SSH read tools (Phase 2) ─────────────────────────────────────────────

# Cap file content well under the client 150k result limit.
_FILE_CONTENT_CAP = 100_000


@mcp_server.tool(name="serverally_list_sites", annotations={"title": "List hosted sites", **_RO})
async def serverally_list_sites(server: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """Websites/domains hosted on a server (CyberPanel, or a connected cPanel/Plesk panel).

    ``server`` is a name or id. Read-only, credential-free. A server with no panel returns
    a clear note. Each site: domain, state, PHP version, admin email.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc = await _resolve_server(db, user, server)
        if acc is None:
            return await _unknown_server(db, user, server)
        srv = acc.server
        await _audit(db, user, "list_sites", srv.id)
    # Live call — outside the DB session (SSH/API is slow; srv columns stay usable).
    try:
        sites = await hosting_service.list_websites(srv)
    except HostingError as exc:
        return f"{srv.name}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error listing sites on {srv.name}: {type(exc).__name__}"
    data = {"server": srv.name, "count": len(sites), "sites": sites}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    if not sites:
        return f"No sites found on {srv.name}."
    lines = [f"# Sites on {srv.name} ({len(sites)})", ""]
    for s in sites:
        php = f"  ·  PHP {s['php']}" if s.get("php") else ""
        lines.append(f"- **{s.get('domain', '?')}** — {s.get('state', '')}{php}")
    return "\n".join(lines)


@mcp_server.tool(name="serverally_list_files", annotations={"title": "List files", **_RO})
async def serverally_list_files(
    server: str, path: str = "/", show_hidden: bool = False,
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """List a directory on a server over SFTP (metadata only — name/type/size/permissions).

    ``server`` is a name or id; ``path`` an absolute directory. SSH servers only. Read-only.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc = await _resolve_server(db, user, server)
        if acc is None:
            return await _unknown_server(db, user, server)
        srv = acc.server
        if srv.connection_type != "ssh":
            return f"{srv.name}: file browsing needs an SSH server (this is '{srv.connection_type}')."
        await _audit(db, user, "list_files", srv.id)
    try:
        entries = await file_service.list_dir(srv, path or "/", show_hidden)
    except Exception as exc:  # noqa: BLE001
        return f"Error listing '{path}' on {srv.name}: {type(exc).__name__}: {exc}"[:250]
    items = [
        {"name": e["name"], "type": e["type"], "size": e["size"],
         "permissions": e["permissions"], "path": e["path"], "modified": _iso(e.get("modified"))}
        for e in entries
    ]
    data = {"server": srv.name, "path": path, "count": len(items), "entries": items}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    lines = [f"# {path} on {srv.name} ({len(items)} entries)", ""]
    for e in items:
        tag = "📁" if e["type"] == "dir" else "🔗" if e["type"] == "link" else "  "
        size = "" if e["type"] == "dir" else f"  ({e['size']} B)"
        lines.append(f"- {tag} `{e['name']}`{size}  {e['permissions']}")
    return "\n".join(lines)


@mcp_server.tool(name="serverally_read_file", annotations={"title": "Read a file", **_RO})
async def serverally_read_file(
    server: str, path: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN
) -> str:
    """Read a TEXT file on a server over SFTP.

    Secrets are masked **server-side** before returning (passwords, keys, tokens, connection
    strings, PEM blocks) — over MCP there is no client-side redaction, so this is enforced
    here. Binary files are refused; large files are truncated. ``server`` is a name or id;
    ``path`` an absolute file path. SSH servers only. Read-only.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc = await _resolve_server(db, user, server)
        if acc is None:
            return await _unknown_server(db, user, server)
        srv = acc.server
        if srv.connection_type != "ssh":
            return f"{srv.name}: reading files needs an SSH server (this is '{srv.connection_type}')."
        await _audit(db, user, "read_file", srv.id)
    try:
        res = await file_service.read_file(srv, path)
    except Exception as exc:  # noqa: BLE001
        return f"Error reading '{path}' on {srv.name}: {type(exc).__name__}: {exc}"[:250]
    raw = res.get("content") or ""
    if res.get("is_binary") or _looks_binary(raw):
        return f"'{path}' on {srv.name} is a binary file ({res.get('size', 0)} bytes) — not shown."
    content, hidden = redact_secrets(raw)
    truncated = len(content) > _FILE_CONTENT_CAP
    if truncated:
        content = content[:_FILE_CONTENT_CAP]
    data = {
        "server": srv.name, "path": path, "size": res.get("size"),
        "secrets_hidden": hidden, "truncated": truncated, "content": content,
    }
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    note = f"{res.get('size', 0)} bytes"
    if hidden:
        note += f", {hidden} secret(s) hidden"
    if truncated:
        note += ", truncated"
    return f"# {path} on {srv.name} ({note})\n\n```\n{content}\n```"


# ── MCP activity feed (docs/MCP-SERVER-PLAN.md) ───────────────────────────────
# Record every ACTION (run_command + the write tools) as a live running→finish row so the
# user can watch, in the app, what their connected AI does on their servers. Best-effort by
# construction — a recording failure never breaks a tool. Passive reads are NOT tracked, so
# the feed reads as "what the AI changed", not chatter.

class _ActivityHandle:
    """Outcome sink for a tracked action — the tool sets the result, _track records it."""

    def __init__(self) -> None:
        self.id: str | None = None
        self.status = "ok"
        self.exit_code: int | None = None
        self.detail: str | None = None

    def set_ok(self, exit_code: int | None = None, detail: str | None = None) -> None:
        self.status, self.exit_code, self.detail = "ok", exit_code, detail

    def set_blocked(self, detail: str | None = None) -> None:
        self.status, self.detail = "blocked", detail

    def set_error(self, detail: str | None = None) -> None:
        self.status, self.detail = "error", detail


async def _caller_client(db) -> tuple[str | None, str | None]:
    """(client_id, client_name) of the connected app, from the bearer token."""
    from mcp.server.auth.middleware.auth_context import get_access_token

    tok = get_access_token()
    cid = getattr(tok, "client_id", None) if tok else None
    if not cid:
        return None, None
    row = (await db.execute(select(OAuthClient).where(OAuthClient.client_id == cid))).scalar_one_or_none()
    return cid, (row.client_name if row else None)


@asynccontextmanager
async def _track(db, user: User, tool: str, srv, *, command: str | None = None):
    """Record an MCP action live (running → finish). Yields an _ActivityHandle the tool sets
    the outcome on; defaults to ok, records error on an exception. The 'running' row is
    committed (own session) before the work runs, so the feed shows it live."""
    handle = _ActivityHandle()
    try:
        cid, cname = await _caller_client(db)
        handle.id = await mcp_activity_service.start(
            user_id=user.id, client_id=cid, client_name=cname, tool=tool,
            server_id=(srv.id if srv is not None else None),
            server_name=(srv.name if srv is not None else None), command=command,
        )
    except Exception:  # noqa: BLE001
        logger.debug("mcp activity start failed", exc_info=True)
    try:
        yield handle
    except Exception:
        handle.status = "error"
        raise
    finally:
        await mcp_activity_service.finish(
            handle.id, status=handle.status, exit_code=handle.exit_code, detail=handle.detail
        )


# ── write tools (Phase 3) ─────────────────────────────────────────────────────
# Every write requires EXECUTE permission (Rule 7 across the boundary — a viewer can
# never execute). Deterministic — 0 AI actions. No shell, no deletes, no restore (§3).

# Non-read annotations. destructiveHint defaults False (scans change nothing); a tool that
# modifies the server overrides it to True.
_WRITE = {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True}


async def _executor(db, user: User, ref: str):
    """Resolve a server the caller may EXECUTE on. Returns ``(Access, None)`` when allowed,
    else ``(None, message)`` — a read-only connection, an unknown server, or missing execute
    permission."""
    # A read-only connection (Phase 4 scopes) cannot use write tools.
    from mcp.server.auth.middleware.auth_context import get_access_token
    from app.mcp.oauth_provider import SCOPE_WRITE

    token = get_access_token()
    if token is not None and SCOPE_WRITE not in (token.scopes or []):
        return None, (
            "This connection is read-only. Reconnect from ServerAlly → Settings → Connected "
            "applications with Full access to make changes."
        )
    acc = await _resolve_server(db, user, ref)
    if acc is None:
        return None, await _unknown_server(db, user, ref)
    if not acc.can_execute:
        return None, (
            f"You don't have permission to run actions on {acc.server.name} — this needs "
            "execute access, which your role doesn't grant."
        )
    return acc, None


@mcp_server.tool(name="serverally_run_security_scan", annotations={"title": "Run security scan", **_WRITE})
async def serverally_run_security_scan(server: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """Run a FRESH security audit on a server and save it, returning the grade + findings.

    The probes are read-only (they don't change the server), but this performs an action
    and needs execute permission. May take a minute. ``server`` is a name or id. If the call
    times out, the result is still saved — read it with get_security_scan.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc, err = await _executor(db, user, server)
        if err:
            return err
        srv = acc.server
        async with _track(db, user, "run_security_scan", srv) as act:
            result = await security_service.run_scan(srv)  # inline SSH scan (mirrors the router)
            counts = result["counts"]
            db.add(SecurityScan(
                server_id=srv.id, user_id=user.id, score=result["score"], grade=result["grade"],
                status=result["status"], error=result.get("error"), duration_ms=result.get("duration_ms"),
                critical_count=counts.get("critical", 0), high_count=counts.get("high", 0),
                medium_count=counts.get("medium", 0), low_count=counts.get("low", 0),
                pass_count=counts.get("pass", 0), info_count=counts.get("info", 0),
                findings=json.dumps(result["findings"]),
            ))
            await db.commit()
            await _audit(db, user, "run_security_scan", srv.id)
            act.set_ok(detail=f"grade {result['grade']} ({result['score']}/100)")
            data = {
                "server": srv.name, "grade": result["grade"], "score": result["score"], "counts": counts,
                "findings": [_scan_finding_public(f) for f in result["findings"] if isinstance(f, dict)],
            }
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    lines = [f"# {data['server']} security scan — grade {data['grade']} ({data['score']}/100)", f"Findings: {data['counts']}", ""]
    for f in data["findings"]:
        if f.get("status") == "pass":
            continue
        lines.append(f"- **[{f.get('severity', '?')}]** {f.get('title') or f.get('name', '')} — {f.get('detail') or f.get('description', '')}")
    return "\n".join(lines).rstrip()


@mcp_server.tool(name="serverally_run_threat_scan", annotations={"title": "Run threat scan", **_WRITE})
async def serverally_run_threat_scan(server: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """Run a FRESH threat/IOC scan on a server and save it, returning the verdict + evidence.

    Every probe is read-only (recommended fixes are display-only, never run), but this
    performs an action and needs execute permission. ``server`` is a name or id.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc, err = await _executor(db, user, server)
        if err:
            return err
        srv = acc.server
        async with _track(db, user, "run_threat_scan", srv) as act:
            result = await threat_service.run_scan(srv)
            counts = result["counts"]
            db.add(ThreatScan(
                server_id=srv.id, user_id=user.id, verdict=result["verdict"],
                status=result["status"], error=result.get("error"), duration_ms=result.get("duration_ms"),
                critical_count=counts.get("critical", 0), high_count=counts.get("high", 0),
                medium_count=counts.get("medium", 0), low_count=counts.get("low", 0),
                pass_count=counts.get("pass", 0), info_count=counts.get("info", 0),
                findings=json.dumps(result["findings"]),
            ))
            await db.commit()
            await _audit(db, user, "run_threat_scan", srv.id)
            act.set_ok(detail=f"verdict: {result['verdict']}")
            data = {
                "server": srv.name, "verdict": result["verdict"], "counts": counts,
                "findings": [_scan_finding_public(f) for f in result["findings"] if isinstance(f, dict)],
            }
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    lines = [f"# {data['server']} threat scan — {data['verdict']}", f"Findings: {data['counts']}", ""]
    for f in data["findings"]:
        lines.append(f"- **[{f.get('severity', '?')}]** {f.get('title') or f.get('name', '')} — {f.get('detail') or f.get('description') or f.get('evidence', '')}")
    return "\n".join(lines).rstrip()


@mcp_server.tool(
    name="serverally_run_playbook",
    annotations={"title": "Run a playbook", "readOnlyHint": False, "destructiveHint": True,
                 "idempotentHint": False, "openWorldHint": True},
)
async def serverally_run_playbook(
    server: str, playbook: str, variables: dict[str, str] | None = None,
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Start an official playbook (one-click install/config script) on a server.

    Returns a ``run_id`` IMMEDIATELY — the playbook runs in the background (it can take
    minutes); poll ``get_playbook_run(run_id)`` for progress and output. A playbook CHANGES
    the server, so this needs execute permission. ``playbook`` is a slug from list_playbooks;
    ``variables`` is a dict of that playbook's inputs. ``server`` is a name or id.
    """
    variables = variables or {}
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc, err = await _executor(db, user, server)
        if err:
            return err
        srv = acc.server
        pb = (await db.execute(
            select(Playbook).where(Playbook.slug == playbook, Playbook.is_official == True)  # noqa: E712
        )).scalar_one_or_none()
        if pb is None:
            return f"Playbook '{playbook}' not found. Use list_playbooks to see the available slugs."
        supported = supported_os_for(pb)
        if not os_matches(srv, supported):
            return (f"Playbook '{playbook}' needs {', '.join(supported or []) or 'a different OS'} — "
                    f"{srv.name} is {srv.os_type or 'unknown'}.")
        raw = pb.script_powershell if (srv.connection_type == "winrm" and pb.script_powershell) else pb.script_bash
        if not raw:
            return f"Playbook '{playbook}' has no script for {srv.name}'s OS."
        script = substitute_variables(raw, variables)
        run = PlaybookRun(
            server_id=srv.id, user_id=user.id, playbook_id=pb.id,
            variables_used=encrypt_variables(variables), status="running",
        )
        db.add(run)
        await db.flush()  # populate run.id
        run_id = str(run.id)
        srv_id = str(srv.id)
        srv_name = srv.name
        await db.commit()  # commit BEFORE enqueuing so the worker can find the run
        await _audit(db, user, "run_playbook", srv.id)

    run_playbook_task.delay(run_id, srv_id, script)  # durable background run
    data = {"run_id": run_id, "server": srv_name, "playbook": playbook, "status": "running",
            "note": "Started in the background. Poll get_playbook_run(run_id) for progress and output."}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    return (f"▶ Started **{playbook}** on {srv_name}. Run id `{run_id}`.\n\n"
            "It runs in the background — call `get_playbook_run` with that id to follow progress.")


@mcp_server.tool(name="serverally_get_playbook_run", annotations={"title": "Playbook run status", **_RO})
async def serverally_get_playbook_run(run_id: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """Status + output of a playbook run started with run_playbook.

    ``run_id`` is what run_playbook returned. Scoped to your own runs. Output is truncated to
    the most recent portion. Read-only.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        try:
            rid = uuid.UUID(str(run_id))
        except ValueError:
            return "Invalid run_id — use the id returned by run_playbook."
        run = (await db.execute(
            select(PlaybookRun).where(PlaybookRun.id == rid, PlaybookRun.user_id == user.id)
        )).scalar_one_or_none()
        await _audit(db, user, "get_playbook_run")
        if run is None:
            return "Playbook run not found (or it belongs to another account)."
        output = run.output or ""
        if len(output) > _FILE_CONTENT_CAP:
            output = "… (earlier output trimmed)\n" + output[-_FILE_CONTENT_CAP:]
        data = {
            "run_id": str(run.id), "status": run.status,
            "started_at": _iso(run.started_at), "completed_at": _iso(run.completed_at),
            "failure_reason": run.failure_reason, "output": output,
        }
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    lines = [f"# Playbook run {data['run_id']} — {data['status']}"]
    if data["failure_reason"]:
        lines.append(f"**Failed:** {data['failure_reason']}")
    body = output[-4000:] if output else "(no output captured yet — still running or just started)"
    lines.append(f"\n```\n{body}\n```")
    return "\n".join(lines)


# ── hosting + backup writes (Phase 3) ─────────────────────────────────────────
# Additive, procedure-carrying writes (§3a): create sites/databases, issue SSL, run an
# existing backup. Execute-gated. No deletes, no restore (§3). The underlying
# cyberpanel_cli.create_website already verifies the site really appears before success.

@mcp_server.tool(name="serverally_list_backups", annotations={"title": "List backup jobs", **_RO})
async def serverally_list_backups(server: str = "", response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """Configured backup jobs the caller can see. Optional ``server`` (name or id) filter.

    Read-only. Each: id, name, type, source, server, schedule, last_run, last_status. Use the
    id with run_backup. Never returns the backup's stored DB credential.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        servers = await team_service.accessible_servers(db, user)
        name_by_id = {s.id: s.name for s in servers}
        ids = list(name_by_id)
        if server.strip():
            acc = await _resolve_server(db, user, server)
            if acc is None:
                return await _unknown_server(db, user, server)
            ids = [acc.server.id]
        rows = (await db.execute(
            select(Backup).where(Backup.server_id.in_(ids)).order_by(Backup.created_at)
        )).scalars().all() if ids else []
        await _audit(db, user, "list_backups")
        items = [
            {"id": str(b.id), "name": b.name, "type": b.backup_type, "source": b.source,
             "server": name_by_id.get(b.server_id), "schedule": b.human_schedule or b.cron_expression,
             "active": b.is_active, "last_run": _iso(b.last_run), "last_status": b.last_status}
            for b in rows
        ]
        data = {"count": len(items), "backups": items}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    if not items:
        return "No backup jobs configured."
    lines = [f"# Backup jobs ({len(items)})", ""]
    for b in items:
        lines.append(f"- **{b['name']}** ({b['type']}) on {b['server']} — {b['schedule'] or 'manual'}  ·  "
                     f"last: {b['last_status'] or 'never'}  ·  `{b['id']}`")
    return "\n".join(lines)


@mcp_server.tool(name="serverally_run_backup", annotations={"title": "Run a backup", **_WRITE})
async def serverally_run_backup(backup_id: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """Run an EXISTING backup job now (no ad-hoc definitions — only jobs already configured).

    ``backup_id`` is from list_backups. Requires execute permission on the backup's server.
    Non-destructive (it creates an archive). May take a while for large data.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        try:
            bid = uuid.UUID(str(backup_id))
        except ValueError:
            return "Invalid backup_id — use the id from list_backups."
        backup = (await db.execute(select(Backup).where(Backup.id == bid))).scalar_one_or_none()
        if backup is None:
            return "Backup job not found."
        acc, err = await _executor(db, user, str(backup.server_id))
        if err:
            return err
        srv = acc.server
        run = await backup_service.perform_backup(db, srv, backup)
        await _audit(db, user, "run_backup", srv.id)
        data = {"backup": backup.name, "server": srv.name, "status": run.status,
                "artifact": run.artifact_path, "size_bytes": run.size_bytes, "run_id": str(run.id)}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    ok = "✅" if data["status"] == "success" else "⚠️"
    size = f" ({data['size_bytes']} bytes)" if data["size_bytes"] else ""
    return f"{ok} Backup **{data['backup']}** on {data['server']} — {data['status']}{size}."


@mcp_server.tool(name="serverally_create_site", annotations={"title": "Create a website", **_WRITE})
async def serverally_create_site(
    server: str, domain: str, php: str = "8.1", email: str = "",
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Create a new website/domain on a CyberPanel (or connected hosting) server.

    Verifies the site actually appears before reporting success (the underlying CLI can
    report success while failing). Requires execute permission. ``server`` name/id.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc, err = await _executor(db, user, server)
        if err:
            return err
        srv = acc.server
        await _audit(db, user, "create_site", srv.id)
    body = {"domain": domain, "php": php}
    if email:
        body["email"] = email
    try:
        result = await hosting_service.create_website(srv, body)
    except HostingError as exc:
        return f"Could not create {domain} on {srv.name}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error creating {domain} on {srv.name}: {type(exc).__name__}"
    data = {"server": srv.name, "domain": domain, "result": result}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    return f"✅ Created **{domain}** on {srv.name} (PHP {php}). Point its DNS at the server, then issue SSL."


@mcp_server.tool(name="serverally_issue_ssl", annotations={"title": "Issue SSL", **_WRITE})
async def serverally_issue_ssl(server: str, domain: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN) -> str:
    """Issue (or renew) a free Let's Encrypt SSL certificate for a domain on the server.

    The domain's DNS must already point to the server, or issuance fails. Requires execute
    permission. ``server`` is a name or id.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc, err = await _executor(db, user, server)
        if err:
            return err
        srv = acc.server
        await _audit(db, user, "issue_ssl", srv.id)
    try:
        result = await hosting_service.issue_ssl(srv, domain)
    except HostingError as exc:
        return f"Could not issue SSL for {domain} on {srv.name}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error issuing SSL for {domain} on {srv.name}: {type(exc).__name__}"
    if response_format == ResponseFormat.JSON:
        return json.dumps({"server": srv.name, "domain": domain, "result": result}, indent=2)
    return f"🔒 SSL issued for **{domain}** on {srv.name}."


@mcp_server.tool(name="serverally_create_database", annotations={"title": "Create a database", **_WRITE})
async def serverally_create_database(
    server: str, domain: str, db_name: str, db_user: str, db_password: str,
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Create a MySQL/MariaDB database + user on a hosting server.

    You supply ``db_password`` — it is used to create the database and is NEVER returned or
    stored by this tool. ``domain`` is the site the DB belongs to. Requires execute
    permission. ``server`` is a name or id.
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc, err = await _executor(db, user, server)
        if err:
            return err
        srv = acc.server
        await _audit(db, user, "create_database", srv.id)
    body = {"domain": domain, "db_name": db_name, "db_user": db_user, "db_password": db_password}
    try:
        await hosting_service.create_database(srv, body)
    except HostingError as exc:
        return f"Could not create database {db_name} on {srv.name}: {exc}"
    except Exception as exc:  # noqa: BLE001
        return f"Error creating database {db_name} on {srv.name}: {type(exc).__name__}"
    # Never echo the password back.
    data = {"server": srv.name, "domain": domain, "db_name": db_name, "db_user": db_user, "status": "created"}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    return f"✅ Created database **{db_name}** (user {db_user}) on {srv.name}."


# ── admin tool: run_command (Full power / mcp:admin) ──────────────────────────
# "Full power" adds a real shell: the caller's own AI runs arbitrary commands and gets
# stdout/stderr. This deliberately crosses the "no shell over MCP" line (§3), at the
# user's EXPLICIT opt-in on the consent page. The floor that ALWAYS holds: every command
# passes the same absolute blocklist Ally uses (catastrophic commands refused), execution
# needs execute permission (Rule 7), and every call is audit-logged. ServerAlly's HIGHER
# safety layers (skills, verify-gate, step approval, injection framing) do NOT wrap this —
# over MCP the caller's AI is the reasoner. See the Decisions Log (2026-07-24).

_CMD_OUTPUT_CAP = 30_000  # cap stdout+stderr returned to the caller
_ADMIN = {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}


async def _admin_executor(db, user: User, ref: str):
    """Resolve a server the caller may run ARBITRARY COMMANDS on. Requires the mcp:admin
    scope (Full power) AND execute permission (Rule 7). Returns ``(Access, None)`` or
    ``(None, message)``."""
    from mcp.server.auth.middleware.auth_context import get_access_token
    from app.mcp.oauth_provider import SCOPE_ADMIN

    token = get_access_token()
    if token is not None and SCOPE_ADMIN not in (token.scopes or []):
        return None, (
            "This connection can't run commands. Reconnect from ServerAlly → Settings → "
            "Connected applications and choose 'Full power' to enable running commands."
        )
    acc = await _resolve_server(db, user, ref)
    if acc is None:
        return None, await _unknown_server(db, user, ref)
    if not acc.can_execute:
        return None, (
            f"You don't have permission to run commands on {acc.server.name} — this needs "
            "execute access, which your role doesn't grant."
        )
    return acc, None


@mcp_server.tool(name="serverally_run_command", annotations={"title": "Run a shell command", **_ADMIN})
async def serverally_run_command(
    server: str, command: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN
) -> str:
    """Run a shell command on a server and return its stdout, stderr, and exit code.

    FULL POWER — needs a connection made with 'Full power' access (the mcp:admin scope).
    Runs on Linux servers (bash, over SSH) and Windows servers (PowerShell, over WinRM).
    ``server`` is a name or id; ``command`` is the exact command line to run.

    Safety: every command is first checked against ServerAlly's absolute blocklist, so
    catastrophic commands (e.g. ``rm -rf /``, ``mkfs``, fork bombs) are REFUSED. Everything
    else runs as-is — there is no confirmation prompt and no undo. This is a real terminal;
    every call is audit-logged. Prefer read-only commands (``docker logs``, ``systemctl
    status``, ``df -h``) unless you intend to change the server.
    """
    command = (command or "").strip()
    if not command:
        return "No command was given."
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        acc, err = await _admin_executor(db, user, server)
        if err:
            return err
        srv = acc.server
        sname = srv.name  # capture now — _audit commits below (expires ORM attrs), and we format after the session closes
        # A shell needs a command channel — SSH or WinRM only (hosting/RDP have none).
        if srv.connection_type not in ("ssh", "winrm"):
            return (
                f"{sname}: running commands needs an SSH or Windows (WinRM) server "
                f"(this one is '{srv.connection_type}', which has no command channel)."
            )
        # Absolute safety floor: refuse catastrophic commands (the same blocklist Ally uses).
        os_family = "windows" if srv.connection_type == "winrm" or (srv.shell or "") == "powershell" else "linux"
        verdict = safety_service.validate_command(
            command, os_family, safety_service.access_for(srv))
        # Track the action live (running → finish) so the user sees it in the app's feed.
        async with _track(db, user, "run_command", srv, command=command) as act:
            if verdict.status == "blocked":
                act.set_blocked("On ServerAlly's absolute blocklist — refused.")
                await _audit(db, user, "run_command_blocked", srv.id)
                return (
                    f"⛔ Refused on {sname}: this command is on ServerAlly's absolute safety "
                    "blocklist because it could irreversibly destroy the server. Nothing was run."
                )
            await _audit(db, user, "run_command", srv.id)  # the call is audited; the command text is not, to never log a secret
            try:
                stdout, stderr, exit_code = await connection_manager.execute(srv, command)
            except Exception as exc:  # noqa: BLE001
                act.set_error(type(exc).__name__)
                return f"Error running the command on {sname}: {type(exc).__name__}: {exc}"[:300]
            act.set_ok(exit_code=exit_code)  # the exit code shows as its own chip; no redundant detail

    stdout, stderr = stdout or "", stderr or ""
    truncated = len(stdout) + len(stderr) > _CMD_OUTPUT_CAP
    if truncated:
        stdout = stdout[:_CMD_OUTPUT_CAP]
        stderr = stderr[: max(0, _CMD_OUTPUT_CAP - len(stdout))]
    if response_format == ResponseFormat.JSON:
        return json.dumps({
            "server": sname, "command": command, "exit_code": exit_code,
            "stdout": stdout, "stderr": stderr, "truncated": truncated,
        }, indent=2)
    out = [f"# `{command}` on {sname} — exit {exit_code}" + (" · output truncated" if truncated else "")]
    if stdout.strip():
        out.append(f"\n**stdout**\n```\n{stdout.rstrip()}\n```")
    if stderr.strip():
        out.append(f"\n**stderr**\n```\n{stderr.rstrip()}\n```")
    if not stdout.strip() and not stderr.strip():
        out.append("\n_(no output)_")
    return "\n".join(out)


# ── DNS ───────────────────────────────────────────────────────────────────────
#
# Three tools, and the shape of them is the design.
#
# **There is one write tool, `set_dns_record`, not a create and an update.** The caller's
# AI is asked for an intent — "make api.example.com point at 1.2.3.4" — and should not have
# to first discover whether that record exists. More importantly, separate create/update is
# how the most common DNS accident happens: a SECOND A record is added instead of the first
# being changed, so half the visitors keep reaching the old server. That failure looks
# intermittent, survives a cache flush, and is genuinely hard to diagnose.
#
# **There is deliberately no delete tool.** MCP's rule is no shell, no delete, no restore
# (Decisions Log, 2026-07-23) and DNS is exactly why: removing an MX record stops mail with
# no undo anywhere in the system. Fixing a wrong record — the thing people actually need —
# is what `set` does.
#
# The rules that decide whether a record is sane live in `dns_service.validate`, and are
# reused rather than restated here: a CNAME on the apex, an MX pointing at an IP address, a
# TTL below the floor. Every one of them is a value the provider would happily accept and
# which breaks the domain quietly.

def _full_access_required() -> str | None:
    """Whether this connection is Full access. A message when it is not.

    The server-based tools get this from `_executor`, which resolves a server at the same
    time. DNS has no server, and the .env tools resolve theirs differently — so the scope is
    checked on its own here rather than quietly skipped.

    Named for what it CHECKS rather than for its first caller: it now guards DNS changes and
    both settings-file tools, and a rule named after one of its callers is how a second copy
    gets written for the next one.
    """
    from mcp.server.auth.middleware.auth_context import get_access_token

    from app.mcp.oauth_provider import SCOPE_WRITE

    token = get_access_token()
    if token is not None and SCOPE_WRITE not in (token.scopes or []):
        return ("This connection is read-only. Reconnect from ServerAlly → Settings → "
                "Connected applications with Full access to change DNS.")
    return None


def _dns_match(existing: list, rec: dict) -> list:
    """The records this change would replace: same type, same name.

    Pulled out and named because it is the whole rule. Inline, the only thing a test could
    check was that the existing records had been READ — and a mutation that read them and
    then ignored them, always creating, passed happily. That mutation IS the bug: a second
    A record beside the first, half the visitors on the old server.

    Compared case-insensitively because DNS names are, and a provider may return them in a
    different case from the one we sent.
    """
    return [r for r in existing
            if r.type == rec["type"] and r.name.lower() == rec["name"].lower()]


async def _dns_zone(db, user: User, zone: str):
    """Find a zone by NAME across the caller's DNS accounts.

    By name because that is what the caller knows — an AI asked to fix `example.com` has no
    zone id and no account id. Returns ``(account, zone, None)`` or ``(None, None, message)``.
    """
    from app.models.dns_account import DnsAccount
    from app.services import dns_service as dns

    wanted = (zone or "").strip().lower().rstrip(".")
    if not wanted:
        return None, None, "Which domain? Give the zone, for example example.com."

    accounts = (await db.execute(
        select(DnsAccount).where(DnsAccount.user_id == user.id)
    )).scalars().all()
    if not accounts:
        return None, None, ("No DNS provider is connected to this ServerAlly account. "
                            "Connect one in ServerAlly → DNS first.")

    seen: list[str] = []
    for a in accounts:
        try:
            for z in await dns.list_zones(a):
                seen.append(z.name)
                if z.name.lower().rstrip(".") == wanted:
                    return a, z, None
        except dns.DnsError:
            # One provider being unreachable must not hide a zone held by another.
            continue
    known = ", ".join(sorted(set(seen))[:20]) or "none"
    return None, None, f"No zone called “{zone}” on this account. Zones here: {known}."


@mcp_server.tool(name="serverally_list_dns_zones",
                 annotations={"title": "List DNS zones", **_RO})
async def serverally_list_dns_zones(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """List every DNS zone (domain) the caller's connected providers manage.

    Read-only. Never returns the provider API token.
    """
    from app.models.dns_account import DnsAccount
    from app.services import dns_service as dns

    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        accounts = (await db.execute(
            select(DnsAccount).where(DnsAccount.user_id == user.id)
        )).scalars().all()
        if not accounts:
            return "No DNS provider is connected. Connect one in ServerAlly → DNS."
        out = []
        for a in accounts:
            try:
                for z in await dns.list_zones(a):
                    out.append({"zone": z.name, "status": z.status,
                                "provider": a.provider, "account": a.label})
            except dns.DnsError as exc:
                out.append({"zone": None, "provider": a.provider,
                            "account": a.label, "error": str(exc)})

    if response_format == ResponseFormat.JSON:
        return json.dumps({"count": len(out), "zones": out}, indent=2)
    lines = [f"# DNS zones ({len(out)})", ""]
    for z in out:
        if z.get("error"):
            lines.append(f"- ⚠️ {z['account']} ({z['provider']}): {z['error']}")
        else:
            lines.append(f"- **{z['zone']}** — {z['status']} · {z['provider']}")
    return "\n".join(lines)


@mcp_server.tool(name="serverally_list_dns_records",
                 annotations={"title": "List DNS records", **_RO})
async def serverally_list_dns_records(
    zone: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """List the DNS records in a zone. ``zone`` is the domain, e.g. ``example.com``.

    Read-only. Records the provider manages itself (NS, SOA) are shown but marked
    non-editable — they are visible because a wrong answer often makes sense only once you
    can see them, and they are not changeable because editing them breaks the domain.
    """
    from app.services import dns_service as dns

    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        account, z, err = await _dns_zone(db, user, zone)
        if err:
            return err
        try:
            found = await dns.list_records(account, z.zone_id)
        except dns.DnsError as exc:
            return f"Could not read the records for {z.name}: {exc}"

    records = [dns.public_record(r) for r in found]
    if response_format == ResponseFormat.JSON:
        return json.dumps({"zone": z.name, "count": len(records),
                           "editable_types": list(dns.MANAGED_TYPES),
                           "records": records}, indent=2)
    lines = [f"# {z.name} — {len(records)} records", ""]
    for r in records:
        lock = "" if r["editable"] else "  _(managed by the provider)_"
        pri = f" priority {r['priority']}" if r["priority"] is not None else ""
        lines.append(f"- **{r['type']}** `{r['name']}` → `{r['content']}`"
                     f" · TTL {r['ttl']}{pri}{lock}")
    return "\n".join(lines)


@mcp_server.tool(name="serverally_set_dns_record",
                 annotations={"title": "Set a DNS record", **_WRITE})
async def serverally_set_dns_record(
    zone: str, type: str, name: str, content: str, ttl: int = 300,
    priority: int | None = None, proxied: bool | None = None,
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Point a DNS name at a value — creating the record, or changing the existing one.

    This is an upsert on purpose. Ask for what the record SHOULD be and it is made so:
    if no record of this type and name exists it is created, and if exactly one exists it
    is changed. That avoids the most common DNS accident, which is adding a second A record
    instead of correcting the first — leaving half of visitors on the old server, a failure
    that looks intermittent and is very hard to trace.

    **When several records already share this type and name it REFUSES** and lists them.
    That is legitimate for MX, TXT and round-robin A records, and choosing which one to
    replace is the owner's decision, not a guess this tool should make.

    There is no delete tool. Removing a record — an MX above all — stops something working
    with no undo; fixing a wrong value is what this does.

    Args:
        zone: the domain, e.g. ``example.com``.
        type: A, AAAA, CNAME, TXT, MX, SRV or CAA. NS and SOA cannot be changed.
        name: the host — ``@`` or the domain for the apex, or ``www``/``api``.
        content: the value — an IP for A, a hostname for CNAME/MX, text for TXT.
        ttl: seconds; 1 means automatic at Cloudflare.
        priority: required for MX and SRV.
        proxied: Cloudflare's orange cloud, when the provider supports it.
    """
    from app.services import dns_service as dns

    denied = _full_access_required()
    if denied:
        return denied

    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        account, z, err = await _dns_zone(db, user, zone)
        if err:
            return err

        # The rules live in one place and are reused, never restated: a CNAME on the apex,
        # an MX pointing at an IP, a TTL under the floor. Each is a value the provider
        # accepts and which breaks the domain quietly.
        try:
            rec = dns.validate(type_=type, name=name, content=content,
                               zone=z.name, ttl=ttl, priority=priority)
        except dns.InvalidRecord as exc:
            return f"❌ {exc}"
        if proxied is not None:
            rec["proxied"] = proxied

        try:
            existing = await dns.list_records(account, z.zone_id)
        except dns.DnsError as exc:
            # Cannot look, so cannot know whether this would duplicate. Refusing is the
            # honest answer — creating blind is how the second A record appears.
            return (f"Could not read the existing records for {z.name}, so nothing was "
                    f"changed: {exc}")

        matches = _dns_match(existing, rec)
        if len(matches) > 1:
            listed = "; ".join(f"{r.content}" for r in matches)
            return (f"❌ {z.name} already has {len(matches)} {rec['type']} records for "
                    f"`{rec['name']}` ({listed}). Several records sharing a name is normal "
                    f"for MX, TXT and round-robin A records, so this tool will not guess "
                    f"which one you meant to replace. Change it in ServerAlly → DNS.")

        warning = dns.warn_for(type_=rec["type"], name=rec["name"], zone=z.name,
                               existing=existing)
        try:
            if matches:
                saved = await dns.update_record(account, z.zone_id,
                                                matches[0].record_id, rec)
                action, before = "updated", matches[0].content
            else:
                saved = await dns.create_record(account, z.zone_id, rec)
                action, before = "created", None
        except dns.DnsError as exc:
            return f"Could not save the record: {exc}"

        # DNS changes are the ones people need to reconstruct later — "when did this
        # break?" is usually answered by finding the record change that caused it.
        await _audit(db, user, f"dns_record_{action}")

    data = {"zone": z.name, "action": action, "previous": before,
            "record": dns.public_record(saved), "warning": warning}
    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2)
    was = f" (was `{before}`)" if before else ""
    msg = (f"✅ {action.capitalize()} **{saved.type}** `{saved.name}` → "
           f"`{saved.content}`{was} in {z.name}.")
    if warning:
        msg += f"\n\n⚠️ {warning}"
    msg += f"\n\nChanges can take up to the TTL ({saved.ttl}s) to reach everyone."
    return msg


# ── a site's settings file (.env) ─────────────────────────────────────────────
#
# Built because the alternative was worse. `read_file` REDACTS secrets over MCP — deliberately,
# since there is no client-side redaction out here — so an AI that needs an application's
# credentials cannot get them through the proper tool, and its workaround is `run_command`:
# a full shell, with none of ServerAlly's higher protections and no rollback. Asking for the
# shell in order to read one file is a safety control being walked around.
#
# So these two tools do the job the shell was being borrowed for, bounded to one file, and
# with the protections `cat > .env` could never have: the content never touches a command
# line, the old file is kept and put back if the site stops serving, ownership and mode
# travel across, and Laravel's config cache is rebuilt (without which the edit appears to do
# nothing at all).
#
# **Reading requires Full access, not Read-only.** These return real credentials, and a
# customer who picked "Read-only" believes they granted something that cannot hurt them —
# handing over every database password would make that label a lie.

async def _resolve_site(db, user: User, ref: str):
    """Find one of the caller's sites by DOMAIN (or id). Returns ``(site, message)``."""
    from sqlalchemy import or_
    from app.models.site import Site

    wanted = (ref or "").strip().lower().rstrip(".")
    if not wanted:
        return None, "Which site? Give its domain, for example shop.example.com."
    rows = (await db.execute(
        select(Site).where(Site.user_id == user.id, Site.is_present.is_(True))
    )).scalars().all()
    hits = [s for s in rows if (s.domain or "").lower() == wanted or str(s.id) == ref]
    if not hits:
        known = ", ".join(sorted(s.domain for s in rows)[:15]) or "none"
        return None, f"No site called “{ref}” on this account. Sites here: {known}."
    if len(hits) > 1:
        # One domain on two servers. Which one holds the credentials being asked for is not
        # something to guess at.
        where = ", ".join(str(s.server_id) for s in hits)
        return None, (f"“{ref}” exists on more than one server ({where}). Use the site's id "
                      f"rather than its domain.")
    return hits[0], None


async def _env_target(db, user: User, ref: str):
    """The site, its server and where its application really lives — or a message.

    The app root comes from the Laravel probe, which finds it by locating `artisan`. Never
    from the caller and never guessed from the document root, because this path decides
    which file gets read or rewritten.
    """
    from app.services import laravel_service

    site, err = await _resolve_site(db, user, ref)
    if err:
        return None, None, None, err
    acc = await _resolve_server(db, user, str(site.server_id))
    if acc is None:
        return None, None, None, f"You do not have access to the server {site.domain} is on."
    if not acc.can_execute:
        return None, None, None, (f"You have view-only access to {acc.server.name}, so its "
                                  f"settings files are not available.")
    server = acc.server
    if server.connection_type != "ssh":
        return None, None, None, ("Settings files are read over SSH on a Linux server.")
    if (site.app_type or "") != "laravel":
        return None, None, None, (
            f"{site.domain} does not run a Laravel application, and this reads the .env of "
            f"one. For other files use serverally_read_file (which masks secrets).")
    app = await laravel_service.read(server, site.doc_root or "")
    if not app.get("ok") or not app.get("path"):
        return None, None, None, (app.get("reason") or "We could not read this application.")
    return site, server, app, None


@mcp_server.tool(name="serverally_get_site_env",
                 annotations={"title": "Read a site's settings (.env)", **_RO})
async def serverally_get_site_env(
    site: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Read a Laravel site's ``.env`` — the real values, not masked.

    Unlike ``serverally_read_file``, which masks secrets, this returns them: reading the
    credentials IS the purpose here, rather than an accident of reading some other file.

    For that reason it needs a **Full access** connection even though it only reads. A
    Read-only connection is one the customer believes cannot hurt them, and handing it every
    database password would make that promise false.

    Fetched over SFTP, never through a shell command — a command's arguments are visible in
    ``ps`` and are kept in the stored output of the run, and every line of this file is a
    credential.

    Args:
        site: the domain, e.g. ``shop.example.com``.
    """
    from app.services import connection_manager, env_service, file_service

    denied = _full_access_required()
    if denied:
        return ("Reading a settings file returns real credentials, so it needs a Full access "
                "connection. " + denied.split(". ", 1)[-1])

    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        site_row, server, app, err = await _env_target(db, user, site)
        if err:
            return err
        try:
            path = env_service.env_path(app["path"])
        except env_service.EnvError as exc:
            return str(exc)

        out, e, _c = await connection_manager.execute(
            server, env_service.build_facts_command(app["path"], site_row.domain))
        facts = env_service.parse_facts((out or "") + (e or ""))
        content = ""
        if facts["exists"]:
            try:
                content = (await file_service.download_file(server, path)).decode(
                    "utf-8", errors="replace")
            except Exception as exc:  # noqa: BLE001
                return f"That file could not be read: {exc}"
        await _audit(db, user, "site_env_read", server.id)

    warning = env_service.exposure_warning(facts)
    if response_format == ResponseFormat.JSON:
        return json.dumps({"site": site_row.domain, "path": path, "exists": facts["exists"],
                           "content": content, "warning": warning}, indent=2)
    head = f"# {site_row.domain} — `{path}`"
    if warning:
        head += f"\n\n⚠️ {warning}"
    if not facts["exists"]:
        return head + "\n\n_There is no .env file here yet._"
    return head + f"\n\n```dotenv\n{content.rstrip()}\n```"


@mcp_server.tool(name="serverally_set_site_env",
                 annotations={"title": "Save a site's settings (.env)", **_WRITE})
async def serverally_set_site_env(
    site: str, content: str, response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """Replace a Laravel site's ``.env``, and put the old one back if the site stops working.

    Send the WHOLE file, not a fragment — this replaces it. Read it first with
    ``serverally_get_site_env``, change what you need, and send the result back.

    What this does that writing the file through a shell would not:

    - the content never touches a command line, so it cannot leak into ``ps`` or the stored
      output of the run
    - the previous file is kept and **restored if the site stops serving** after the change
    - ownership and mode are carried across, or the application can no longer read its own
      configuration and every page becomes a 500
    - Laravel's config cache is rebuilt when it was in use — without that the edit appears
      to do nothing, which is the most confusing outcome available here

    The audit records THAT the file changed and nothing about what is in it.
    """
    from app.services import connection_manager, env_service, file_service

    denied = _full_access_required()
    if denied:
        return denied

    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return _NO_USER
        site_row, server, app, err = await _env_target(db, user, site)
        if err:
            return err
        try:
            data = env_service.check_content(content)
            root = app["path"].rstrip("/")
            tmp = f"{root}/{env_service.TMP_NAME}"
        except env_service.EnvError as exc:
            return f"❌ {exc}"

        try:
            await file_service.upload_file(server, tmp, data)
        except Exception as exc:  # noqa: BLE001
            return f"Those settings could not be sent: {exc}"

        out, e, code = await connection_manager.execute(
            server, env_service.build_apply_command(
                root, site_row.domain, php_bin=app.get("php_bin", ""),
                rebuild_cache=bool(app.get("cache_config"))))
        ok, message = env_service.explain(code, (out or "") + (e or ""))
        if not ok:
            # Never leave our half-written copy beside the real file — it holds the same
            # credentials.
            await connection_manager.execute(server, env_service.build_discard_command(root))
            return f"❌ {message}"
        await _audit(db, user, "site_env_saved", server.id)

    if response_format == ResponseFormat.JSON:
        return json.dumps({"site": site_row.domain, "saved": True,
                           "bytes": len(data), "message": message}, indent=2)
    return f"✅ Saved `{site_row.domain}` settings ({len(data)} bytes). {message}"
