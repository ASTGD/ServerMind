"""Monitoring router — metrics history and alert rule CRUD."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.models.alert import Alert, ServerMetric
from app.models.server import Server
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.monitoring import AlertCreate, AlertOut, ServerMetricOut
from app.services import notification_service

router = APIRouter(prefix="/api", tags=["monitoring"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_server(server_id: str, user: User, db: AsyncSession) -> Server:
    """Resolve a server the user can access (owner or team member)."""
    return await resolve_server(server_id, user, db)


async def _get_alert(alert_id: str, user: User, db: AsyncSession) -> Alert:
    try:
        aid = uuid.UUID(alert_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Alert not found")
    row = await db.execute(
        select(Alert).where(
            Alert.id == aid,
            Alert.user_id == user.id,
        )
    )
    alert = row.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


_VALID_METRICS = {"cpu", "ram", "disk"}
_VALID_CONDITIONS = {"gt", "gte", "lt", "lte"}
_VALID_CHANNELS = {"email", "webhook", "slack"}


def _validate_alert_body(body: AlertCreate) -> None:
    if body.metric not in _VALID_METRICS:
        raise HTTPException(status_code=422, detail=f"metric must be one of {_VALID_METRICS}")
    if body.condition not in _VALID_CONDITIONS:
        raise HTTPException(status_code=422, detail=f"condition must be one of {_VALID_CONDITIONS}")
    if body.channel not in _VALID_CHANNELS:
        raise HTTPException(status_code=422, detail=f"channel must be one of {_VALID_CHANNELS}")
    if not body.channel_target.strip():
        raise HTTPException(status_code=422, detail="channel_target cannot be empty")
    if not (0 <= body.threshold <= 100):
        raise HTTPException(status_code=422, detail="threshold must be 0–100")


# ── Metrics history ───────────────────────────────────────────────────────────

@router.get("/servers/{server_id}/metrics/history", response_model=list[ServerMetricOut])
async def get_metrics_history(
    server_id: str,
    db: DBDep,
    current_user: CurrentUser,
    hours: int = Query(default=24, ge=1, le=168),
    limit: int = Query(default=288, ge=1, le=2016),
) -> list[ServerMetric]:
    """Return historical metric snapshots for a server.

    Default: last 24 h (up to 288 points at 5-min collection interval).
    Max: 168 h (7 days).
    """
    await _get_server(server_id, current_user, db)

    from datetime import datetime, timedelta, timezone
    since = datetime.now(tz=timezone.utc) - timedelta(hours=hours)

    rows = await db.execute(
        select(ServerMetric)
        .where(
            ServerMetric.server_id == uuid.UUID(server_id),
            ServerMetric.recorded_at >= since,
        )
        .order_by(ServerMetric.recorded_at.asc())
        .limit(limit)
    )
    return list(rows.scalars().all())


# ── Alert CRUD ─────────────────────────────────────────────────────────────────

@router.get("/servers/{server_id}/alerts", response_model=list[AlertOut])
async def list_alerts(
    server_id: str, db: DBDep, current_user: CurrentUser
) -> list[Alert]:
    """List all alert rules for a server."""
    await _get_server(server_id, current_user, db)
    rows = await db.execute(
        select(Alert)
        .where(Alert.server_id == uuid.UUID(server_id), Alert.user_id == current_user.id)
        .order_by(Alert.created_at.desc())
    )
    return list(rows.scalars().all())


@router.post("/servers/{server_id}/alerts", response_model=AlertOut, status_code=201)
async def create_alert(
    server_id: str, body: AlertCreate, db: DBDep, current_user: CurrentUser
) -> Alert:
    """Create a new alert rule."""
    await _get_server(server_id, current_user, db)
    _validate_alert_body(body)

    alert = Alert(
        server_id=uuid.UUID(server_id),
        user_id=current_user.id,
        metric=body.metric,
        condition=body.condition,
        threshold=body.threshold,
        channel=body.channel,
        channel_target=body.channel_target,
        is_active=True,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.put("/alerts/{alert_id}", response_model=AlertOut)
async def update_alert(
    alert_id: str, body: AlertCreate, db: DBDep, current_user: CurrentUser
) -> Alert:
    """Update an existing alert rule."""
    alert = await _get_alert(alert_id, current_user, db)
    _validate_alert_body(body)

    alert.metric = body.metric
    alert.condition = body.condition
    alert.threshold = body.threshold
    alert.channel = body.channel
    alert.channel_target = body.channel_target

    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/alerts/{alert_id}", status_code=204)
async def delete_alert(
    alert_id: str, db: DBDep, current_user: CurrentUser
) -> None:
    """Delete an alert rule."""
    alert = await _get_alert(alert_id, current_user, db)
    await db.delete(alert)
    await db.commit()


@router.post("/alerts/{alert_id}/toggle", response_model=AlertOut)
async def toggle_alert(
    alert_id: str, db: DBDep, current_user: CurrentUser
) -> Alert:
    """Toggle an alert rule active/inactive."""
    alert = await _get_alert(alert_id, current_user, db)
    alert.is_active = not alert.is_active
    await db.commit()
    await db.refresh(alert)
    return alert


@router.post("/alerts/{alert_id}/test", status_code=202)
async def test_alert(
    alert_id: str, db: DBDep, current_user: CurrentUser
) -> dict[str, str]:
    """Send a test notification for an alert rule.

    Uses a dummy value of 99.9 so the message is obviously a test.
    """
    alert = await _get_alert(alert_id, current_user, db)
    srv_row = await db.execute(select(Server).where(Server.id == alert.server_id))
    server = srv_row.scalar_one_or_none()
    server_name = server.name if server else "Unknown Server"

    asyncio.create_task(
        notification_service.fire_alert(alert, f"[TEST] {server_name}", 99.9)
    )
    return {"status": "queued", "message": "Test notification sent"}
