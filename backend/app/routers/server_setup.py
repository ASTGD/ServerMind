"""Set up a fresh server — the one-button path.

Two doors lead here. The form posts directly; Ally posts the same thing after working out
what the customer meant. Neither runs the installers itself, so there is one behaviour to
reason about and one place a guard can be missed.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.server_setup import ServerSetup
from app.models.user import User
from app.services import audit_service, installed_service, setup_service
from app.workers import setup_runner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/servers/{server_id}/setup", tags=["setup"])

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class StartBody(BaseModel):
    purpose: str = Field(default="websites", max_length=30)
    timezone: str = Field(default="UTC", max_length=64)
    monitoring: bool = True
    # Both default to what the setup did before the choice existed, so an older client
    # that does not send them gets an identical build.
    php_version: str = Field(default="default", max_length=10)
    db_engine: str = Field(default="mariadb", max_length=20)
    # The deliberate override for "yes, I know it already has things on it".
    force: bool = False


def _public(s: ServerSetup) -> dict:
    steps = s.steps or []
    done = sum(1 for r in steps if r.get("state") in ("done", "skipped"))
    return {
        "id": str(s.id), "purpose": s.purpose, "status": s.status,
        "steps": steps, "current": s.current,
        "failed_step": s.failed_step, "message": s.message,
        "progress": setup_service.progress(done, len(steps)),
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "finished_at": s.finished_at.isoformat() if s.finished_at else None,
    }


async def _latest(server, db: AsyncSession) -> ServerSetup | None:
    """The most recent setup — but only if it describes THIS machine.

    A setup that finished before the host key was replaced ran on hardware that is gone,
    so reading it as the current state tells a customer their rebuilt server is already
    set up and offers them nothing to do about it.

    The rule lives HERE, at the read, rather than at each caller. It was written at one
    call site first and the setup panel simply never got it — a guard that has to be
    remembered is a guard that gets missed, which is the same fault one level down.
    """
    from app.services import server_role

    row = (await db.execute(
        select(ServerSetup).where(ServerSetup.server_id == server.id)
        .order_by(ServerSetup.started_at.desc()).limit(1))).scalar_one_or_none()
    if row and not server_role.setup_applies(
            row.finished_at, getattr(server, "identity_changed_at", None)):
        return None
    return row


@router.get("/role")
async def role(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Is ServerAlly the control panel for this server, or is a real panel?

    Lives beside setup because it reads the same facts, and because the answer decides
    whether setup should be offered at all: running it installs nginx, PHP and a database,
    which shuts the control-panel door for good.

    Every field is derived. Nothing here is stored, so the page cannot disagree with the
    machine — see `server_role`.
    """
    from sqlalchemy import func

    from app.models.site import Site
    from app.services import server_role

    server = await resolve_server(server_id, current_user, db)
    latest = await _latest(server, db)
    site_count = (await db.execute(
        select(func.count()).select_from(Site)
        .where(Site.server_id == server.id, Site.is_present == True)  # noqa: E712
    )).scalar() or 0

    out = server_role.decide(
        connection_type=server.connection_type,
        panel_type=server.panel_type,
        setup_done=bool(latest and latest.status == "done"),
        setup_running=bool(latest and latest.status == "running"),
        site_count=int(site_count),
    )
    # What the customer would be choosing between, read from the playbooks this deployment
    # actually has rather than from a list written out again here — an installer we do not
    # ship must never appear as a door.
    out["panels"] = await _panel_installers(db) if out["can_choose"] else []

    # A server is only "fresh" if we LOOKED. Somebody adds a box they have been using for a
    # year, and telling them it is a clean machine — while it runs Docker, or nginx, or a
    # database — is the page being confidently wrong about the one thing it is for.
    if out["can_choose"]:
        looked = await _whats_on_it(server)
        out.update(looked)

        # "What is on the machine beats what we believe about it" was already the rule, but
        # it only ever read a stored column, which OS detection fills in when a server is
        # added. That leaves one hole, and it is on the path this page created: somebody
        # picks "Install a control panel", it installs, and nothing records it until they
        # happen to press Detect system — so the app keeps offering the fork on a server
        # that answered it.
        #
        # Recorded rather than merely returned, so there is ONE source of truth. Returning
        # it alone would leave the menu and the site guards reading the empty column and
        # the page reading the scan — two opinions about the same machine.
        seen = (looked.get("found") or {}).get("panels") or []
        if seen and not server.panel_type:
            server.panel_type = seen[0].strip().lower()
            server.category = "hosting"   # what OS detection does with the same finding
            await db.commit()
            await db.refresh(server)
            out.update(server_role.decide(
                connection_type=server.connection_type,
                panel_type=server.panel_type,
                setup_done=False, site_count=0,
            ))
            out["panels"] = []
    return out


async def _whats_on_it(server) -> dict:
    """A live look at the machine, for the one page where the answer changes the decision.

    Best-effort by construction: a server that cannot be reached still gets its two doors,
    with the page saying honestly that it could not look rather than implying the box is
    empty. One SSH round trip, on a page each server shows once.
    """
    from app.services import server_role

    try:
        found = await installed_service.scan_server(server)
    except Exception:  # noqa: BLE001 - unreachable, refused, timed out: all the same here
        logger.info("Start-here scan failed for %s", server.id, exc_info=True)
        return {"found": None, "is_clean": None, "scan_failed": True}

    shown = {k: found.get(k) for k in
             ("os", "web_servers", "databases", "containers", "runtimes", "panels")}
    return {"found": shown, "is_clean": server_role.is_fresh(found), "scan_failed": False}


async def _panel_installers(db: AsyncSession) -> list[dict]:
    from app.models.playbook import Playbook

    rows = (await db.execute(
        select(Playbook).where(Playbook.category == "control-panel",
                               Playbook.is_official == True)  # noqa: E712
        .order_by(Playbook.title)
    )).scalars().all()
    return [{"id": str(p.id), "slug": p.slug, "title": p.title,
             "description": p.description} for p in rows]


@router.get("")
async def status(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """What can be set up here, and how the last attempt went."""
    server = await resolve_server(server_id, current_user, db)
    latest = await _latest(server, db)

    options, blocked = [], ""
    try:
        setup_service.check_server(server)
    except setup_service.SetupRefused as exc:
        blocked = str(exc)
    for key in setup_service.PURPOSES:
        options.append(setup_service.summarise(setup_service.build_recipe(
            key, ssh_port=server.port or 22)))

    # The screen draws its dropdowns from these rather than from a copy of its own, so an
    # option can never be shown that `start` then refuses.
    return {"options": options, "blocked": blocked,
            "php_choices": [dict(c) for c in setup_service.PHP_CHOICES],
            "db_choices": [dict(c) for c in setup_service.DB_CHOICES],
            "os_type": (server.os_type or "").strip().lower(),
            "already_set_up": bool(latest and latest.status == "done"),
            "latest": _public(latest) if latest else None}


@router.post("", status_code=202)
async def start(server_id: str, body: StartBody, request: Request,
                db: DBDep, current_user: CurrentUser) -> dict:
    server = await resolve_server(server_id, current_user, db, need_execute=True)

    running = await _latest(server, db)
    if running and running.status == "running":
        raise HTTPException(
            status_code=409,
            detail="This server is already being set up. Watch it on the server page.")

    # Look at the machine before touching it. A server with a control panel, or one already
    # serving websites, is the case where "set up" quietly means "break".
    facts: dict = {}
    try:
        scan = await installed_service.scan_server(server)
        facts = scan if scan.get("supported") else {}
    except Exception:  # noqa: BLE001
        facts = {}      # unreadable is not proof of anything; the panel_type check still runs
    try:
        setup_service.check_server(server, installed=facts, force=body.force)
        # Checked against the REAL operating system, not the one the browser believed it
        # had. Debian genuinely cannot install MySQL, and finding that out mid-install
        # costs a rebuilt server rather than a click.
        setup_service.check_choices(body.php_version, body.db_engine,
                                    os_type=(server.os_type or ""))
        recipe = setup_service.build_recipe(
            body.purpose, ssh_port=server.port or 22,
            timezone=body.timezone, monitoring=body.monitoring,
            login_user=server.username or "root",
            auth_type=server.auth_type or "password",
            php_version=body.php_version, db_engine=body.db_engine)
    except setup_service.SetupRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    setup = ServerSetup(
        server_id=server.id, user_id=current_user.id, purpose=recipe.key,
        status="running", current=0,
        steps=[{"label": s.label, "slug": s.slug, "optional": s.optional,
                "state": "pending"} for s in recipe.steps])
    db.add(setup)
    await db.commit()
    await db.refresh(setup)

    await setup_runner.start(setup.id, recipe.steps, server)
    await audit_service.audit(db, current_user, "server.setup_started",
                              target_type="server", target_id=server_id,
                              meta={"purpose": recipe.key, "forced": body.force,
                                    "php": body.php_version, "db": body.db_engine},
                              request=request)
    logger.info("Server setup %s started on %s (%s)", setup.id, server.name, recipe.key)
    return _public(setup)


@router.post("/stop")
async def stop(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Stop after the current step.

    Deliberately not a kill: cutting an `apt install` mid-flight leaves a half-configured
    package that is harder to recover from than one extra completed step.
    """
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    latest = await _latest(server, db)
    if not latest or latest.status != "running":
        raise HTTPException(status_code=409, detail="Nothing is running on this server.")
    latest.status = "stopped"
    latest.message = ("Stopped. The step that was already running will finish; nothing "
                      "after it starts.")
    await db.commit()
    await db.refresh(latest)
    return _public(latest)
