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


async def _latest(server_id, db: AsyncSession) -> ServerSetup | None:
    return (await db.execute(
        select(ServerSetup).where(ServerSetup.server_id == server_id)
        .order_by(ServerSetup.started_at.desc()).limit(1))).scalar_one_or_none()


@router.get("")
async def status(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """What can be set up here, and how the last attempt went."""
    server = await resolve_server(server_id, current_user, db)
    latest = await _latest(server.id, db)

    options, blocked = [], ""
    try:
        setup_service.check_server(server)
    except setup_service.SetupRefused as exc:
        blocked = str(exc)
    for key in setup_service.PURPOSES:
        options.append(setup_service.summarise(setup_service.build_recipe(
            key, ssh_port=server.port or 22)))

    return {"options": options, "blocked": blocked,
            "already_set_up": bool(latest and latest.status == "done"),
            "latest": _public(latest) if latest else None}


@router.post("", status_code=202)
async def start(server_id: str, body: StartBody, request: Request,
                db: DBDep, current_user: CurrentUser) -> dict:
    server = await resolve_server(server_id, current_user, db, need_execute=True)

    running = await _latest(server.id, db)
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
        recipe = setup_service.build_recipe(
            body.purpose, ssh_port=server.port or 22,
            timezone=body.timezone, monitoring=body.monitoring)
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
                              meta={"purpose": recipe.key, "forced": body.force},
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
    latest = await _latest(server.id, db)
    if not latest or latest.status != "running":
        raise HTTPException(status_code=409, detail="Nothing is running on this server.")
    latest.status = "stopped"
    latest.message = ("Stopped. The step that was already running will finish; nothing "
                      "after it starts.")
    await db.commit()
    await db.refresh(latest)
    return _public(latest)
