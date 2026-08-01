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
from app.services import playbook_service, site_service, team_service

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


class InstallIn(BaseModel):
    """What to put on a site that already exists."""
    site_type: str
    variables: dict[str, str] = {}


@router.get("/sites/{site_id}")
async def get_site(site_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """One site, with the server it lives on.

    Its own page reads this rather than picking a row out of the list, so the page works
    when it is opened directly from a link or a bookmark — which is how someone returns to
    a site they were told about.
    """
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

    try:
        site, run_id, script = await site_service.install(
            db, server, current_user, site,
            site_type=body.site_type, variables=body.variables)
    except (site_service.SiteError, playbook_service.UnresolvedVariables) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Enqueued after the commit inside install(), so the worker can always find the run.
    run_playbook_task.delay(run_id, str(server.id), script)
    await audit_service.audit(db, current_user, "site.installed",
                              target_type="server", target_id=str(server.id),
                              meta={"domain": site.domain, "type": body.site_type})
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
    site.status = "installing"
    site.install_error = None
    await db.commit()
    await db.refresh(run)

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
    return {
        "jobs": cron_service.jobs_for_site(listing.get("users", []), site.domain, site.doc_root),
        "reachable": listing.get("reachable", False),
        "server_id": str(server.id),
    }
