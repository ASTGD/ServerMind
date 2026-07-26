"""``/api/v1`` — the surface a customer's own code talks to.

Every route here authenticates with an **API key** and nothing else. That is the security
design: this router is a deliberately small set of thin adapters over the existing service
layer, so the dangerous operations are not guarded by a check that someone could forget to
add — they simply have no route here at all.

Not reachable with a key, by construction: changing a password or email, 2FA, reading a
server credential, minting or listing API keys, deleting a server, and running an arbitrary
shell command. A customer who wants their AI to do open-ended work uses the MCP connector,
which has its own consent flow and its own audit trail.

Every route is scoped to the caller (``team_service``), so a key sees exactly the servers its
owner can see — CLAUDE.md rule 7 — and writes additionally require the ``write`` scope *and*
execute permission on that server.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.api_key import ApiCaller, get_api_caller, require_write
from app.models.alert import ServerMetric
from app.models.escalation import STATUS_ACKNOWLEDGED, STATUS_OPEN, Incident
from app.models.playbook import Playbook, PlaybookRun
from app.models.security_scan import SecurityScan
from app.models.server import Server
from app.models.uptime import UptimeMonitor
from app.services import (
    escalation_service, fleet_service, incident_service, playbook_service,
    secret_vars, team_service,
)
from app.services.rate_limit_service import limiter
from app.workers.playbook_tasks import run_playbook_task

router = APIRouter(prefix="/api/v1", tags=["public-api"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
Caller = Annotated[ApiCaller, Depends(get_api_caller)]
Writer = Annotated[ApiCaller, Depends(require_write)]


# ── Serialising ──────────────────────────────────────────────────────────────
# Allowlists, not model dumps. A `Server` row carries `encrypted_cred` and `fingerprint`;
# dumping it would publish both the first time someone added a field. Same reasoning as the
# MCP tools and the admin console.

def _server(s: Server) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "host": s.host,
        "category": s.category,
        "connection_type": s.connection_type,
        "os": s.os_type,
        "os_version": s.os_version,
        "status": s.status,
        "tags": list(s.tags or []),
        "last_seen": s.last_seen.isoformat() if s.last_seen else None,
    }


def _metric(m: ServerMetric | None) -> dict | None:
    if m is None:
        return None
    return {
        "cpu_percent": float(m.cpu_percent) if m.cpu_percent is not None else None,
        "ram_percent": float(m.ram_percent) if m.ram_percent is not None else None,
        "disk_percent": float(m.disk_percent) if m.disk_percent is not None else None,
        "load_1": float(m.load_1) if m.load_1 is not None else None,
        "uptime_seconds": m.uptime_seconds,
        "recorded_at": m.recorded_at.isoformat() if m.recorded_at else None,
    }


def _run(r: PlaybookRun) -> dict:
    return {
        "run_id": str(r.id),
        "server_id": str(r.server_id),
        "status": r.status,
        "output": r.output,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


async def _resolve(db: AsyncSession, caller: ApiCaller, server: str) -> Server:
    """Find a server by id or name, scoped to what the caller may see.

    Accepting a name as well as an id is what makes the API usable from a shell script,
    where hardcoding a UUID is miserable.
    """
    reachable = await team_service.accessible_servers(db, caller.user)
    try:
        wanted = uuid.UUID(server)
        match = next((s for s in reachable if s.id == wanted), None)
    except ValueError:
        low = server.strip().lower()
        match = next((s for s in reachable if s.name.lower() == low), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"No server '{server}' you can access.")
    return match


async def _executable(db: AsyncSession, caller: ApiCaller, server: str) -> Server:
    """Same, but the caller must also be allowed to change that server."""
    srv = await _resolve(db, caller, server)
    access = await team_service.get_access(db, caller.user, srv.id)
    if access is None or not access.can_execute:
        raise HTTPException(status_code=403,
                            detail=f"You don't have permission to make changes on {srv.name}.")
    return srv


# ── Who am I ─────────────────────────────────────────────────────────────────

@router.get("/whoami")
async def whoami(caller: Caller) -> dict:
    """Confirm a key works and show what it can do — the first call anyone makes."""
    return {
        "account": caller.user.email,
        "plan": caller.user.plan,
        "key": {"name": caller.key.name, "prefix": caller.key.prefix,
                "scopes": list(caller.key.scopes or [])},
        "can_write": caller.can_write,
    }


# ── Servers ──────────────────────────────────────────────────────────────────

@router.get("/servers")
async def list_servers(db: DBDep, caller: Caller) -> dict:
    servers = await team_service.accessible_servers(db, caller.user)
    return {"servers": [_server(s) for s in servers], "count": len(servers)}


@router.get("/servers/{server}")
async def get_server(server: str, db: DBDep, caller: Caller) -> dict:
    srv = await _resolve(db, caller, server)
    latest = (await db.execute(
        select(ServerMetric).where(ServerMetric.server_id == srv.id)
        .order_by(desc(ServerMetric.recorded_at)).limit(1)
    )).scalar_one_or_none()
    scan = (await db.execute(
        select(SecurityScan).where(SecurityScan.server_id == srv.id)
        .order_by(desc(SecurityScan.created_at)).limit(1)
    )).scalar_one_or_none()
    return {
        **_server(srv),
        "metrics": _metric(latest),
        "security": {"grade": scan.grade, "score": scan.score,
                     "scanned_at": scan.created_at.isoformat()} if scan else None,
    }


@router.get("/servers/{server}/metrics")
async def server_metrics(
    server: str, db: DBDep, caller: Caller,
    hours: int = Query(default=1, ge=1, le=168),
) -> dict:
    """Recent metric history — for graphing in the customer's own dashboard."""
    srv = await _resolve(db, caller, server)
    since = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    rows = (await db.execute(
        select(ServerMetric).where(
            ServerMetric.server_id == srv.id, ServerMetric.recorded_at >= since
        ).order_by(ServerMetric.recorded_at)
    )).scalars().all()
    return {"server": srv.name, "hours": hours,
            "samples": [_metric(m) for m in rows], "count": len(rows)}


# ── Fleet health ─────────────────────────────────────────────────────────────

@router.get("/fleet/health")
async def fleet_health(db: DBDep, caller: Caller) -> dict:
    """The same scored fleet report the dashboard shows. Deterministic, no AI cost."""
    servers = await team_service.accessible_servers(db, caller.user)
    analyzed = await fleet_service.analyze_fleet(db, servers)
    return {"servers": [fleet_service.to_dict(h) for h in analyzed], "count": len(analyzed)}


# ── Incidents ────────────────────────────────────────────────────────────────

@router.get("/incidents")
async def list_incidents(
    db: DBDep, caller: Caller,
    status: str | None = Query(default="active"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    query = select(Incident).where(Incident.user_id == caller.user.id)
    if status == "active":
        query = query.where(Incident.status.in_([STATUS_OPEN, STATUS_ACKNOWLEDGED]))
    elif status:
        query = query.where(Incident.status == status)
    rows = (await db.execute(
        query.order_by(desc(Incident.created_at)).limit(limit)
    )).scalars().all()
    return {"incidents": [incident_service.serialize(r) for r in rows], "count": len(rows)}


@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge(incident_id: str, db: DBDep, caller: Writer) -> dict:
    """Acknowledge from the customer's own tooling — their pager integration, their rota."""
    try:
        iid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident = (await db.execute(
        select(Incident).where(Incident.id == iid, Incident.user_id == caller.user.id)
    )).scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    await incident_service.acknowledge(db, incident, by=f"API key '{caller.key.name}'")
    return incident_service.serialize(incident)


# ── Uptime ───────────────────────────────────────────────────────────────────

@router.get("/uptime")
async def uptime(db: DBDep, caller: Caller) -> dict:
    rows = (await db.execute(
        select(UptimeMonitor).where(UptimeMonitor.user_id == caller.user.id)
        .order_by(UptimeMonitor.name)
    )).scalars().all()
    return {"monitors": [{
        "id": str(m.id), "name": m.name, "url": m.url,
        "status": m.current_status, "last_checked": m.last_checked.isoformat() if m.last_checked else None,
        "response_ms": m.last_response_ms, "error": m.last_error,
        "certificate": {"days_left": m.cert_days_left, "state": m.cert_state,
                        "issuer": m.cert_issuer} if m.cert_state else None,
    } for m in rows], "count": len(rows)}


# ── Playbooks: the headline automation case ──────────────────────────────────

@router.get("/playbooks")
async def list_playbooks(db: DBDep, caller: Caller,
                         category: str | None = Query(default=None)) -> dict:
    query = select(Playbook).where(Playbook.is_official.is_(True))
    if category:
        query = query.where(Playbook.category == category)
    rows = (await db.execute(query.order_by(Playbook.title))).scalars().all()
    return {"playbooks": [{
        "slug": p.slug, "title": p.title, "description": p.description,
        "category": p.category, "os_family": p.os_family,
        "variables": p.variables or [],
        "estimated_seconds": p.est_runtime_sec,
    } for p in rows], "count": len(rows)}


class RunPlaybookBody(BaseModel):
    playbook: str = Field(min_length=1, max_length=255)
    variables: dict[str, str] = Field(default_factory=dict)


@router.post("/servers/{server}/playbooks/run")
@limiter.limit("30/minute")
async def run_playbook(
    server: str, body: RunPlaybookBody, request: Request, db: DBDep, caller: Writer,
) -> dict:
    """Run a playbook and return a ``run_id`` immediately.

    Start-and-poll rather than wait: a playbook can take minutes, and a request that hangs
    that long dies in whatever proxy sits in front of the caller. This is the same shape the
    MCP tool uses, for the same reason.
    """
    srv = await _executable(db, caller, server)
    playbook = (await db.execute(
        select(Playbook).where(Playbook.slug == body.playbook, Playbook.is_official.is_(True))
    )).scalar_one_or_none()
    if playbook is None:
        raise HTTPException(status_code=404,
                            detail=f"No playbook '{body.playbook}'. GET /api/v1/playbooks for slugs.")

    supported = playbook_service.supported_os_for(playbook)
    if not playbook_service.os_matches(srv, supported):
        raise HTTPException(
            status_code=422,
            detail=f"'{body.playbook}' needs {', '.join(supported or []) or 'a different OS'} — "
                   f"{srv.name} is {srv.os_type or 'unknown'}.",
        )
    raw = (playbook.script_powershell
           if (srv.connection_type == "winrm" and playbook.script_powershell)
           else playbook.script_bash)
    if not raw:
        raise HTTPException(status_code=422,
                            detail=f"'{body.playbook}' has no script for {srv.name}'s OS.")

    run = PlaybookRun(
        server_id=srv.id, user_id=caller.user.id, playbook_id=playbook.id,
        variables_used=secret_vars.encrypt_variables(body.variables), status="running",
    )
    db.add(run)
    await db.flush()
    run_id, srv_id, srv_name = str(run.id), str(srv.id), srv.name
    script = playbook_service.substitute_variables(raw, body.variables)
    # Commit BEFORE enqueuing, so the worker can always find the run it is given.
    await db.commit()

    run_playbook_task.delay(run_id, srv_id, script)
    logger.info("API key '%s' started playbook %s on %s", caller.key.name, body.playbook, srv_name)
    return {"run_id": run_id, "server": srv_name, "playbook": body.playbook,
            "status": "running",
            "poll": f"/api/v1/playbook-runs/{run_id}"}


@router.get("/playbook-runs/{run_id}")
async def playbook_run(run_id: str, db: DBDep, caller: Caller) -> dict:
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not found")
    run = (await db.execute(
        select(PlaybookRun).where(PlaybookRun.id == rid, PlaybookRun.user_id == caller.user.id)
    )).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run(run)


# ── Scans ────────────────────────────────────────────────────────────────────

@router.post("/servers/{server}/security-scan")
@limiter.limit("10/minute")
async def security_scan(server: str, request: Request, db: DBDep, caller: Writer) -> dict:
    """Run the read-only security audit and return its result.

    Write-scoped even though the scan changes nothing, because it opens an SSH session and
    does real work on the customer's server — a read-only key should not be able to cause
    load on a production box.
    """
    from app.services import security_service

    srv = await _executable(db, caller, server)
    try:
        result = await security_service.run_scan(srv)
    except Exception as exc:  # noqa: BLE001
        logger.warning("API security scan failed for %s: %s", srv.name, exc)
        raise HTTPException(status_code=502, detail=f"Could not scan {srv.name}: {exc}")

    # Persist it like the browser does, so an API-triggered scan appears in the same
    # history and feeds the same fleet score — an invisible scan would be a second,
    # divergent source of truth.
    counts = result.get("counts", {})
    scan = SecurityScan(
        server_id=srv.id, user_id=caller.user.id,
        score=result["score"], grade=result["grade"], status=result["status"],
        error=result.get("error"), duration_ms=result.get("duration_ms"),
        critical_count=counts.get("critical", 0), high_count=counts.get("high", 0),
        medium_count=counts.get("medium", 0), low_count=counts.get("low", 0),
        # A JSON string, matching the column type the browser route writes.
        findings=json.dumps(result.get("findings", [])),
    )
    db.add(scan)
    await db.commit()
    return {"server": srv.name, "score": result["score"], "grade": result["grade"],
            "status": result["status"], "counts": counts,
            "findings": result.get("findings", [])}


# ── Escalation policies (read-only) ──────────────────────────────────────────

@router.get("/escalation/policies")
async def policies(db: DBDep, caller: Caller) -> dict:
    """Read-only on purpose: who gets woken at 3am is a decision for a person in a browser,
    not something a script should be able to quietly rewrite."""
    from app.models.escalation import EscalationPolicy

    rows = (await db.execute(
        select(EscalationPolicy).where(EscalationPolicy.user_id == caller.user.id)
    )).scalars().all()
    out = []
    for p in rows:
        steps = await incident_service.steps_for(db, p)
        out.append({
            "id": str(p.id), "name": p.name, "is_default": p.is_default,
            "is_active": p.is_active, "min_severity": p.min_severity,
            "summary": escalation_service.describe(steps, p.repeat_minutes, p.max_repeats),
        })
    return {"policies": out, "count": len(out)}
