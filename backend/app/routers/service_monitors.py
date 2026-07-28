"""Service monitors — discover what's installed, choose what to watch.

Discovery exists because an owner does not know their database unit is called
``mariadb``. Asking someone to type a unit name is asking them to already know the
answer they came here to find, so we look, and they pick from a list.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.server import Server
from app.models.service_monitor import ServiceMonitor
from app.models.user import User
from app.services import connection_manager, service_monitor_service as svc, team_service

router = APIRouter(prefix="/api", tags=["service-monitors"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class MonitorIn(BaseModel):
    unit: str = Field(max_length=128)
    label: str = Field(max_length=255)
    failure_threshold: int = Field(default=2, ge=1, le=10)
    auto_restart: bool = False
    max_restarts: int = Field(default=3, ge=1, le=10)
    restart_window_seconds: int = Field(default=1800, ge=300, le=86_400)
    is_active: bool = True


def _public(m: ServiceMonitor, server_name: str | None = None) -> dict:
    return {
        "id": str(m.id), "server_id": str(m.server_id), "server_name": server_name,
        "unit": m.unit, "label": m.label,
        "is_active": m.is_active, "status": m.current_status, "state": m.last_state,
        "last_checked": m.last_checked.isoformat() if m.last_checked else None,
        "last_error": m.last_error,
        "auto_restart": m.auto_restart, "max_restarts": m.max_restarts,
        "restart_window_seconds": m.restart_window_seconds,
        "restart_count": m.restart_count, "gave_up": m.gave_up,
        "last_restart_at": m.last_restart_at.isoformat() if m.last_restart_at else None,
        "failure_threshold": m.failure_threshold,
    }


@router.get("/service-monitors")
async def list_all(db: DBDep, current_user: CurrentUser) -> dict:
    """Every watched service across the servers the caller can reach."""
    servers = await team_service.accessible_servers(db, current_user)
    names = {s.id: s.name for s in servers}
    if not servers:
        return {"monitors": [], "count": 0, "down": 0}
    rows = (await db.execute(
        select(ServiceMonitor).where(ServiceMonitor.server_id.in_(list(names)))
        .order_by(ServiceMonitor.label)
    )).scalars().all()
    monitors = [_public(m, names.get(m.server_id)) for m in rows]
    return {"monitors": monitors, "count": len(monitors),
            "down": sum(1 for m in monitors if m["status"] == "down")}


@router.get("/servers/{server_id}/services/discover")
async def discover(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Read-only: which services this server actually has, and whether they're running."""
    server = await resolve_server(server_id, current_user, db)
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=422,
            detail="Service monitoring needs an SSH connection to this server.")
    try:
        out, _err, _code = await connection_manager.execute(server, svc.discovery_probe())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail=f"Could not reach {server.name}: {exc}") from exc

    found = svc.discovered(out or "")
    watched = {m.unit for m in (await db.execute(
        select(ServiceMonitor).where(ServiceMonitor.server_id == server.id)
    )).scalars().all()}
    for f in found:
        f["watched"] = f["unit"] in watched
    return {"server": server.name, "services": found, "count": len(found)}


@router.get("/servers/{server_id}/service-monitors")
async def list_for_server(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    server = await resolve_server(server_id, current_user, db)
    rows = (await db.execute(
        select(ServiceMonitor).where(ServiceMonitor.server_id == server.id)
        .order_by(ServiceMonitor.label)
    )).scalars().all()
    return {"monitors": [_public(m, server.name) for m in rows], "count": len(rows)}


@router.post("/servers/{server_id}/service-monitors", status_code=201)
async def create(server_id: str, body: MonitorIn, db: DBDep,
                 current_user: CurrentUser) -> dict:
    """Watch a service. Needs execute permission — it can restart things."""
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    try:
        unit = svc.valid_unit(body.unit)
    except svc.InvalidUnit as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing = (await db.execute(
        select(ServiceMonitor).where(ServiceMonitor.server_id == server.id,
                                     ServiceMonitor.unit == unit)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409,
                            detail=f"{body.label} is already being watched on this server.")

    m = ServiceMonitor(
        user_id=current_user.id, server_id=server.id, unit=unit,
        label=body.label.strip()[:255] or unit,
        failure_threshold=body.failure_threshold, auto_restart=body.auto_restart,
        max_restarts=body.max_restarts,
        restart_window_seconds=body.restart_window_seconds, is_active=body.is_active)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return _public(m, server.name)


async def _owned(monitor_id: str, db: AsyncSession, user: User) -> ServiceMonitor:
    m = await db.get(ServiceMonitor, monitor_id)
    if not m:
        raise HTTPException(status_code=404, detail="No such service monitor.")
    # Reached through the SERVER's access rules, not just ownership, so a team member
    # with rights to the server can manage its monitors — the same path everything else
    # in the product uses (Rule 7).
    await resolve_server(str(m.server_id), user, db, need_execute=True)
    return m


@router.put("/service-monitors/{monitor_id}")
async def update(monitor_id: str, body: MonitorIn, db: DBDep,
                 current_user: CurrentUser) -> dict:
    m = await _owned(monitor_id, db, current_user)
    m.label = body.label.strip()[:255] or m.unit
    m.failure_threshold = body.failure_threshold
    m.auto_restart = body.auto_restart
    m.max_restarts = body.max_restarts
    m.restart_window_seconds = body.restart_window_seconds
    m.is_active = body.is_active
    await db.commit()
    await db.refresh(m)
    return _public(m)


@router.post("/service-monitors/{monitor_id}/reset")
async def reset(monitor_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Clear a give-up. Used after fixing whatever kept crashing the service."""
    m = await _owned(monitor_id, db, current_user)
    m.gave_up = False
    m.restart_count = 0
    m.restart_window_started = None
    await db.commit()
    await db.refresh(m)
    return _public(m)


@router.delete("/service-monitors/{monitor_id}", status_code=204)
async def remove(monitor_id: str, db: DBDep, current_user: CurrentUser) -> None:
    m = await _owned(monitor_id, db, current_user)
    await db.delete(m)
    await db.commit()
