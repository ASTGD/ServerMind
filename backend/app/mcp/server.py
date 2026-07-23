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
from datetime import datetime, timedelta, timezone
from enum import Enum

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.alert import ServerMetric
from app.models.mission import Mission
from app.models.playbook import Playbook
from app.models.security_scan import SecurityScan
from app.models.server import Server
from app.models.threat_scan import ThreatScan
from app.models.user import User
from app.services import audit_service, fleet_service, mission_service, team_service

logger = logging.getLogger(__name__)

# Stateless JSON over Streamable HTTP — simplest to scale/proxy and the right
# shape for the Phase-1 OAuth bearer flow. Served at exactly ``/mcp`` (inner path
# "/" here, mounted at "/mcp" in main.py).
mcp_server = FastMCP(
    "serverally_mcp",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
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
