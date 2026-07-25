"""Uptime monitors — CRUD, on-demand check, and history.

Monitors are user-owned. A monitor may be tied to a server (so a failure points at the
box to fix), in which case the caller must have access to that server.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.uptime import UptimeCheck, UptimeMonitor
from app.models.user import User
from app.services import uptime_service
from app.workers import uptime_worker

router = APIRouter(prefix="/api", tags=["uptime"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

_INTERVALS = {60, 300, 900, 1800, 3600}


class MonitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=1000)
    server_id: uuid.UUID | None = None
    method: str = "GET"
    expected_status: int = Field(default=200, ge=100, le=599)
    expected_keyword: str | None = Field(default=None, max_length=255)
    interval_seconds: int = 300
    timeout_seconds: int = Field(default=15, ge=1, le=60)
    failure_threshold: int = Field(default=2, ge=1, le=10)
    is_active: bool = True
    channel: str | None = None
    channel_target: str | None = Field(default=None, max_length=500)


class MonitorUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    url: str | None = Field(default=None, max_length=1000)
    method: str | None = None
    expected_status: int | None = Field(default=None, ge=100, le=599)
    expected_keyword: str | None = Field(default=None, max_length=255)
    interval_seconds: int | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    failure_threshold: int | None = Field(default=None, ge=1, le=10)
    is_active: bool | None = None
    channel: str | None = None
    channel_target: str | None = Field(default=None, max_length=500)


class MonitorOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    server_id: uuid.UUID | None = None
    name: str
    url: str
    method: str
    expected_status: int
    expected_keyword: str | None = None
    interval_seconds: int
    timeout_seconds: int
    failure_threshold: int
    is_active: bool
    current_status: str
    last_checked: datetime | None = None
    last_status_change: datetime | None = None
    last_response_ms: int | None = None
    last_error: str | None = None
    channel: str | None = None
    channel_target: str | None = None
    created_at: datetime
    # Computed
    uptime_24h: float = 100.0
    uptime_30d: float = 100.0


class CheckOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    status: str
    http_status: int | None = None
    response_ms: int | None = None
    error: str | None = None
    checked_at: datetime


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=404, detail="Monitor not found")


def _validate(interval: int | None, method: str | None, url: str | None) -> None:
    if interval is not None and interval not in _INTERVALS:
        raise HTTPException(
            status_code=422, detail=f"interval_seconds must be one of {sorted(_INTERVALS)}"
        )
    if method is not None and method.upper() not in {"GET", "HEAD", "POST"}:
        raise HTTPException(status_code=422, detail="method must be GET, HEAD or POST")
    if url is not None and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="url must start with http:// or https://")


async def _get_monitor(monitor_id: str, user: User, db: AsyncSession) -> UptimeMonitor:
    row = await db.execute(
        select(UptimeMonitor).where(
            UptimeMonitor.id == _uuid(monitor_id), UptimeMonitor.user_id == user.id
        )
    )
    monitor = row.scalar_one_or_none()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


async def _with_uptime(db: AsyncSession, monitors: list[UptimeMonitor]) -> list[MonitorOut]:
    """Attach 24h / 30d uptime percentages, computed in two grouped queries (no N+1)."""
    out = [MonitorOut.model_validate(m) for m in monitors]
    if not monitors:
        return out
    ids = [m.id for m in monitors]
    now = datetime.now(tz=timezone.utc)

    for window, field in ((timedelta(hours=24), "uptime_24h"), (timedelta(days=30), "uptime_30d")):
        rows = (await db.execute(
            select(
                UptimeCheck.monitor_id,
                func.count().label("total"),
                func.count().filter(UptimeCheck.status == "up").label("up"),
            )
            .where(UptimeCheck.monitor_id.in_(ids), UptimeCheck.checked_at >= now - window)
            .group_by(UptimeCheck.monitor_id)
        )).all()
        stats = {r[0]: (r[2], r[1]) for r in rows}
        for item in out:
            up, total = stats.get(item.id, (0, 0))
            setattr(item, field, uptime_service.uptime_percentage(up, total))
    return out


@router.get("/uptime/monitors", response_model=list[MonitorOut])
async def list_monitors(
    db: DBDep, current_user: CurrentUser, server_id: str | None = Query(default=None)
) -> list[MonitorOut]:
    """Your uptime monitors, optionally filtered to one server."""
    q = select(UptimeMonitor).where(UptimeMonitor.user_id == current_user.id)
    if server_id:
        q = q.where(UptimeMonitor.server_id == _uuid(server_id))
    monitors = list((await db.execute(q.order_by(UptimeMonitor.created_at.desc()))).scalars().all())
    return await _with_uptime(db, monitors)


@router.post("/uptime/monitors", response_model=MonitorOut, status_code=201)
async def create_monitor(body: MonitorCreate, db: DBDep, current_user: CurrentUser) -> MonitorOut:
    """Add a monitor. Checked immediately so the user sees a real result at once, rather
    than an 'unknown' badge until the next sweep."""
    _validate(body.interval_seconds, body.method, body.url)
    if body.server_id:
        await resolve_server(str(body.server_id), current_user, db)

    monitor = UptimeMonitor(
        user_id=current_user.id,
        server_id=body.server_id,
        name=body.name,
        url=body.url,
        method=(body.method or "GET").upper(),
        expected_status=body.expected_status,
        expected_keyword=body.expected_keyword or None,
        interval_seconds=body.interval_seconds,
        timeout_seconds=body.timeout_seconds,
        failure_threshold=body.failure_threshold,
        is_active=body.is_active,
        channel=body.channel,
        channel_target=body.channel_target,
    )
    db.add(monitor)
    await db.commit()
    await db.refresh(monitor)

    try:
        await uptime_worker._check_one(monitor.id)
        await db.refresh(monitor)
    except Exception as exc:  # noqa: BLE001 — a failed first probe must not fail creation
        logger.warning("First uptime check failed for %s: %s", monitor.id, exc)

    return (await _with_uptime(db, [monitor]))[0]


@router.put("/uptime/monitors/{monitor_id}", response_model=MonitorOut)
async def update_monitor(
    monitor_id: str, body: MonitorUpdate, db: DBDep, current_user: CurrentUser
) -> MonitorOut:
    monitor = await _get_monitor(monitor_id, current_user, db)
    data = body.model_dump(exclude_unset=True)
    _validate(data.get("interval_seconds"), data.get("method"), data.get("url"))
    if "method" in data and data["method"]:
        data["method"] = data["method"].upper()

    for field, value in data.items():
        setattr(monitor, field, value)
    await db.commit()
    await db.refresh(monitor)
    return (await _with_uptime(db, [monitor]))[0]


@router.delete("/uptime/monitors/{monitor_id}", status_code=204)
async def delete_monitor(monitor_id: str, db: DBDep, current_user: CurrentUser) -> None:
    monitor = await _get_monitor(monitor_id, current_user, db)
    await db.delete(monitor)
    await db.commit()


@router.post("/uptime/monitors/{monitor_id}/check", response_model=MonitorOut)
async def check_now(monitor_id: str, db: DBDep, current_user: CurrentUser) -> MonitorOut:
    """Probe this monitor right now."""
    monitor = await _get_monitor(monitor_id, current_user, db)
    await uptime_worker._check_one(monitor.id)
    await db.refresh(monitor)
    return (await _with_uptime(db, [monitor]))[0]


@router.get("/uptime/monitors/{monitor_id}/history", response_model=list[CheckOut])
async def monitor_history(
    monitor_id: str, db: DBDep, current_user: CurrentUser,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[CheckOut]:
    """Recent check results, newest first."""
    monitor = await _get_monitor(monitor_id, current_user, db)
    rows = (await db.execute(
        select(UptimeCheck)
        .where(UptimeCheck.monitor_id == monitor.id)
        .order_by(UptimeCheck.checked_at.desc())
        .limit(limit)
    )).scalars().all()
    return [CheckOut.model_validate(r) for r in rows]
