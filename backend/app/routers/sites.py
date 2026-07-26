"""Sites — every website across the fleet, in one searchable place.

The point of this router is **joining**, not collecting. Uptime, certificate expiry and the
security grade already exist; what was missing was one list where a domain is the thing you
look up, rather than a server. When a client rings about ``acmeshop.com``, nobody should have
to remember which of forty servers it lives on.

Read-only apart from the scan, which is itself a read-only probe on the server. There is
deliberately no create, no delete and no edit: making a site is a control panel's job — see
[POSITIONING-CATEGORY.md](../../../docs/POSITIONING-CATEGORY.md).
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.server import Server
from app.models.site import Site
from app.models.uptime import UptimeMonitor
from app.models.user import User
from app.services import site_service, team_service

router = APIRouter(prefix="/api", tags=["sites"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _monitor_key(url: str) -> str:
    """The hostname a monitored URL points at, lowercased.

    Matching a site to its monitor on hostname is what lets the page show up/down and
    certificate expiry without storing either on the site row — one fact, one owner.
    """
    from urllib.parse import urlparse

    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


async def _uptime_by_host(db: AsyncSession, user_id) -> dict[str, dict]:
    """Every monitor of this user's, keyed by hostname."""
    rows = (await db.execute(
        select(UptimeMonitor).where(UptimeMonitor.user_id == user_id)
    )).scalars().all()
    out: dict[str, dict] = {}
    for monitor in rows:
        host = _monitor_key(monitor.url)
        if not host:
            continue
        out[host] = {
            "monitor_id": str(monitor.id),
            "status": monitor.current_status,
            "last_checked": monitor.last_checked.isoformat() if monitor.last_checked else None,
            "response_ms": monitor.last_response_ms,
            "error": monitor.last_error,
            "cert_days_left": monitor.cert_days_left,
            "cert_state": monitor.cert_state,
        }
    return out


@router.get("/sites")
async def list_sites(
    db: DBDep, current_user: CurrentUser,
    q: str | None = Query(default=None, max_length=200),
    server_id: str | None = Query(default=None),
    include_gone: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict:
    """Every site across every server the caller can reach.

    Searching matches the domain and its aliases, because a client will name whichever one they
    were given. Team-scoped through ``accessible_servers`` — the same Rule 7 path everything
    else uses — so a member sees sites on exactly the servers they can see.
    """
    servers = await team_service.accessible_servers(db, current_user)
    names = {s.id: s.name for s in servers}
    if not servers:
        return {"sites": [], "count": 0, "servers_scanned": 0, "never_scanned": []}

    query = select(Site).where(Site.server_id.in_(list(names)))
    if not include_gone:
        query = query.where(Site.is_present.is_(True))
    if server_id:
        try:
            query = query.where(Site.server_id == uuid.UUID(server_id))
        except ValueError:
            raise HTTPException(status_code=422, detail="That server id isn't valid.")
    if q:
        needle = f"%{q.strip().lower()}%"
        # Alias match uses array_to_string so one LIKE covers the primary domain and every
        # alias — a client quotes whichever name they were given.
        query = query.where(
            func.lower(Site.domain).like(needle)
            | func.lower(func.array_to_string(Site.aliases, ",")).like(needle)
        )

    rows = (await db.execute(query.order_by(Site.domain).limit(limit))).scalars().all()
    uptime = await _uptime_by_host(db, current_user.id)

    sites = [
        site_service.serialize(
            row,
            server_name=names.get(row.server_id),
            uptime=uptime.get(row.domain.lower()),
        )
        for row in rows
    ]

    # Which servers have never been scanned, so the page can say "scan these" rather than
    # implying the fleet genuinely has no websites. Only SSH servers can be scanned at all.
    scanned_ids = {row[0] for row in (await db.execute(
        select(Site.server_id).where(Site.server_id.in_(list(names))).distinct()
    )).all()}
    never = [
        {"id": str(s.id), "name": s.name}
        for s in servers
        if s.id not in scanned_ids and s.connection_type == "ssh"
    ]

    return {
        "sites": sites,
        "count": len(sites),
        "servers_scanned": len(scanned_ids),
        "never_scanned": never,
    }


@router.post("/servers/{server_id}/sites/scan")
async def scan_server(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Look at one server and record the websites it serves.

    Read-only on the server: it reads web-server config and looks for application markers. It
    never reads application config contents, so a customer's database password cannot end up in
    their site inventory.
    """
    server = await resolve_server(server_id, current_user, db)
    found, truncated, error = await site_service.discover(server)
    if error:
        raise HTTPException(status_code=502, detail=error)

    summary = await site_service.sync(db, server, found)
    logger.info("Site scan on %s: %s", server.name, summary)
    return {
        "server": server.name,
        **summary,
        "truncated": truncated,
        "note": (f"Only the first {site_service.MAX_SITES} sites were recorded — this server "
                 "has more." if truncated else None),
    }


@router.get("/servers/{server_id}/sites")
async def server_sites(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """The sites on one server — for the server's own detail page."""
    server = await resolve_server(server_id, current_user, db)
    rows = (await db.execute(
        select(Site).where(Site.server_id == server.id, Site.is_present.is_(True))
        .order_by(Site.domain)
    )).scalars().all()
    uptime = await _uptime_by_host(db, current_user.id)
    return {
        "sites": [
            site_service.serialize(r, server_name=server.name,
                                   uptime=uptime.get(r.domain.lower()))
            for r in rows
        ],
        "count": len(rows),
    }
