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

import asyncio
import logging
import secrets
import shlex
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import audit_service, ssl_service
from app.workers.playbook_tasks import run_playbook_task
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.server import Server
from app.models.mail_health import MailHealthRecord
from app.models.site import Site
from app.models.uptime import UptimeMonitor
from app.models.user import User
from app.services import (playbook_service, site_cron_service, site_service,
                          team_service, uptime_service)

router = APIRouter(prefix="/api", tags=["sites"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


#: One matcher, so the page's lookup and the rule that pauses a check agree on what
#: "this site's monitor" means.
_monitor_key = site_service.monitor_host


async def _ever_up(db: AsyncSession, monitor_ids: list) -> set:
    """Which of these monitors has ever seen the site answer.

    One grouped query, the same shape the uptime screen already uses. It is what separates
    "this domain was never pointed here" from "it was working and has stopped" — the same
    words from the checker, and two completely different situations.
    """
    from app.models.uptime import UptimeCheck

    if not monitor_ids:
        return set()
    rows = (await db.execute(
        select(UptimeCheck.monitor_id)
        .where(UptimeCheck.monitor_id.in_(monitor_ids), UptimeCheck.status == "up")
        .group_by(UptimeCheck.monitor_id)
    )).all()
    return {r[0] for r in rows}


async def _uptime_by_host(db: AsyncSession, user_id) -> dict[str, dict]:
    """Every monitor of this user's, keyed by hostname."""
    rows = (await db.execute(
        select(UptimeMonitor).where(UptimeMonitor.user_id == user_id)
    )).scalars().all()
    seen_up = await _ever_up(db, [m.id for m in rows])
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
            # Classified here rather than by matching the sentence in the browser: the
            # words live in one place, and a screen that has to recognise them by copying
            # them is a screen that stops recognising them the day they are reworded.
            "unresolved": (monitor.last_error or "") == uptime_service.DNS_FAILURE,
            "ever_up": monitor.id in seen_up,
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
    # A site whose installer FAILED must stop claiming to be building. Nothing else runs
    # this: the reconciler existed, worked and was tested, and had no callers at all — so a
    # failed install showed "Setting up…" indefinitely. It is cheap (one join) and belongs
    # wherever somebody is about to be told what state a site is in.
    await site_service.reconcile_installs(db, current_user.id)

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
    mail = await _mail_by_domain(db, current_user.id)

    sites = []
    for row in rows:
        item = site_service.serialize(
            row,
            server_name=names.get(row.server_id),
            uptime=uptime.get(row.domain.lower()),
        )
        # Up, secure and deliverable in one row. Joined here rather than fetched separately
        # so the page cannot show a site whose three answers came from three moments.
        item["mail"] = mail.get(row.domain.lower())
        sites.append(item)

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


async def _mail_by_domain(db: AsyncSession, user_id) -> dict[str, dict]:
    """The last mail-health result for every domain this customer watches."""
    rows = (await db.execute(
        select(MailHealthRecord).where(MailHealthRecord.user_id == user_id)
    )).scalars().all()
    return {
        r.domain.lower(): {
            "id": str(r.id), "verdict": r.verdict, "score": r.score,
            "summary": r.summary, "findings": r.findings or [],
            "checked": r.last_checked.isoformat() if r.last_checked else None,
        }
        for r in rows
    }


async def _watch_new(db: AsyncSession, user, server) -> int:
    """Create uptime monitors for this server's sites that have none yet."""
    # Only a site that is actually there. This filtered on `is_present` alone, and a site
    # whose install failed deliberately keeps that flag (it never arrived, so it cannot
    # have vanished) — so we were creating an uptime check for a site that was never built,
    # which then reported it down forever with no way to ever recover.
    sites = [s for s in (await db.execute(
        select(Site).where(Site.server_id == server.id, Site.user_id == user.id,
                           Site.is_present.is_(True)))).scalars().all()
        if site_service.should_watch(s.status, s.is_present)]
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


@router.get("/site-types")
async def site_types(db: DBDep, current_user: CurrentUser) -> dict:
    """What can be installed on a server, and what each one needs to know.

    Served from the backend rather than listed again in the browser, so adding a type is
    one entry plus a playbook — which is the whole promise of the catalogue. A type whose
    playbook is missing from this deployment simply does not appear.
    """
    from app.models.playbook import Playbook

    rows = (await db.execute(
        select(Playbook).where(Playbook.is_official == True)  # noqa: E712
    )).scalars().all()
    by_slug = {p.slug: p for p in rows}
    items = site_service.catalogue(by_slug)
    return {
        "groups": [{"id": g, "label": label, "blurb": blurb}
                   for g, label, blurb in site_service.SITE_GROUPS],
        "types": items,
    }


class CreateSiteIn(BaseModel):
    """What to put on this server."""
    domain: str
    site_type: str
    #: Extra answers the chosen installer needs — a database name, an app's port. Kept
    #: open-ended because each installer asks for different things and the catalogue is
    #: meant to grow by adding a playbook, not by editing this schema.
    variables: dict[str, str] = {}


@router.post("/servers/{server_id}/sites", status_code=201)
async def create_site(server_id: str, body: CreateSiteIn, db: DBDep,
                      current_user: CurrentUser) -> dict:
    """Create a site on this server, and start the installer that builds it.

    Returns immediately with the site recorded as `installing`. The install runs in the
    background — the row carries `install_run_id` so progress can be followed, and a failure
    is written back onto the site rather than left in a log nobody reads.

    A site becomes `live` only when a scan SEES it on the server. An installer exiting 0 is
    not proof, which is the same rule the mission verification gate follows.
    """
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=400,
            detail="Sites can only be created on a Linux server we reach over SSH.")

    try:
        site, run_id, script = await site_service.create(
            db, server, current_user,
            domain=body.domain, site_type=body.site_type, variables=body.variables)
    except (site_service.SiteError, playbook_service.UnresolvedVariables) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Enqueued AFTER the commit inside create(), so the worker can always find the run.
    run_playbook_task.delay(run_id, str(server.id), script)
    await audit_service.audit(db, current_user, "site.created",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "type": body.site_type})
    return {**site_service.serialize(site, server_name=server.name), "run_id": run_id}


@router.get("/servers/{server_id}/sites")
async def server_sites(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """The sites on one server — for the server's own detail page."""
    await site_service.reconcile_installs(db, current_user.id)
    server = await resolve_server(server_id, current_user, db)
    rows = (await db.execute(
        select(Site).where(Site.server_id == server.id, Site.is_present.is_(True))
        .order_by(Site.domain)
    )).scalars().all()
    uptime = await _uptime_by_host(db, current_user.id)
    # A server whose identity changed or whose credentials stopped working cannot be looked
    # at, so every row below is the last thing we saw rather than the current truth. Saying
    # so is the difference between a stale list and a lying one — without it the page showed
    # four sites from a server that had been wiped, each with a confident-sounding reason
    # for being down.
    unreachable = server.status if server.status in ("host_changed", "auth_failed",
                                                     "offline") else None
    return {
        # Null when the server is reachable. Otherwise the reason, so the page can say the
        # list is the last thing we saw rather than presenting it as current.
        "stale_because": unreachable,
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


class InstallIn(BaseModel):
    """What to put on a site that already exists."""
    site_type: str
    variables: dict[str, str] = {}
    #: Delete what is on the site first. Defaults to off, so a client that has never heard
    #: of this field cannot destroy a site by omission.
    replace: bool = False
    #: The domain, typed by the person doing it. Required only for a replace, and required
    #: for the same reason it is on cloud destroy: the loss here is rarely "I meant not
    #: to", it is "I did it to the wrong one".
    confirm: str | None = None


@router.get("/sites/{site_id}")
async def get_site(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """One site, with the server it lives on.

    Its own page reads this rather than picking a row out of the list, so the page works
    when it is opened directly from a link or a bookmark — which is how someone returns to
    a site they were told about.
    """
    await site_service.reconcile_installs(db, current_user.id)
    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")

    server = await resolve_server(str(site.server_id), current_user, db)
    return {
        **site_service.serialize(site, server_name=server.name),
        "server": {
            "id": str(server.id),
            "name": server.name,
            "connection_type": server.connection_type,
            "panel_type": server.panel_type,
        },
    }


@router.get("/sites/{site_id}/details")
async def site_details(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Where this site's files are, who owns them, which PHP it runs, how big it is.

    Read from the server every time rather than stored. All of it changes without us —
    somebody uploads, somebody switches PHP, an update lands — and a stored path shown for
    a site that has since moved is worse than no path, because someone will `cd` to it.

    Deliberately its own request, not part of the site page's first load: it is an SSH
    round trip with a `du` in it, and the page should draw immediately and fill this in.
    """
    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")

    server = await resolve_server(str(site.server_id), current_user, db)
    if server.connection_type != "ssh":
        # Nothing dishonest to report — we have no way to look inside this kind of server.
        return {"reachable": False}
    return await site_service.probe_details(server, site)


@router.post("/sites/{site_id}/install")
async def install_on_site(site_id: str, body: InstallIn, db: DBDep,
                          current_user: CurrentUser) -> dict:
    """Put an application onto a site that already exists.

    The second half of making a site: the domain is added first, then what runs on it is
    chosen here. The installer replaces the empty site's configuration — and can only do
    that, because the shared guard requires our own marker in the existing config and
    refuses a folder with anything in it.
    """
    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")

    server = await resolve_server(str(site.server_id), current_user, db, need_execute=True)
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=400,
            detail="Applications can only be installed on a Linux server we reach over SSH.")

    # Checked here rather than inside the service, because it is a fact about the person at
    # the keyboard rather than about the site. Compared against the domain the SERVER holds,
    # so a client that sent the wrong site's id cannot satisfy its own confirmation.
    if body.replace and (body.confirm or "").strip().lower() != site.domain.lower():
        raise HTTPException(
            status_code=422,
            detail=f"To replace what is on this site, type its domain exactly: {site.domain}")

    try:
        site, run_id, script = await site_service.install(
            db, server, current_user, site,
            site_type=body.site_type, variables=body.variables, replace=body.replace)
    except (site_service.SiteError, playbook_service.UnresolvedVariables) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Enqueued after the commit inside install(), so the worker can always find the run.
    run_playbook_task.delay(run_id, str(server.id), script)
    await audit_service.audit(db, current_user, "site.installed",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "type": body.site_type,
                                    "replaced": body.replace})
    return {**site_service.serialize(site, server_name=server.name), "run_id": run_id}


@router.get("/sites/{site_id}/ssl-readiness")
async def ssl_readiness(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Can HTTPS be turned on for this site yet?

    Answered before anything is started, because the one requirement is outside our
    control: the domain has to point at this server already, since the authority proves
    ownership by reaching it through that name. A domain bought an hour ago does not, and
    that is normal — so the answer carries the record to create rather than an error.
    """
    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")
    server = await resolve_server(str(site.server_id), current_user, db)

    check = await ssl_service.check_dns(site.domain, server.host)
    return {
        **check,
        "has_ssl": bool(site.has_ssl),
        "message": None if check["ready"] else ssl_service.dns_message(site.domain, check),
    }


@router.post("/sites/{site_id}/ssl")
async def turn_on_ssl(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Get a certificate for this site and serve it over HTTPS.

    Refuses up front when the domain does not point here yet. Let's Encrypt allows five
    certificates per domain per week, and a failed attempt spends one of them — so an
    attempt that cannot possibly succeed is worse than a refusal.
    """
    from app.models.playbook import Playbook, PlaybookRun
    from app.services import playbook_service
    from app.services.secret_vars import encrypt_variables

    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")

    server = await resolve_server(str(site.server_id), current_user, db, need_execute=True)
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=400,
            detail="HTTPS is set up over SSH on a Linux server. A hosting panel issues its "
                   "own certificates — use its own screen for that.")

    check = await ssl_service.check_dns(site.domain, server.host)
    if not check["ready"]:
        raise HTTPException(status_code=422,
                            detail=ssl_service.dns_message(site.domain, check))

    pb = (await db.execute(
        select(Playbook).where(Playbook.slug == "site-ssl",
                               Playbook.is_official == True)  # noqa: E712
    )).scalar_one_or_none()
    if pb is None or not pb.script_bash:
        raise HTTPException(status_code=422,
                            detail="The HTTPS installer is not available on this ServerAlly.")

    variables = {"DOMAIN": site.domain, "EMAIL": current_user.email}
    script = playbook_service.substitute_variables(pb.script_bash, variables)

    run = PlaybookRun(server_id=server.id, user_id=current_user.id, playbook_id=pb.id,
                      variables_used=encrypt_variables(variables), status="running")
    db.add(run)
    await db.commit()
    await db.refresh(run)

    run_playbook_task.delay(str(run.id), str(server.id), script)
    await audit_service.audit(db, current_user, "site.ssl_requested",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain})
    return {"run_id": str(run.id), "domain": site.domain}


class RemoveIn(BaseModel):
    """Typed back, because there is no undo anywhere in this system."""
    confirm_domain: str
    drop_database: bool = False


@router.post("/sites/{site_id}/remove")
async def remove_site(site_id: str, body: RemoveIn, db: DBDep,
                      current_user: CurrentUser) -> dict:
    """Take a site off the server: files, configuration, certificate and — if asked — its
    database.

    Only a site ServerAlly built. One that was already on the server when we found it has a
    layout we did not choose, and deleting its folder on a guess is how something
    irreplaceable disappears; those can be untracked instead, which changes nothing on the
    server. The script enforces this too, by requiring our own marker in the configuration.

    The typed domain has to match, for the same reason the database drop asks: the loss is
    rarely "I meant not to", it is "I deleted the one next to it".
    """
    from app.models.playbook import Playbook, PlaybookRun
    from app.services import playbook_service
    from app.services.secret_vars import encrypt_variables

    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")

    if (body.confirm_domain or "").strip() != site.domain:
        raise HTTPException(
            status_code=422,
            detail=f"Type the domain exactly — {site.domain} — to confirm. Removing a site "
                   f"cannot be undone, and there is no copy of it here.")

    if site.source != "manual":
        raise HTTPException(
            status_code=422,
            detail="This site was already on the server when ServerAlly found it, so it is "
                   "not removed from here — its files are laid out in a way we did not "
                   "choose. You can stop tracking it instead, which changes nothing on the "
                   "server.")

    server = await resolve_server(str(site.server_id), current_user, db, need_execute=True)
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=400,
            detail="Sites are removed over SSH on a Linux server. A hosting panel removes "
                   "its own — use its own screen for that.")

    pb = (await db.execute(
        select(Playbook).where(Playbook.slug == "site-remove",
                               Playbook.is_official == True)  # noqa: E712
    )).scalar_one_or_none()
    if pb is None or not pb.script_bash:
        raise HTTPException(status_code=422,
                            detail="The remove-site tool is not available on this ServerAlly.")

    variables = {"DOMAIN": site.domain, "DROP_DB": "yes" if body.drop_database else "no"}
    script = playbook_service.substitute_variables(pb.script_bash, variables)

    run = PlaybookRun(server_id=server.id, user_id=current_user.id, playbook_id=pb.id,
                      variables_used=encrypt_variables(variables), status="running")
    db.add(run)
    # The row goes when the server confirms it is gone, not before: a site removed from the
    # list while it is still being served is a site nobody knows about any more.
    #
    # Its own status, and pointed at THIS run. It used to reuse "installing" and leave
    # install_run_id on the original install, so the reconciler judged the removal by a run
    # that had nothing to do with it and put the site straight back to "Setup failed" — the
    # site was gone from the server and still on the screen.
    site.status = "removing"
    site.install_error = None
    await db.commit()
    await db.refresh(run)
    site.install_run_id = run.id
    await db.commit()

    run_playbook_task.delay(str(run.id), str(server.id), script)
    await audit_service.audit(db, current_user, "site.removed",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain,
                                    "database": body.drop_database})
    return {"run_id": str(run.id), "domain": site.domain}


@router.get("/sites/{site_id}/logs")
async def site_logs(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """This site's own log files.

    The server-wide list answers "what is happening on this machine", which on a machine
    with fifteen sites is the wrong question.
    """
    from app.services import log_service

    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")
    server = await resolve_server(str(site.server_id), current_user, db)
    if server.connection_type != "ssh":
        return {"logs": [], "reachable": False}

    logs = await log_service.discover_for_site(server, site.domain, site.doc_root)
    return {"logs": logs, "reachable": True, "server_id": str(server.id)}


class AppActionIn(BaseModel):
    """One named operation, never a command the caller composes."""
    action: str = Field(max_length=40)
    target: str = Field(default="", max_length=100)


async def _site_and_server(site_id: str, current_user, db, *, need_execute: bool = False):
    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")
    server = await resolve_server(str(site.server_id), current_user, db,
                                  need_execute=need_execute)
    return site, server


@router.get("/sites/{site_id}/app")
async def site_app(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """The application running on this site, and everything its own screen shows.

    Dispatched through ``app_registry``, so a site running something we have no tools for
    answers ``app: null`` and shows no section at all — rather than an empty one implying
    the feature exists and is merely switched off.
    """
    from app.services import (app_registry, laravel_service, php_site_service,
                              webapp_service, wordpress_service)

    site, server = await _site_and_server(site_id, current_user, db)
    spec = app_registry.app_for(site.app_type)
    if spec is None:
        return {"app": None}
    if server.connection_type != "ssh":
        return {"app": spec.id, "label": spec.label, "ok": False,
                "reason": f"{spec.label} is managed over SSH, and this server is not "
                          f"reached that way."}

    root = site.doc_root or ""
    if spec.id == "wordpress":
        data = await wordpress_service.read(server, root)
    elif spec.id == "laravel":
        data = await laravel_service.read(server, root)
    elif spec.id == "php":
        data = await php_site_service.read(server, root, site.domain)
    elif spec.id == "app":
        # Keyed off the DOMAIN, not the folder: the program is a systemd unit named after
        # the site, and it may run from anywhere.
        data = await webapp_service.read(server, site.domain)
    else:
        data = {"ok": False, "reason": f"{spec.label} has no screen yet."}
    return {"app": spec.id, "label": spec.label, **data}


@router.post("/sites/{site_id}/app/action")
async def site_app_action(site_id: str, body: AppActionIn, db: DBDep,
                          current_user: CurrentUser) -> dict:
    """Run one named action on this site's application. Needs execute permission (Rule 7)."""
    from app.services import (app_registry, laravel_service, webapp_service,
                              wordpress_service)

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    spec = app_registry.app_for(site.app_type)
    if spec is None or server.connection_type != "ssh":
        raise HTTPException(422, "There is nothing here we can manage.")

    root = site.doc_root or ""
    try:
        if spec.id == "wordpress":
            result = await wordpress_service.act(server, root, body.action, body.target)
        elif spec.id == "laravel":
            result = await laravel_service.act(server, root, body.action)
        elif spec.id == "app":
            result = await webapp_service.act(server, site.domain, body.action)
        else:
            # PHP is read-only by design: a pool limit is shared by every site using it, so
            # changing one belongs to the server's PHP screen, not to one site's page.
            raise HTTPException(422, f"There is nothing to change on a {spec.label} site "
                                     f"from here.")
    except (wordpress_service.WordPressError, laravel_service.LaravelError) as exc:
        raise HTTPException(422, str(exc)) from exc

    await audit_service.audit(db, current_user, f"site.{spec.id}.{body.action}",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "target": body.target})
    return result


class SiteDeployIn(BaseModel):
    """Connect a repository to this site."""
    repo: str = Field(max_length=500)
    branch: str = Field(default="main", max_length=120)
    #: Where inside the repository the web server should look. "" is the repo root.
    web_dir: str = Field(default="public", max_length=120)
    build_commands: list[str] = []
    after_commands: list[str] = []
    shared_paths: list[str] = []


@router.get("/sites/{site_id}/deploy")
async def site_deploy(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """This site's deployment, if it has one.

    A site has at most one: "deploy my code here" is one question about one website, and a
    second target pointing at the same folder would be two things fighting over one symlink.
    """
    from app.models.deployment import DeployTarget
    from app.services import deploy_service

    site, server = await _site_and_server(site_id, current_user, db)
    target = (await db.execute(
        select(DeployTarget).where(DeployTarget.site_id == site.id)
    )).scalars().first()

    if target is None:
        # What the form should suggest, worked out from the site rather than typed again.
        try:
            # A panel server keeps releases BESIDE the folder it serves, because that
            # folder is about to become a symlink to them.
            root = (deploy_service.panel_deploy_root(site.domain) if server.panel_type
                    else deploy_service.deploy_root_for(site.doc_root or ""))
        except deploy_service.InvalidDeploy:
            root = ""
        return {
            "target": None,
            "suggested": {
                "path": root,
                # Laravel and Symfony serve from public/; a plain PHP or static repo does
                # not. The site's own type is the best guess available.
                "web_dir": "public" if site.app_type in ("laravel",) else "",
            },
            "can_deploy": server.connection_type == "ssh" and (
                not server.panel_type
                or deploy_service.supports_panel_deploy(server.panel_type)),
        }

    return {
        "target": {
            "id": str(target.id), "repo": target.repo, "branch": target.branch,
            "path": target.path, "web_dir": target.web_dir or "",
            "auto_deploy": target.auto_deploy, "serving": target.serving,
            "current_release": target.current_release,
            "last_status": target.last_status,
            "last_deployed_at": target.last_deployed_at.isoformat()
            if target.last_deployed_at else None,
            "served_from": deploy_service.served_path(target.path, target.web_dir),
        },
        "can_deploy": True,
    }


@router.post("/sites/{site_id}/deploy", status_code=201)
async def connect_site_deploy(site_id: str, body: SiteDeployIn, db: DBDep,
                              current_user: CurrentUser) -> dict:
    """Connect a repository to this site. Does not touch the live site yet.

    Creating this changes nothing a visitor can see: the site keeps serving its current
    files until something has actually been deployed AND the owner asks for it to be used.
    """
    from app.models.deployment import DeployTarget
    from app.services import crypto_service, deploy_service

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    if server.connection_type != "ssh":
        raise HTTPException(400, "Deploying code needs a Linux server we reach over SSH.")
    if server.panel_type and not deploy_service.supports_panel_deploy(server.panel_type):
        # Refused by NAME rather than guessed at. Going live here means replacing the
        # panel's document root with a symlink, and a panel whose layout we do not know is
        # a panel whose customer website we would be replacing.
        raise HTTPException(
            400, f"Deploying is not supported on {server.panel_type} yet — we only know "
                 f"where CyberPanel keeps a site's files. Deploy through the panel instead.")

    existing = (await db.execute(
        select(DeployTarget).where(DeployTarget.site_id == site.id)
    )).scalars().first()
    if existing is not None:
        raise HTTPException(409, "This site already has a repository connected.")

    try:
        # On a panel the vhost is never touched: releases live beside the served folder and
        # that folder becomes a symlink to the current one, so the panel's own default
        # document root is already right and a panel reset has nothing to revert.
        path = (deploy_service.panel_deploy_root(site.domain) if server.panel_type
                else deploy_service.deploy_root_for(site.doc_root or ""))
        target = DeployTarget(
            user_id=current_user.id, server_id=server.id, site_id=site.id,
            name=site.domain,
            repo=deploy_service.valid_repo(body.repo),
            branch=deploy_service.valid_branch(body.branch),
            path=deploy_service.valid_path(path),
            web_dir=deploy_service.valid_web_dir(body.web_dir),
            shared_paths=deploy_service.valid_shared(body.shared_paths),
            build_commands=deploy_service.valid_commands(body.build_commands, label="build"),
            after_commands=deploy_service.valid_commands(body.after_commands,
                                                        label="after-deploy"),
            webhook_secret=crypto_service.encrypt(secrets.token_hex(24)),
        )
    except deploy_service.InvalidDeploy as exc:
        raise HTTPException(422, str(exc)) from exc

    db.add(target)
    await db.commit()
    await db.refresh(target)
    await audit_service.audit(db, current_user, "site.deploy.connected",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "repo": target.repo})
    return {"id": str(target.id), "path": target.path,
            "served_from": deploy_service.served_path(target.path, target.web_dir)}


@router.post("/sites/{site_id}/deploy/serve")
async def serve_site_from_deploy(site_id: str, db: DBDep,
                                 current_user: CurrentUser) -> dict:
    """Point the site's web server at the deployed code.

    The one step here a visitor can see, and the only dangerous one — so it is done exactly
    like the PHP version switch: keep a copy of the config, change the document root, let
    the web server check its own config, reload, then prove the site still serves real
    content. Anything else and the old file goes back.

    It refuses outright when nothing has been deployed yet, which is why the site can sit
    happily on its existing files through as many failed first deploys as it takes.
    """
    from app.models.deployment import DeployTarget
    from app.services import connection_manager, deploy_service, site_service

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    target = (await db.execute(
        select(DeployTarget).where(DeployTarget.site_id == site.id)
    )).scalars().first()
    if target is None:
        raise HTTPException(404, "This site has no repository connected.")

    if server.panel_type:
        # The panel's vhost is never touched. Its OWN document root becomes a symlink to
        # the current release, so the panel's default value is already correct and a panel
        # reset writes the same string that is there — nothing to revert. It also means a
        # reset can never expose the application's `.env`, because the app root is not the
        # served folder any more.
        if not deploy_service.supports_panel_deploy(server.panel_type):
            raise HTTPException(
                400, f"Deploying is not supported on {server.panel_type} yet.")
        # The deploy folder has to be the one we chose for this site. A target whose path
        # was edited elsewhere would otherwise decide which folder gets replaced by a
        # symlink, and that folder is somebody's website.
        expected = deploy_service.panel_deploy_root(site.domain)
        if target.path != expected:
            raise HTTPException(
                422, f"This site's deploy folder is {target.path}, but on a panel server "
                     f"it has to be {expected}. Reconnect the repository to fix it.")
        command = deploy_service.build_panel_link_command(
            deploy_service.panel_link_path(site.domain), target.path,
            target.web_dir, site.domain)
        stdout, stderr, code = await connection_manager.execute(server, command)
        out = (stdout or "") + (stderr or "")
        if code != 0:
            raise HTTPException(422, deploy_service.explain_panel_link(code, out))
        message = [deploy_service.explain_panel_link(0, out)]
    else:
        facts = await site_service.probe_details(server, site)
        config_path = facts.get("config_path")
        if not config_path:
            raise HTTPException(
                422, "We could not find this site's web-server configuration, so nothing "
                     "was changed.")

        command = deploy_service.build_point_command(
            config_path, site.domain, target.path, target.web_dir)
        stdout, stderr, code = await connection_manager.execute(server, command)
        message = (stdout or stderr or "").strip().splitlines()[-1:] or [""]

        if code != 0:
            raise HTTPException(422, deploy_service.POINT_OUTCOMES.get(code, message[0]))

    target.serving = True
    await db.commit()
    await audit_service.audit(db, current_user, "site.deploy.serving",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain})
    return {"serving": True, "message": message[0]}


@router.get("/sites/{site_id}/database")
async def site_database(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """The database this site uses, and whether it can actually reach it.

    The server's database screen answers "what is on this machine". On a box with forty
    databases that is the wrong question — this one answers "which is THIS site's, and is
    it the reason the site is broken".

    Nothing here can carry a password: the probe reads one from the site's own config to
    make the connection attempt, on the server, and returns a single word.
    """
    from app.services import database_service, site_database_naming, site_database_service

    site, server = await _site_and_server(site_id, current_user, db)
    if server.connection_type != "ssh":
        return {"ok": False, "reason": "This needs a Linux server we reach over SSH."}

    result = await site_database_service.read(server, site.app_type, site.doc_root or "")
    if result.get("ok"):
        return result

    # A site with no configuration we can read — a plain PHP site — leaves the page unable
    # to see even a database we made for it ourselves, so it would offer to make another
    # and fail on the name. Looking for one named after the site closes that, and is
    # reported as the guess it is.
    listing = await database_service.list_databases(server)
    match = site_database_naming.find_named_after(site.domain, listing.get("engines", []))
    if match:
        result = {**result, "named_after_site": match}
    return result


class RobotsIn(BaseModel):
    block: bool


@router.get("/sites/{site_id}/robots")
async def read_robots(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Whether search engines are being asked to stay away from this site."""
    from app.services import connection_manager, robots_service as rb

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    cfg, _apache, why = await _resolve_site_config(server, site)
    if cfg is None:
        return {"ok": False, "reason": why or "This site's configuration was not found."}

    # Read from a real request, not from the file. What a crawler sees is the only thing
    # that decides whether the site is indexed.
    out, _e, _c = await connection_manager.execute(
        server,
        f'curl -sI --max-time 6 -H "Host: {shlex.quote(site.domain)[1:-1]}" '
        f'http://127.0.0.1/ 2>/dev/null | grep -i "^x-robots-tag:" | head -1')
    return {"ok": True, "blocked": "noindex" in (out or "").lower(),
            "header": (out or "").strip()}


@router.post("/sites/{site_id}/robots")
async def set_robots(site_id: str, body: RobotsIn, db: DBDep,
                     current_user: CurrentUser) -> dict:
    """Ask search engines not to index this site — or allow them again."""
    from app.services import connection_manager, robots_service as rb

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    cfg, apache, why = await _resolve_site_config(server, site)
    if cfg is None:
        raise HTTPException(422, why or "This site's configuration could not be found.")

    out, err, code = await connection_manager.execute(
        server, rb.build_command(cfg, site.domain, block=body.block, apache=apache))
    ok, message = rb.explain(code, (out or "") + (err or ""), block=body.block)
    if not ok:
        raise HTTPException(422, message)
    await audit_service.audit(db, current_user, "site.robots",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "blocked": body.block})
    return {"message": message, "blocked": body.block}


class QueueWorkerIn(BaseModel):
    connection: str
    queue: str = "default"
    processes: int = 1
    timeout: int = 60
    sleep: int = 3
    tries: int = 3
    backoff: int = 0
    memory: int = 128
    environment: str = ""


@router.get("/sites/{site_id}/queue")
async def read_queue_workers(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """This application's queue connections, and the workers already running for it."""
    from app.services import connection_manager, queue_worker_service as qw
    from app.services import site_daemon_service as daemons

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    if (site.app_type or "") != "laravel":
        raise HTTPException(400, "Queue workers are a Laravel feature, and this site does "
                                 "not run one.")
    out, err, _c = await connection_manager.execute(
        server, qw.build_probe_command(site.doc_root or ""))
    state = qw.parse_probe((out or "") + (err or ""))
    if not state.get("ok"):
        return state

    listed, _e, _c2 = await connection_manager.execute(
        server, daemons.build_list_command(site.domain))
    running = [d for d in daemons.parse_list(listed or "")
               if "--queue-" in d.get("unit", "") or "queue-" in d.get("name", "")]
    state["workers"] = running
    state["limits"] = qw.LIMITS
    return state


@router.post("/sites/{site_id}/queue", status_code=201)
async def add_queue_workers(site_id: str, body: QueueWorkerIn, db: DBDep,
                            current_user: CurrentUser) -> dict:
    """Create the workers, refusing the combination that processes a job twice."""
    from app.services import connection_manager, queue_worker_service as qw
    from app.services import laravel_service

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    if (site.app_type or "") != "laravel":
        raise HTTPException(400, "Queue workers are a Laravel feature.")

    app = await laravel_service.read(server, site.doc_root or "")
    if not app.get("ok"):
        raise HTTPException(422, app.get("reason") or "We could not read this application.")

    out, err, _c = await connection_manager.execute(
        server, qw.build_probe_command(site.doc_root or ""))
    state = qw.parse_probe((out or "") + (err or ""))

    try:
        connection = qw.valid_name(body.connection, what="connection name")
        queue = qw.valid_name(body.queue, what="queue name")
        numbers = {k: qw.check_number(getattr(body, k), k)
                   for k in ("timeout", "sleep", "tries", "backoff", "memory", "processes")}
        # The one that matters. Refused, not warned about — the consequence is a customer
        # charged twice, and a warning is something somebody clicks past.
        qw.check_timeout(numbers["timeout"],
                         qw.retry_after_for(state.get("connections", []), connection))
        units = qw.build_units(
            domain=site.domain, working_dir=app.get("path") or site.doc_root or "",
            run_as=app.get("runs_as") or "www-data", queue=queue,
            php=app.get("php_bin") or "php", connection=connection,
            environment=body.environment.strip(), **numbers)
    except qw.QueueError as exc:
        raise HTTPException(422, str(exc)) from exc

    from app.services import site_daemon_service as daemons

    made, failed = [], []
    for unit, content, script in units:
        o, e, code = await connection_manager.execute(
            server, daemons.build_install_command(unit, content, script))
        (made if code == 0 else failed).append(unit)
        if code != 0:
            failed[-1] = f"{unit}: {((o or '') + (e or '')).strip().splitlines()[-1:] or ['']}"

    if not made:
        raise HTTPException(422, "No worker would start. " + "; ".join(str(f) for f in failed))

    await audit_service.audit(db, current_user, "site.queue.created",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "queue": queue,
                                    "processes": len(made)})
    note = (f"{len(made)} worker(s) running on {queue}."
            + (f" {len(failed)} did not start." if failed else ""))
    return {"message": note, "created": made}


class WpDebugIn(BaseModel):
    enable: bool


class WpXmlrpcIn(BaseModel):
    block: bool


async def _wp_context(site_id: str, db, current_user, *, need_execute: bool):
    site, server = await _site_and_server(site_id, current_user, db,
                                          need_execute=need_execute)
    if server.connection_type != "ssh":
        raise HTTPException(400, "These settings need a Linux server we reach over SSH.")
    if (site.app_type or "") != "wordpress":
        raise HTTPException(400, "This site does not run WordPress.")
    return site, server


@router.get("/sites/{site_id}/wp-security")
async def read_wp_security(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """The two WordPress security switches, and whether either is currently unsafe."""
    import base64 as _b

    from app.services import connection_manager, wp_security_service as wps

    site, server = await _wp_context(site_id, db, current_user, need_execute=True)
    out, err, _code = await connection_manager.execute(
        server, wps.build_state_command(site.doc_root or ""))

    # The XML-RPC block lives in the web-server config, so it is read from there rather
    # than from anything we remember having done.
    block = ""
    cfg, _apache, _why = await _resolve_site_config(server, site)
    if cfg:
        got, _e, code = await connection_manager.execute(
            server, f"base64 < {shlex.quote(cfg)}")
        if code == 0:
            try:
                block = _b.b64decode(got or "").decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                block = ""

    state = wps.parse_state((out or "") + (err or ""), config_block=block)
    state["xmlrpc_breaks"] = list(wps.XMLRPC_BREAKS)
    # Where the log WOULD go, so the screen can say it before anything is switched — and
    # can say plainly when there is nowhere safe.
    try:
        state["log_path"] = wps.log_path_for(state.get("path") or site.doc_root or "")
        state["can_debug"] = True
        state["cannot_debug_reason"] = None
    except wps.WpSecurityError as exc:
        state["log_path"] = ""
        state["can_debug"] = False
        state["cannot_debug_reason"] = str(exc)
    return state


@router.post("/sites/{site_id}/wp-security/debug")
async def set_wp_debug(site_id: str, body: WpDebugIn, db: DBDep,
                       current_user: CurrentUser) -> dict:
    """Turn debug logging on or off.

    Three constants move together on the way on. The one that stops PHP errors being
    printed into the page for visitors is not optional and is not a separate switch.
    """
    from app.services import connection_manager, laravel_service  # noqa: F401
    from app.services import wp_security_service as wps

    site, server = await _wp_context(site_id, db, current_user, need_execute=True)
    root = site.doc_root or ""
    try:
        command = wps.build_debug_command(root, root, enable=body.enable)
    except wps.WpSecurityError as exc:
        raise HTTPException(422, str(exc)) from exc

    out, err, _code = await connection_manager.execute(server, command)
    ok, message = wps.explain_debug((out or "") + (err or ""), enable=body.enable)
    if not ok:
        raise HTTPException(422, message)
    await audit_service.audit(db, current_user, "site.wp.debug",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "enabled": body.enable})
    return {"message": message}


@router.post("/sites/{site_id}/wp-security/xmlrpc")
async def set_wp_xmlrpc(site_id: str, body: WpXmlrpcIn, db: DBDep,
                        current_user: CurrentUser) -> dict:
    """Block or unblock xmlrpc.php at the web server, before WordPress starts."""
    from app.services import connection_manager, wp_security_service as wps

    site, server = await _wp_context(site_id, db, current_user, need_execute=True)
    cfg, apache, why = await _resolve_site_config(server, site)
    if cfg is None:
        raise HTTPException(422, why or "This site's configuration could not be found.")

    out, err, code = await connection_manager.execute(
        server, wps.build_xmlrpc_command(cfg, site.domain, block=body.block, apache=apache))
    ok, message = wps.explain_xmlrpc(code, (out or "") + (err or ""), block=body.block)
    if not ok:
        raise HTTPException(422, message)
    await audit_service.audit(db, current_user, "site.wp.xmlrpc",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "blocked": body.block})
    return {"message": message}


class EnvIn(BaseModel):
    content: str


async def _env_context(site_id: str, db, current_user, *, need_execute: bool):
    """The site, its server, and where its application actually lives.

    The app root comes from the Laravel probe, which finds it by locating `artisan` — never
    from the caller and never guessed from the document root, because this path decides
    which file gets rewritten.
    """
    from app.services import laravel_service

    site, server = await _site_and_server(site_id, current_user, db,
                                          need_execute=need_execute)
    if server.connection_type != "ssh":
        raise HTTPException(400, "Settings can only be edited on a Linux server over SSH.")
    if (site.app_type or "") != "laravel":
        raise HTTPException(
            400, "This is the settings file of a Laravel application, and this site does "
                 "not run one.")
    app = await laravel_service.read(server, site.doc_root or "")
    if not app.get("ok") or not app.get("path"):
        raise HTTPException(422, app.get("reason") or "We could not read this application.")
    return site, server, app


@router.get("/sites/{site_id}/env")
async def read_site_env(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """This application's settings file.

    Fetched over SFTP rather than through a shell command: every value in it is a
    credential, and a command's arguments are visible in `ps` and are kept in the stored
    output of the run.
    """
    from app.services import connection_manager, env_service, file_service

    site, server, app = await _env_context(site_id, db, current_user, need_execute=True)
    try:
        path = env_service.env_path(app["path"])
    except env_service.EnvError as exc:
        raise HTTPException(422, str(exc)) from exc

    out, err, _code = await connection_manager.execute(
        server, env_service.build_facts_command(app["path"], site.domain))
    facts = env_service.parse_facts((out or "") + (err or ""))

    content = ""
    if facts["exists"]:
        try:
            content = (await file_service.download_file(server, path)).decode(
                "utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 — a read failure is an outcome, not a crash
            raise HTTPException(422, f"That file could not be read: {exc}") from exc

    await audit_service.audit(db, current_user, "site.env.read",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain})
    return {
        "path": path,
        "content": content,
        # A scannable view for a reader who is not editing. `secret` is a display hint from
        # the KEY, so a screen can hide a value without ever having to decide what a
        # password looks like.
        "settings": env_service.summarise(content),
        **facts,
        "warning": env_service.exposure_warning(facts),
        "php_bin": app.get("php_bin", ""),
    }


@router.post("/sites/{site_id}/env")
async def save_site_env(site_id: str, body: EnvIn, db: DBDep,
                        current_user: CurrentUser) -> dict:
    """Save the settings, and put the old ones back if the site stops working.

    Nothing about the content reaches a command line. It is uploaded over SFTP to a
    temporary name beside the real file, and the shell only performs the backup, the
    ownership, the atomic rename, the cache rebuild and the check that the site still
    serves — none of which carry a value.
    """
    from app.services import connection_manager, env_service, file_service

    site, server, app = await _env_context(site_id, db, current_user, need_execute=True)
    try:
        data = env_service.check_content(body.content)
        root = app["path"].rstrip("/")
        tmp = f"{root}/{env_service.TMP_NAME}"
    except env_service.EnvError as exc:
        raise HTTPException(422, str(exc)) from exc

    try:
        await file_service.upload_file(server, tmp, data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Those settings could not be sent: {exc}") from exc

    out, err, code = await connection_manager.execute(
        server,
        env_service.build_apply_command(
            root, site.domain,
            php_bin=app.get("php_bin", ""),
            # Rebuilt only when it was already in use. Building one on a site that does not
            # cache would change how it behaves, which is not what "save" means.
            rebuild_cache=bool(app.get("cache_config"))))
    ok, message = env_service.explain(code, (out or "") + (err or ""))
    if not ok:
        # Never leave our half-written copy behind — it sits next to the real file and
        # holds the same credentials.
        await connection_manager.execute(server, env_service.build_discard_command(root))
        raise HTTPException(422, message)

    # Deliberately records THAT the file changed and nothing about what is in it.
    await audit_service.audit(db, current_user, "site.env.saved",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "bytes": len(data)})
    return {"message": message}


@router.get("/sites/{site_id}/cron")
async def site_cron(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """The scheduled jobs that belong to this site.

    A crontab is the server's, so this is a filter over it rather than a separate list —
    and it matches on the site's FOLDER first, because matching on the domain alone would
    claim a neighbour's job that merely mentions this domain in a URL.
    """
    from app.services import cron_service

    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")
    server = await resolve_server(str(site.server_id), current_user, db)
    if server.connection_type != "ssh":
        return {"jobs": [], "reachable": False}

    listing = await cron_service.list_jobs(server)
    jobs = cron_service.jobs_for_site(
        listing.get("users", []), site.domain, site.doc_root)
    # What this application needs but does not have. Offered, never added on its own, and
    # withheld once something is already doing the job.
    suggested = None
    if not site_cron_service.already_scheduled(site.app_type, jobs):
        suggested = site_cron_service.suggested_job(site.app_type, site.doc_root or "")
    return {
        "jobs": jobs,
        "reachable": listing.get("reachable", False),
        "server_id": str(server.id),
        "suggested": suggested,
    }


async def _daemon_context(site_id: str, db, current_user, *, need_execute: bool):
    """The site, its server, and the two facts every daemon write needs."""
    from app.services import connection_manager, site_cron_service

    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")
    server = await resolve_server(str(site.server_id), current_user, db,
                                  need_execute=need_execute)
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=400,
            detail="Background jobs need a Linux server we reach over SSH.")
    if not site.doc_root:
        raise HTTPException(
            status_code=422,
            detail="We do not know where this site's files are. Scan the server first.")

    # The same rule as its scheduled jobs, for the same reason: a worker run as root
    # leaves root-owned files inside the site, and the site breaks days later.
    root = site_cron_service.app_root(site.app_type, site.doc_root)
    stdout, _e, _c = await connection_manager.execute(
        server, site_cron_service.build_owner_command(root))
    owner = site_cron_service.parse_owner(stdout)
    if need_execute and not owner:
        raise HTTPException(
            status_code=422,
            detail="We could not tell which account owns this site's files, so we will "
                   "not guess which one should run a background job.")
    return site, server, root, owner


@router.get("/sites/{site_id}/daemons")
async def site_daemons(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """The background processes kept running for this site."""
    from app.services import connection_manager, site_cron_service, site_daemon_service

    site, server, root, _owner = await _daemon_context(
        site_id, db, current_user, need_execute=False)
    stdout, _e, _c = await connection_manager.execute(
        server, site_daemon_service.build_list_command(site.domain))
    daemons = site_daemon_service.parse_list(stdout)
    running = {d["command"] for d in daemons}
    suggested = site_daemon_service.suggested(
        site.app_type, site_cron_service.app_root(site.app_type, site.doc_root or ""))
    if suggested and any(suggested["command"] in c for c in running):
        suggested = None
    return {"daemons": daemons, "suggested": suggested, "working_dir": root}


class DaemonIn(BaseModel):
    name: str = Field(max_length=31)
    command: str = Field(max_length=500)
    description: str = Field(default="", max_length=120)


@router.post("/sites/{site_id}/daemons", status_code=201)
async def add_site_daemon(site_id: str, body: DaemonIn, db: DBDep,
                          current_user: CurrentUser) -> dict:
    """Keep a command running for this site, and restart it if it stops."""
    from app.services import connection_manager, site_daemon_service

    site, server, root, owner = await _daemon_context(
        site_id, db, current_user, need_execute=True)

    try:
        unit = site_daemon_service.unit_name(site.domain, body.name)
        content = site_daemon_service.build_unit(
            domain=site.domain,
            description=body.description or f"{body.name} for {site.domain}",
            command=body.command.strip(), working_dir=root, run_as=owner or "",
            unit=unit)
        script = site_daemon_service.build_script(root, body.command)
    except site_daemon_service.DaemonError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = site_daemon_service.parse_list((await connection_manager.execute(
        server, site_daemon_service.build_list_command(site.domain)))[0])
    if any(d["unit"] == unit for d in existing):
        raise HTTPException(
            status_code=409,
            detail=f"This site already has a background job called “{body.name}”. "
                   f"Remove it first, or use a different name.")

    out, err, _code = await connection_manager.execute(
        server, site_daemon_service.build_install_command(unit, content, script))
    text = (out or "") + (err or "")
    await audit_service.audit(db, current_user, "site.daemon_added",
                              target_type="server", target_id=str(server.id),
                              meta={"site": site.domain, "unit": unit})

    if "SM_DAEMON_OK" in text:
        return {"ok": True, "unit": unit,
                "message": f"“{body.name}” is running and will start again on boot."}
    # Started is not the same as running: a command with a typo starts, exits at once, and
    # systemd calls the start successful. The unit is left in place with its own log, which
    # is the only thing that says why.
    log = "\n".join(ln for ln in text.splitlines()
                    if not ln.startswith("SM_DAEMON"))[-1500:]
    return {"ok": False, "unit": unit,
            "message": f"“{body.name}” was set up but did not stay running.",
            "log": log.strip()}


class DaemonActionIn(BaseModel):
    unit: str = Field(max_length=120)
    action: str = Field(max_length=10)


@router.post("/sites/{site_id}/daemons/action")
async def act_on_site_daemon(site_id: str, body: DaemonActionIn, db: DBDep,
                             current_user: CurrentUser) -> dict:
    """Start, stop, restart or remove one of this site's background jobs."""
    from app.services import connection_manager, site_daemon_service

    site, server, _root, _owner = await _daemon_context(
        site_id, db, current_user, need_execute=True)

    # The guard that keeps this a site page rather than a systemd editor. Without it a
    # wrong name here stops nginx, or the database every other site on the box uses.
    if not site_daemon_service.owns(body.unit, site.domain):
        raise HTTPException(
            status_code=422,
            detail="That is not one of this site's background jobs. The server's Services "
                   "screen manages everything else on this machine.")

    try:
        cmd = (site_daemon_service.build_remove_command(body.unit)
               if body.action == "remove"
               else site_daemon_service.build_action_command(body.unit, body.action))
    except site_daemon_service.DaemonError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    out, err, _code = await connection_manager.execute(server, cmd)
    await audit_service.audit(db, current_user, f"site.daemon_{body.action}",
                              target_type="server", target_id=str(server.id),
                              meta={"site": site.domain, "unit": body.unit})
    return {"ok": True, "output": ((out or "") + (err or "")).strip()[-500:]}


@router.get("/sites/{site_id}/php")
async def site_php(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Which PHP runs this site, and what else this server has installed."""
    from app.services import php_service

    site, server = await _site_and_server(site_id, current_user, db)
    if server.connection_type != "ssh":
        return {"ok": False, "reason": "This needs a Linux server we reach over SSH."}

    state = await php_service.read(server)
    config = php_service.config_for_site(
        state.get("sites", []), site.doc_root, site.domain)
    if config is None:
        return {
            "ok": False,
            "versions": state.get("versions", []),
            "reason": "We could not work out which of this server's configuration files "
                      "serves this site, so we will not change one and hope. The server's "
                      "PHP screen lists them all.",
        }
    return {
        "ok": True,
        "version": config.get("version"),
        "config": config.get("config"),
        "versions": state.get("versions", []),
        "running": state.get("running", []),
        "cli_default": state.get("cli_default"),
    }


class SitePhpIn(BaseModel):
    version: str = Field(max_length=10)


@router.post("/sites/{site_id}/php")
async def switch_site_php(site_id: str, body: SitePhpIn, db: DBDep,
                          current_user: CurrentUser) -> dict:
    """Change which PHP version serves this site, and put it back if the site breaks.

    The config to rewrite is resolved HERE, from the site, and never accepted from the
    caller. A path from the client would make this endpoint able to rewrite any file on
    the server; resolving it from the site also means the page cannot switch a neighbour.
    """
    from app.services import connection_manager, php_service

    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")
    server = await resolve_server(str(site.server_id), current_user, db, need_execute=True)
    if server.connection_type != "ssh":
        raise HTTPException(status_code=400,
                            detail="This server is not managed over SSH.")

    try:
        version = php_service.valid_version(body.version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    state = await php_service.read(server)
    config = php_service.config_for_site(
        state.get("sites", []), site.doc_root, site.domain)
    if config is None:
        raise HTTPException(
            status_code=422,
            detail="We could not work out which configuration file serves this site, so "
                   "nothing was changed.")
    if version not in state.get("versions", []):
        raise HTTPException(
            status_code=422,
            detail=f"PHP {version} is not installed on this server. Install it first.")

    cmd = php_service.build_switch_command(config["config"], version, site.domain)
    out, err, code = await connection_manager.execute(server, cmd)
    ok, message = php_service.explain_switch(code, out or err)

    await audit_service.audit(
        db, current_user, "php.site_switched" if ok else "php.site_switch_failed",
        target_type="server", target_id=str(server.id),
        meta={"site": site.domain, "version": version, "ok": ok})

    if not ok:
        # 409, not 500: nothing is broken — the change was refused, or made and undone.
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "message": message}


# ── The web-server configuration, edited by hand ─────────────────────────────

@router.get("/sites/{site_id}/vhost")
async def read_site_vhost(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """This site's own web-server configuration file, as it is on the machine."""
    import base64 as _b64

    from app.services import connection_manager, vhost_service

    site, server = await _site_and_server(site_id, current_user, db)
    if server.connection_type != "ssh" or server.panel_type:
        return {"ok": False, "reason": (
            f"This site is managed by {server.panel_type}, which writes its own "
            f"configuration — anything changed here would be overwritten by it."
            if server.panel_type else
            "Editing the configuration needs a Linux server we reach over SSH.")}

    path, _apache, why = await _resolve_site_config(server, site)
    if path is None:
        return {"ok": False, "reason": why}

    out, err, code = await connection_manager.execute(
        server, vhost_service.build_read_command(path))
    if code != 0:
        return {"ok": False, "reason": "That file could not be read on the server.",
                "path": path}
    try:
        content = _b64.b64decode((out or "").strip()).decode(errors="replace")
    except Exception:  # noqa: BLE001 — a file we cannot decode is one we must not offer
        return {"ok": False, "reason": "That file is not readable as text.", "path": path}
    return {"ok": True, "path": path, "content": content}


class AliasIn(BaseModel):
    alias: str = Field(max_length=253)


async def _alias_apply(server, site, aliases: list[str], db) -> dict:
    """Write the list into the site's configuration, and record it only if that worked.

    The order matters: the server is the truth. Saving our row first would leave the page
    showing an alias the web server never accepted — which is the same "we said it worked"
    failure the whole product exists to avoid.
    """
    from app.services import alias_service, connection_manager

    path, apache, why = await _resolve_site_config(server, site)
    if path is None:
        raise HTTPException(status_code=422, detail=why or "Its configuration was not found.")

    cmd = alias_service.build_apply_command(path, site.domain, aliases, apache=apache)
    out, err, code = await connection_manager.execute(server, cmd)
    ok, message = alias_service.explain(code, (out or "") + (err or ""))
    if not ok:
        raise HTTPException(status_code=422, detail=message)

    site.aliases = aliases
    await db.commit()
    return {"aliases": aliases, "message": message}


@router.get("/sites/{site_id}/aliases")
async def list_site_aliases(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """The extra domains this site answers for."""
    site, server = await _site_and_server(site_id, current_user, db)
    return {"domain": site.domain, "aliases": list(site.aliases or [])}


@router.post("/sites/{site_id}/aliases", status_code=201)
async def add_site_alias(site_id: str, body: AliasIn, db: DBDep,
                         current_user: CurrentUser) -> dict:
    """Make this site answer for one more domain."""
    from app.services import alias_service

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)

    # Who else on THIS server already answers for that name. The web server hands a name to
    # whichever block claims it, so without this a neighbour's visitors would quietly start
    # arriving here and nothing on either screen would say why.
    others = (await db.execute(
        select(Site).where(Site.server_id == server.id, Site.id != site.id,
                           Site.is_present.is_(True)))).scalars().all()
    taken: dict[str, str] = {}
    for row in others:
        for name in [row.domain, *(row.aliases or [])]:
            taken[(name or "").strip().lower()] = row.domain

    try:
        alias = alias_service.check_new(
            body.alias, domain=site.domain, existing=list(site.aliases or []), taken=taken)
    except alias_service.AliasError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = await _alias_apply(server, site, [*(site.aliases or []), alias], db)
    await audit_service.audit(db, current_user, "site.alias_added",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "alias": alias})
    return result


@router.delete("/sites/{site_id}/aliases/{alias}")
async def remove_site_alias(site_id: str, alias: str, db: DBDep,
                            current_user: CurrentUser) -> dict:
    """Stop answering for one of them. Runs the same command as adding, so there is no
    separate removal path to get wrong."""
    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    target = (alias or "").strip().lower()
    remaining = [a for a in (site.aliases or []) if a.strip().lower() != target]
    if len(remaining) == len(site.aliases or []):
        raise HTTPException(status_code=404, detail="That is not an alias of this site.")

    result = await _alias_apply(server, site, remaining, db)
    await audit_service.audit(db, current_user, "site.alias_removed",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "alias": target})
    return result



class AuthIn(BaseModel):
    name: str = Field(max_length=32)
    # Never echoed back and never stored. It is hashed before it leaves this process.
    password: str = Field(max_length=200)
    path: str = Field(default="", max_length=200)


async def _auth_read(server, site) -> tuple[list[str], str]:
    """The usernames guarding this site, from the server's own password file."""
    import base64 as _b

    from app.services import connection_manager, site_auth_service as sa

    out, _err, code = await connection_manager.execute(
        server, sa.build_read_command(site.domain))
    if code != 0 or not (out or "").strip():
        return [], ""
    try:
        content = _b.b64decode(out.strip()).decode(errors="replace")
    except Exception:  # noqa: BLE001
        return [], ""
    return sa.parse_users(content), content


async def _auth_apply(server, site, lines: list[str], path: str) -> dict:
    from app.services import connection_manager, site_auth_service as sa

    cfg, apache, why = await _resolve_site_config(server, site)
    if cfg is None:
        raise HTTPException(status_code=422, detail=why or "Its configuration was not found.")
    cmd = sa.build_apply_command(cfg, site.domain, lines, path, apache=apache)
    out, err, code = await connection_manager.execute(server, cmd)
    ok, message = sa.explain(code, (out or "") + (err or ""), users=len(lines), path=path)
    if not ok:
        raise HTTPException(status_code=422, detail=message)
    users, _ = await _auth_read(server, site)
    return {"users": users, "path": path, "enabled": bool(users), "message": message}


@router.get("/sites/{site_id}/auth")
async def get_site_auth(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Who has to sign in before this site is shown."""
    from app.services import site_auth_service as sa

    site, server = await _site_and_server(site_id, current_user, db)
    users, _ = await _auth_read(server, site)
    # The path is read off the configuration rather than remembered, so the screen agrees
    # with the server even if somebody edited the file by hand.
    path = ""
    cfg, _apache, _why = await _resolve_site_config(server, site)
    if cfg:
        from app.services import connection_manager, vhost_service
        import base64 as _b
        out, _e, code = await connection_manager.execute(
            server, vhost_service.build_read_command(cfg))
        if code == 0:
            try:
                text = _b.b64decode((out or "").strip()).decode(errors="replace")
                import re as _re
                m = _re.search(r"location \^~ (\S+)/ \{", text)
                if m and sa.BEGIN in text:
                    path = m.group(1)
            except Exception:  # noqa: BLE001
                path = ""
    return {"users": users, "enabled": bool(users), "path": path}


@router.post("/sites/{site_id}/auth", status_code=201)
async def set_site_auth(site_id: str, body: AuthIn, db: DBDep,
                        current_user: CurrentUser) -> dict:
    """Add a person who may sign in, or change their password."""
    from app.services import site_auth_service as sa

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    try:
        name = sa.clean_name(body.name)
        path = sa.clean_path(body.path)
        line = sa.htpasswd_line(name, body.password)
    except sa.AuthError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _users, content = await _auth_read(server, site)
    lines = sa.replace_user(content, name, line)
    result = await _auth_apply(server, site, lines, path)
    # The username is recorded; the password deliberately is not, so reading the audit trail
    # can never hand somebody a live login.
    await audit_service.audit(db, current_user, "site.auth_set",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "user": name, "path": path})
    return result


@router.delete("/sites/{site_id}/auth/{name}")
async def remove_site_auth(site_id: str, name: str, db: DBDep,
                           current_user: CurrentUser) -> dict:
    """Take one person's access away. Removing the last one opens the site again."""
    from app.services import site_auth_service as sa

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    users, content = await _auth_read(server, site)
    if name not in users:
        raise HTTPException(status_code=404, detail="No such user on this site.")

    current = await get_site_auth(site_id, db, current_user)
    lines = sa.replace_user(content, name, None)
    result = await _auth_apply(server, site, lines, current["path"] if lines else "")
    await audit_service.audit(db, current_user, "site.auth_removed",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "user": name})
    return result



class SuspendIn(BaseModel):
    suspended: bool
    message: str = Field(default="", max_length=200)
    reason: str = Field(default="", max_length=4000)
    code: int = 503


@router.get("/sites/{site_id}/suspend")
async def get_site_suspend(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Whether this site is suspended, and with what."""
    import base64 as _b
    import json as _j

    from app.services import connection_manager, suspend_service as sus

    site, server = await _site_and_server(site_id, current_user, db)
    out, _err, code = await connection_manager.execute(
        server, sus.build_state_command(site.domain))
    state = {}
    if code == 0 and (out or "").strip():
        try:
            state = _j.loads(_b.b64decode(out.strip()).decode())
        except Exception:  # noqa: BLE001
            state = {}
    return {
        "suspended": bool(state),
        "message": state.get("message", ""),
        "reason": state.get("reason", ""),
        "code": state.get("code", sus.DEFAULT_CODE),
        "codes": [dict(c) for c in sus.CODES],
    }


@router.post("/sites/{site_id}/suspend")
async def set_site_suspend(site_id: str, body: SuspendIn, db: DBDep,
                           current_user: CurrentUser) -> dict:
    """Take the site offline behind a notice, or put it back."""
    from app.services import connection_manager, suspend_service as sus

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    try:
        status = sus.check_code(body.code)
    except sus.SuspendError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cfg, apache, why = await _resolve_site_config(server, site)
    if cfg is None:
        raise HTTPException(status_code=422, detail=why or "Its configuration was not found.")

    cmd = sus.build_apply_command(
        cfg, site.domain, suspended=body.suspended, message=body.message,
        reason=body.reason, code=status, apache=apache)
    out, err, rc = await connection_manager.execute(server, cmd)
    ok, message = sus.explain(rc, (out or "") + (err or ""),
                              suspended=body.suspended, status=status)
    if not ok:
        raise HTTPException(status_code=422, detail=message)

    await audit_service.audit(
        db, current_user, "site.suspended" if body.suspended else "site.unsuspended",
        target_type="server", target_id=str(server.id),
        meta={"domain": site.domain, "code": status})
    return {"suspended": body.suspended, "code": status, "message": message}



@router.post("/sites/{site_id}/reset-permissions")
async def reset_site_permissions(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Put this site's file ownership and permissions back to a known-good state.

    The folder is taken from the SITE, never from the caller: this ends in `chown -R`, and
    a path from a browser would be a request to hand the web server somebody else's files.
    """
    from app.services import connection_manager, permissions_service as perms

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    try:
        cmd = perms.build_command(site.doc_root)
    except perms.PermissionsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    out, err, code = await connection_manager.execute(server, cmd)
    ok, message = perms.explain(code, (out or "") + (err or ""))
    if not ok:
        raise HTTPException(status_code=422, detail=message)

    await audit_service.audit(db, current_user, "site.permissions_reset",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "folder": site.doc_root})
    return {"message": message}



class CloneIn(BaseModel):
    domain: str
    server_id: str


@router.get("/sites/{site_id}/clone")
async def site_clone_options(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Where this site can be copied to, and what a copy leaves behind.

    The server list is filtered to the ones a clone can actually land on — Linux over SSH,
    no control panel — rather than showing every server and refusing later. A destination
    that cannot work is not offered.
    """
    from app.services import clone_service as clone, team_service

    site, server = await _site_and_server(site_id, current_user, db)
    servers = [
        {"id": str(s.id), "name": s.name, "host": s.host,
         "same": str(s.id) == str(server.id)}
        for s in await team_service.accessible_servers(db, current_user)
        if s.connection_type == "ssh" and not s.panel_type
    ]
    return {
        "domain": site.domain,
        "server_id": str(server.id),
        "servers": servers,
        # Both wordings, because which one applies depends on the server the customer picks
        # and that choice is made in the browser. Null for a site with no database to share.
        "database_note": {
            "same": clone.database_warning(site.app_type, same_server=True),
            "other": clone.database_warning(site.app_type, same_server=False),
        },
    }


@router.post("/sites/{site_id}/clone", status_code=201)
async def clone_site(site_id: str, body: CloneIn, db: DBDep,
                     current_user: CurrentUser) -> dict:
    """Copy this site's files to a new domain, here or on another server.

    Everything that can be refused is refused BEFORE a byte moves: the destination, the
    domain, the size, and whether the destination has room. A clone that fails halfway is
    a half-built site somebody has to clean up; a clone that fills a disk stops every other
    site on that machine.

    The new site is created through the ordinary install path, so it appears immediately as
    *Setting up* and follows exactly the same rules as any other new site — including that
    it only becomes live when a scan actually SEES it on the server.
    """
    from app.services import clone_service as clone, connection_manager
    from app.workers import clone_runner

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    dest = await resolve_server(body.server_id, current_user, db, need_execute=True)

    try:
        domain = clone.check_request(site, server, dest, body.domain)
    except clone.CloneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    same_server = str(dest.id) == str(server.id)

    # 1 ─ look at what is actually there. This decides whether the copy needs PHP, which is
    #     not a nicety: a PHP site served without a PHP handler publishes wp-config.php.
    out, err, code = await connection_manager.execute(
        server, clone.build_survey_command(site.doc_root or ""))
    try:
        survey = clone.parse_survey((out or "") + (err or ""), code)
        clone.check_transfer_size(survey.bytes, same_server=same_server)
    except clone.CloneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 2 ─ has the destination got room? Asked about the folder sites live in on THAT server.
    out, err, code = await connection_manager.execute(
        dest, clone.build_fit_command("/var/www"))
    try:
        clone.check_fit(survey.bytes, clone.parse_free((out or "") + (err or "")))
    except clone.CloneError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 3 ─ create the new site. Its own guards refuse a domain already configured there, and
    #     `create` refuses one we already track — so a clone can never land on a live site.
    try:
        new_site, run_id, script = await site_service.create(
            db, dest, current_user, domain=domain, site_type=clone.site_type_for(survey))
    except (site_service.SiteError, playbook_service.UnresolvedVariables) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    asyncio.create_task(clone_runner.run_clone(
        run_id=uuid.UUID(run_id), script=script,
        source_server_id=server.id, source_site_id=site.id,
        dest_server_id=dest.id, new_site_id=new_site.id,
        survey=survey, same_server=same_server))

    await audit_service.audit(db, current_user, "site.cloned",
                              target_type="server", target_id=str(dest.id),
                              meta={"from": site.domain, "to": domain,
                                    "server": dest.name, "bytes": survey.bytes})
    return {
        **site_service.serialize(new_site, server_name=dest.name),
        "run_id": run_id,
        "size": clone.human(survey.bytes),
        "files": survey.files,
        "database_note": clone.database_warning(site.app_type, same_server=same_server),
    }


class CacheIn(BaseModel):
    enabled: bool


@router.get("/sites/{site_id}/cache")
async def get_site_cache(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Whether page caching is on for this site."""
    import base64 as _b

    from app.services import connection_manager, fastcgi_cache_service as fc, vhost_service

    site, server = await _site_and_server(site_id, current_user, db)
    cfg, apache, _why = await _resolve_site_config(server, site)
    if cfg is None:
        return {"enabled": False, "supported": False,
                "reason": "We could not find this site's configuration."}
    if apache:
        return {"enabled": False, "supported": False,
                "reason": "Page caching here is an nginx feature, and this site is on Apache."}
    out, _e, code = await connection_manager.execute(
        server, vhost_service.build_read_command(cfg))
    text = ""
    if code == 0:
        try:
            text = _b.b64decode((out or "").strip()).decode(errors="replace")
        except Exception:  # noqa: BLE001
            text = ""
    return {"enabled": fc.BEGIN in text, "supported": "fastcgi_pass" in text,
            "reason": "" if "fastcgi_pass" in text else "This site does not run PHP."}


@router.post("/sites/{site_id}/cache")
async def set_site_cache(site_id: str, body: CacheIn, db: DBDep,
                         current_user: CurrentUser) -> dict:
    """Turn page caching on or off."""
    from app.services import connection_manager, fastcgi_cache_service as fc

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    cfg, apache, why = await _resolve_site_config(server, site)
    if cfg is None:
        raise HTTPException(status_code=422, detail=why or "Its configuration was not found.")
    try:
        cmd = fc.build_apply_command(cfg, site.domain, enabled=body.enabled, apache=apache)
    except fc.CacheError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    out, err, code = await connection_manager.execute(server, cmd)
    ok, message = fc.explain(code, (out or "") + (err or ""), enabled=body.enabled)
    if not ok:
        raise HTTPException(status_code=422, detail=message)
    await audit_service.audit(db, current_user, "site.cache_set",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "enabled": body.enabled})
    return {"enabled": body.enabled, "message": message}


@router.post("/sites/{site_id}/cache/purge")
async def purge_site_cache(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Throw the stored pages away — the escape hatch for "my edit is not showing"."""
    from app.services import connection_manager, fastcgi_cache_service as fc

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    out, err, code = await connection_manager.execute(
        server, fc.build_purge_command(site.domain))
    ok, message = fc.explain_purge(code, (out or "") + (err or ""))
    if not ok:
        raise HTTPException(status_code=422, detail=message)
    return {"message": message}



class VhostIn(BaseModel):
    content: str


@router.post("/sites/{site_id}/vhost")
async def save_site_vhost(site_id: str, body: VhostIn, db: DBDep,
                          current_user: CurrentUser) -> dict:
    """Replace it, and put the old one back if the server or the site disagrees.

    The path is resolved HERE from the site and never accepted from the caller — otherwise
    this endpoint could rewrite any file on the machine, and one site's page could take
    down a neighbour.
    """
    from app.services import connection_manager, vhost_service

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    if server.connection_type != "ssh" or server.panel_type:
        raise HTTPException(
            status_code=400,
            detail="The configuration can only be edited on a Linux server we reach over "
                   "SSH, and not on one a control panel manages.")

    path, _apache, why = await _resolve_site_config(server, site)
    if path is None:
        raise HTTPException(status_code=422, detail=why or "Its configuration was not found.")

    try:
        cmd = vhost_service.build_save_command(path, site.domain, body.content)
    except vhost_service.VhostError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    out, err, code = await connection_manager.execute(server, cmd)
    ok, message = vhost_service.explain(code, (out or "") + (err or ""))
    await audit_service.audit(db, current_user,
                              "site.vhost_saved" if ok else "site.vhost_rejected",
                              target_type="server", target_id=str(server.id),
                              meta={"site": site.domain, "path": path, "ok": ok})
    if not ok:
        # 409, not 500: nothing is broken — the change was refused, or made and undone.
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "message": message}


# ── Redirects ────────────────────────────────────────────────────────────────

async def _redirect_rules(db, site_id) -> list[dict]:
    """Every redirect this site has, oldest first — the order they are matched in."""
    from app.models.site_redirect import SiteRedirect

    rows = (await db.execute(
        select(SiteRedirect).where(SiteRedirect.site_id == site_id)
        .order_by(SiteRedirect.created_at)
    )).scalars().all()
    return [{"row": r, "from": r.redirect_from, "to": r.redirect_to,
             "type": r.redirect_type} for r in rows]


def _serialize_redirect(r) -> dict:
    from app.services import redirect_service

    return {
        "id": str(r.id),
        "from": r.redirect_from,
        "to": r.redirect_to,
        "type": r.redirect_type,
        "type_label": redirect_service.label_for(r.redirect_type),
        "is_applied": r.is_applied,
    }


async def _resolve_site_config(server, site) -> tuple[str | None, bool, str | None]:
    """Which configuration file serves this site, and whether it is Apache.

    Resolved on the SERVER from the site, never accepted from the caller: a path from the
    client would make these endpoints able to rewrite any file on the machine, and would
    let one site's page edit a neighbour's.
    """
    from app.services import php_service

    state = await php_service.read(server)
    # The server could not be read at all. Saying "we could not match a config" here sends
    # somebody looking at their site for a problem that is on the connection.
    if state.get("unreachable"):
        return None, False, state.get("error") or "This server could not be reached."
    config = php_service.config_for_site(state.get("sites", []), site.doc_root, site.domain)
    if config is None:
        return None, False, (
            "We could not work out which of this server's configuration files serves this "
            "site, so we will not edit one and hope.")
    path = config["config"]
    return path, ("/apache2/" in path or "/httpd/" in path), None


async def _apply_redirects(db, server, site, current_user, *,
                           without=None) -> tuple[bool, str]:
    """Write the whole set into the config. Adding, changing and removing are all this.

    ``without`` is the row being deleted. It is excluded from what gets written but is NOT
    yet gone from the table, so a failed write leaves the list and the server still saying
    the same thing. Deleting the row first and writing afterwards produces the dangerous
    disagreement instead: the write fails, the config is restored with the rule still in it,
    and our screen now claims a redirect is gone while visitors are still being sent away.
    """
    from app.services import connection_manager, redirect_service

    path, apache, why = await _resolve_site_config(server, site)
    if path is None:
        return False, why or "The site's configuration could not be found."

    rules = [r for r in await _redirect_rules(db, site.id)
             if without is None or r["row"].id != without.id]
    cmd = redirect_service.build_apply_command(
        path, site.domain, [{"from": r["from"], "to": r["to"], "type": r["type"]}
                            for r in rules],
        apache=apache)
    out, err, code = await connection_manager.execute(server, cmd)
    ok, message = redirect_service.explain(code, (out or "") + (err or ""))

    # Never left claiming to be live when the write failed — that is the difference the dot
    # on each row is showing.
    for r in rules:
        r["row"].is_applied = ok
    await db.commit()
    return ok, message


@router.get("/sites/{site_id}/redirects")
async def list_site_redirects(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """This site's redirects. Reads the table, so the page opens even when the server is not
    reachable — with each row saying honestly whether it is live."""
    site, server = await _site_and_server(site_id, current_user, db)
    rules = await _redirect_rules(db, site.id)
    return {
        "ok": server.connection_type == "ssh" and not server.panel_type,
        "reason": (
            f"This site is managed by {server.panel_type}, which owns its web-server "
            f"settings. Add redirects in the panel instead."
            if server.panel_type else
            "Redirects need a Linux server we reach over SSH."
            if server.connection_type != "ssh" else None),
        "redirects": [_serialize_redirect(r["row"]) for r in rules],
    }


class SiteRedirectIn(BaseModel):
    """Ploi's three fields, with their own value names for the type."""
    redirect_from: str = Field(max_length=500)
    redirect_to: str = Field(max_length=500)
    redirect_type: str = Field(default="redirect", max_length=20)


@router.post("/sites/{site_id}/redirects", status_code=201)
async def add_site_redirect(site_id: str, body: SiteRedirectIn, db: DBDep,
                            current_user: CurrentUser) -> dict:
    """Send one path on this site to another address."""
    from app.models.site_redirect import SiteRedirect
    from app.services import redirect_service

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    if server.connection_type != "ssh" or server.panel_type:
        raise HTTPException(
            status_code=400,
            detail="Redirects are written into the web server's own configuration, which "
                   "needs a Linux server we reach over SSH and no control panel.")

    try:
        src = redirect_service.valid_from(body.redirect_from)
        dst = redirect_service.valid_to(body.redirect_to)
        kind = redirect_service.valid_type(body.redirect_type)
    except redirect_service.RedirectError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = await _redirect_rules(db, site.id)
    if any(r["from"] == src for r in existing):
        raise HTTPException(
            status_code=409,
            detail=f"There is already a redirect from {src} on this site. Remove it first "
                   f"if you want to send it somewhere else.")

    row = SiteRedirect(site_id=site.id, user_id=current_user.id, redirect_from=src,
                       redirect_to=dst, redirect_type=kind, is_applied=False)
    db.add(row)
    await db.commit()
    await db.refresh(row)

    ok, message = await _apply_redirects(db, server, site, current_user)
    await audit_service.audit(db, current_user,
                              "site.redirect_added" if ok else "site.redirect_failed",
                              target_type="server", target_id=str(server.id),
                              meta={"site": site.domain, "from": src, "to": dst,
                                    "type": kind, "ok": ok})
    if not ok:
        # The row is kept and shown as not live, rather than vanishing with an error — the
        # owner can see what was attempted and try again.
        await db.refresh(row)
        raise HTTPException(status_code=409, detail=message)
    await db.refresh(row)
    return _serialize_redirect(row)


@router.delete("/sites/{site_id}/redirects/{redirect_id}", status_code=200)
async def remove_site_redirect(site_id: str, redirect_id: str, db: DBDep,
                               current_user: CurrentUser) -> dict:
    """Remove one redirect and rewrite the block without it."""
    from app.models.site_redirect import SiteRedirect

    site, server = await _site_and_server(site_id, current_user, db, need_execute=True)
    row = (await db.execute(
        select(SiteRedirect).where(SiteRedirect.id == redirect_id,
                                   SiteRedirect.site_id == site.id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No such redirect.")

    # Written to the server first, and the row is only dropped once that succeeded — see
    # the note on _apply_redirects. Nothing here is a two-place change that can half-happen.
    was = row.redirect_from
    ok, message = await _apply_redirects(db, server, site, current_user, without=row)
    await audit_service.audit(db, current_user, "site.redirect_removed",
                              target_type="server", target_id=str(server.id),
                              meta={"site": site.domain, "from": was, "ok": ok})
    if not ok:
        raise HTTPException(status_code=409, detail=message)

    await db.delete(row)
    await db.commit()
    return {"ok": True, "message": "Removed."}


class SiteDatabaseIn(BaseModel):
    """A database for this site. Every field optional — the point is not having to decide."""
    engine: str = Field(default="mysql", max_length=20)
    name: str | None = Field(default=None, max_length=63)
    user: str | None = Field(default=None, max_length=63)
    #: Supplied only if the customer wants their own. Otherwise generated and shown once.
    password: str | None = Field(default=None, max_length=200)


@router.post("/sites/{site_id}/database", status_code=201)
async def create_site_database(site_id: str, body: SiteDatabaseIn, db: DBDep,
                               current_user: CurrentUser) -> dict:
    """Create a database and its own account for a site that has none.

    Only for a site that has none. A site already using one is left alone on purpose: two
    databases and no way to say which the application should use is a worse position than
    the one it started in, and the server's own Databases screen is there for the case
    where somebody genuinely means it.

    The password is returned ONCE and stored nowhere. We hold no copy, which is also why
    there is no "show it again" — saying so is more honest than pretending to have lost it.
    """
    from app.services import database_service, site_database_naming, site_database_service

    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")
    server = await resolve_server(str(site.server_id), current_user, db, need_execute=True)
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=400,
            detail="Databases need a Linux server we reach over SSH.")

    existing = await site_database_service.read(
        server, site.app_type, site.doc_root or "")
    if existing.get("ok") and existing.get("name"):
        raise HTTPException(
            status_code=409,
            detail=f"This site already uses the database “{existing['name']}”. Adding a "
                   f"second one here would leave no way to say which it should use — the "
                   f"server's Databases screen can add one if you mean to.")

    # A site with no readable configuration cannot tell us what it uses, so check whether
    # we have already been here — otherwise a second press fails on the name clash and
    # explains nothing about why.
    listing = await database_service.list_databases(server)
    already = site_database_naming.find_named_after(site.domain, listing.get("engines", []))
    if already:
        raise HTTPException(
            status_code=409,
            detail=f"A database called “{already['name']}” already exists on this server. "
                   f"If it is this site's, put its details into the site's settings — this "
                   f"site's own configuration does not name a database, which is why we "
                   f"cannot tell from here.")

    name = body.name or site_database_naming.suggest_name(site.domain)
    user = body.user or site_database_naming.suggest_user(name)
    password = body.password or site_database_naming.generate_password()

    try:
        result = await database_service.create_database(
            server, engine=body.engine, db_name=name, user=user, password=password)
    except database_service.DatabaseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await audit_service.audit(db, current_user, "database.created",
                              target_type="server", target_id=str(server.id),
                              meta={"database": name, "site": site.domain})
    return {
        **result,
        # Shown once. Never written to our database, never logged, and not in the audit
        # entry above — which records that a database was made, not how to get into it.
        "password": password,
        "host": "127.0.0.1",
    }


class SiteCronIn(BaseModel):
    """A job to schedule for this site.

    ``user`` is deliberately absent: the caller does not choose who runs it. It runs as the
    owner of the site's files, which is a correctness rule rather than a preference — see
    site_cron_service.
    """
    schedule: str = Field(max_length=100)
    command: str = Field(max_length=500)
    note: str = Field(default="", max_length=120)
    #: What the screen was showing, so a job added behind our back is not overwritten.
    expect: str | None = Field(default=None, max_length=64)


class SiteCronRemoveIn(BaseModel):
    user: str = Field(max_length=32)
    raw_line: str = Field(max_length=600)
    expect: str | None = Field(default=None, max_length=64)


async def _site_for_cron(site_id: str, db, current_user, *, need_execute: bool):
    site = (await db.execute(
        select(Site).where(Site.id == site_id, Site.user_id == current_user.id)
    )).scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="No such site.")
    server = await resolve_server(str(site.server_id), current_user, db,
                                  need_execute=need_execute)
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=400,
            detail="Scheduled jobs need a Linux server we reach over SSH.")
    return site, server


@router.post("/sites/{site_id}/cron", status_code=201)
async def add_site_cron(site_id: str, body: SiteCronIn, db: DBDep,
                        current_user: CurrentUser) -> dict:
    """Schedule a job for this site, running as the account that owns its files."""
    from app.services import connection_manager, cron_service

    site, server = await _site_for_cron(site_id, db, current_user, need_execute=True)
    if not site.doc_root:
        raise HTTPException(
            status_code=422,
            detail="We do not know where this site's files are, so we cannot tell which "
                   "account a job should run as. Scan the server first.")

    # Whose files these are decides who runs the job. Guessing here is how a scheduler
    # ends up writing root-owned files into a site that then cannot write them itself.
    stdout, _err, _code = await connection_manager.execute(
        server, site_cron_service.build_owner_command(site.doc_root))
    owner = site_cron_service.parse_owner(stdout)
    if not owner:
        raise HTTPException(
            status_code=422,
            detail="We could not tell which account owns this site's files, so we will "
                   "not guess which one should run its scheduled jobs.")

    try:
        result = await cron_service.add_job(
            server, user=owner, schedule=body.schedule, command=body.command,
            note=body.note or site.domain, expect=body.expect)
    except cron_service.CronError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await audit_service.audit(db, current_user, "cron.added",
                              target_type="server", target_id=str(server.id),
                              meta={"user": owner, "schedule": body.schedule,
                                    "site": site.domain})
    return {**result, "user": owner}


@router.post("/sites/{site_id}/cron/remove")
async def remove_site_cron(site_id: str, body: SiteCronRemoveIn, db: DBDep,
                           current_user: CurrentUser) -> dict:
    """Remove one of this site's scheduled jobs, matched by its exact line."""
    from app.services import cron_service

    site, server = await _site_for_cron(site_id, db, current_user, need_execute=True)

    # A site page may only remove jobs that are this site's. Without this it would be a
    # crontab editor that happens to be reached from a site, and a mistyped line could take
    # out a neighbour's backup.
    listing = await cron_service.list_jobs(server)
    mine = cron_service.jobs_for_site(
        listing.get("users", []), site.domain, site.doc_root)
    if not any(j.get("raw") == body.raw_line and j.get("user") == body.user for j in mine):
        raise HTTPException(
            status_code=422,
            detail="That job does not belong to this site. Remove it from the server's "
                   "own Cron jobs screen if you meant to.")

    try:
        result = await cron_service.remove_job(
            server, user=body.user, raw_line=body.raw_line, expect=body.expect)
    except cron_service.CronError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await audit_service.audit(db, current_user, "cron.removed",
                              target_type="server", target_id=str(server.id),
                              meta={"user": body.user, "site": site.domain})
    return result
