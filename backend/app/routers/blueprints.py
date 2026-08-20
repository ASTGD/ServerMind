"""Blueprints — start, watch and stop a ready-made long job.

Start returns immediately with the run id; the run itself is a background task writing to
`blueprint_runs` — the pattern every long job here follows, because an HTTP request (and
later an MCP tool call) must never wait on a fifteen-minute job.
"""
from __future__ import annotations

import logging

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.blueprint import BlueprintRun
from app.services import audit_service, blueprint_service
from app.workers import blueprint_runner

router = APIRouter(prefix="/api", tags=["blueprints"])
DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
logger = logging.getLogger(__name__)


class StartIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    inputs: dict = Field(default_factory=dict)


def _serialize(run: BlueprintRun, server_name: str | None = None) -> dict:
    total = len(run.steps or [])
    done = sum(1 for s in (run.steps or []) if s.get("state") in ("done", "skipped", "waiting"))
    return {
        "id": str(run.id),
        "server_id": str(run.server_id),
        "server_name": server_name,
        "key": run.blueprint_key,
        "title": run.title,
        "inputs": run.inputs or {},
        "status": run.status,
        "current": run.current,
        "steps": run.steps or [],
        "steps_done": done,
        "steps_total": total,
        "message": run.message,
        "found": run.found or [],
        "left_for_you": run.left_for_you or [],
        "source": run.source,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


@router.get("/blueprints")
async def list_blueprints(current_user: CurrentUser) -> list[dict]:
    """The catalogue: what each blueprint does, needs, and will not do."""
    return [blueprint_service.describe(bp)
            for bp in blueprint_service.CATALOGUE.values()]


@router.post("/servers/{server_id}/blueprints", status_code=201)
async def start_blueprint(server_id: str, body: StartIn,
                          db: DBDep, current_user: CurrentUser) -> dict:
    """Start a blueprint. A missing input is ASKED FOR (422 naming it), never guessed —
    a guessed domain is a website nobody wanted."""
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    try:
        bp = blueprint_service.get(body.key)
        inputs = blueprint_service.check_inputs(bp, body.inputs)
        blueprint_service.check_server(bp, server)
    except blueprint_service.BlueprintError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # One at a time per server. Two blueprints fighting over one machine — both running
    # installers, both editing nginx — is a state nobody can reason about.
    busy = (await db.execute(select(BlueprintRun).where(
        BlueprintRun.server_id == server.id,
        BlueprintRun.status == "running"))).scalars().first()
    if busy is not None:
        raise HTTPException(status_code=409, detail=(
            f"'{busy.title}' is already running on this server. "
            "Wait for it to finish, or stop it first."))

    run = BlueprintRun(
        user_id=current_user.id, server_id=server.id, blueprint_key=bp.key,
        title=f"{bp.title.split(' on ')[0]} — {inputs.get('domain', server.name)}",
        inputs=inputs, status="running",
        steps=blueprint_service.build_steps(bp, inputs))
    db.add(run)
    await db.commit()
    await db.refresh(run)

    await blueprint_runner.start(run.id, server, current_user.id, inputs)
    await audit_service.audit(db, current_user, "blueprint.started",
                              target_type="server", target_id=str(server.id),
                              meta={"blueprint": bp.key, "run_id": str(run.id),
                                    "inputs": inputs})
    return _serialize(run, server.name)


@router.get("/blueprints/runs")
async def list_runs(db: DBDep, current_user: CurrentUser,
                    server_id: str | None = Query(default=None),
                    limit: int = Query(default=30, ge=1, le=100)) -> list[dict]:
    """This account's runs, running first then newest."""
    from app.models.server import Server

    q = select(BlueprintRun, Server.name).join(
        Server, Server.id == BlueprintRun.server_id, isouter=True
    ).where(BlueprintRun.user_id == current_user.id)
    if server_id:
        q = q.where(BlueprintRun.server_id == server_id)
    rows = (await db.execute(q.order_by(BlueprintRun.created_at.desc()).limit(limit))).all()
    out = [_serialize(r, name) for r, name in rows]
    out.sort(key=lambda r: (r["status"] != "running", r["created_at"] or ""), reverse=False)
    return out


@router.get("/blueprints/runs/{run_id}")
async def get_run(run_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    from app.models.server import Server

    run = await db.get(BlueprintRun, run_id)
    if run is None or str(run.user_id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="No such run.")
    server = await db.get(Server, run.server_id)
    return _serialize(run, server.name if server else None)


@router.post("/blueprints/runs/{run_id}/stop")
async def stop_run(run_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Refuses everything further. Cannot undo what already ran — the message says so."""
    run = await db.get(BlueprintRun, run_id)
    if run is None or str(run.user_id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="No such run.")
    await resolve_server(str(run.server_id), current_user, db, need_execute=True)
    await blueprint_runner.stop(db, run)
    await audit_service.audit(db, current_user, "blueprint.stopped",
                              target_type="server", target_id=str(run.server_id),
                              meta={"run_id": str(run.id)})
    return _serialize(run)
