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
from pydantic import BaseModel, Field
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


async def _watch_new(db: AsyncSession, user, server) -> int:
    """Create uptime monitors for this server's sites that have none yet."""
    sites = (await db.execute(
        select(Site).where(Site.server_id == server.id, Site.user_id == user.id,
                           Site.is_present.is_(True)))).scalars().all()
    known = {_monitor_key(m.url) for m in (await db.execute(
        select(UptimeMonitor).where(UptimeMonitor.user_id == user.id))).scalars().all()}
    made = 0
    for site in sites:
        if site.domain in known:
            continue
        db.add(UptimeMonitor(user_id=user.id, server_id=site.server_id,
                             **site_service.monitor_defaults(site.domain)))
        known.add(site.domain)
        made += 1
    if made:
        await db.commit()
    return made


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

    # Start watching what we just found. Discovery without monitoring is a phone book:
    # the customer would have to create a monitor for every site by hand, so nobody ever
    # would, and the up/down column that makes this page worth opening stays empty. New
    # sites only — a site whose monitor was deliberately deleted is not resurrected.
    watching = await _watch_new(db, current_user, server)
    logger.info("Site scan on %s: %s (now watching %d more)", server.name, summary, watching)
    return {
        "server": server.name,
        **summary,
        "watching": watching,
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


# ── the customer's own list, not just what we discovered ─────────────────────
class AddSiteBody(BaseModel):
    domain: str = Field(max_length=300)
    server_id: str | None = None      # optional — a site can live somewhere we do not manage
    watch: bool = True


class WatchBody(BaseModel):
    """Which sites to start checking. Empty means every site that is not watched yet."""
    site_ids: list[str] = Field(default_factory=list, max_length=500)


async def _make_monitor(db: AsyncSession, user, domain: str, server_id=None) -> UptimeMonitor:
    monitor = UptimeMonitor(user_id=user.id, server_id=server_id,
                            **site_service.monitor_defaults(domain))
    db.add(monitor)
    return monitor


@router.post("/sites", status_code=201)
async def add_site(body: AddSiteBody, db: DBDep, current_user: CurrentUser) -> dict:
    """Track a website the customer already owns.

    The point of the whole feature: a competitor can only show sites on servers it built.
    An agency's most important site is often on a host nobody manages — a client's old
    cPanel, someone else's box. This is the only way that site gets watched.
    """
    try:
        domain = site_service.clean_domain(body.domain)
    except site_service.InvalidDomain as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    server = None
    if body.server_id:
        server = await resolve_server(body.server_id, current_user, db)

    existing = (await db.execute(
        select(Site).where(Site.user_id == current_user.id, Site.domain == domain)
    )).scalar_one_or_none()
    if existing:
        # Not an error worth stopping for: they wanted it watched, so make sure it is.
        if not existing.is_present:
            existing.is_present = True
        site = existing
    else:
        site = Site(user_id=current_user.id, server_id=server.id if server else None,
                    domain=domain, aliases=[], source="added", app_type="unknown")
        db.add(site)

    watched = False
    if body.watch:
        hosts = {_monitor_key(m.url) for m in (await db.execute(
            select(UptimeMonitor).where(UptimeMonitor.user_id == current_user.id)
        )).scalars().all()}
        if domain not in hosts:
            await _make_monitor(db, current_user, domain, site.server_id)
            watched = True

    await db.commit()
    await db.refresh(site)
    return {"site": site_service.serialize(site,
                                           server_name=server.name if server else None),
            "watching": watched,
            "message": (f"{domain} is on your list"
                        + (" and we are checking it now." if watched else "."))}


@router.post("/sites/watch")
async def watch_sites(body: WatchBody, db: DBDep, current_user: CurrentUser) -> dict:
    """Start checking sites we already know about.

    Discovery finds 77 sites; without this, a customer would have to create 77 monitors by
    hand, so nobody would — and the up/down column that makes the page worth opening would
    stay empty forever.
    """
    q = select(Site).where(Site.user_id == current_user.id, Site.is_present.is_(True))
    if body.site_ids:
        try:
            q = q.where(Site.id.in_([uuid.UUID(x) for x in body.site_ids]))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Bad site id.") from exc
    sites = (await db.execute(q)).scalars().all()

    already = {_monitor_key(m.url) for m in (await db.execute(
        select(UptimeMonitor).where(UptimeMonitor.user_id == current_user.id)
    )).scalars().all()}

    added = 0
    for site in sites:
        if site.domain in already:
            continue
        await _make_monitor(db, current_user, site.domain, site.server_id)
        already.add(site.domain)
        added += 1
    await db.commit()
    return {"watching": added,
            "message": (f"Now checking {added} site{'' if added == 1 else 's'} every five "
                        "minutes. You will be told if one stops loading."
                        if added else "Every site is already being checked.")}


@router.delete("/sites/{site_id}", status_code=204)
async def forget_site(site_id: str, db: DBDep, current_user: CurrentUser) -> None:
    """Stop tracking a site. Its monitor is left alone — it may be watched deliberately."""
    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")
    await db.delete(site)
    await db.commit()
