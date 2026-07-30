"""Notification channels — where the customer wants to be told things.

Every response is built by `channel_service.public`, an explicit allowlist. A Slack webhook
URL and a Telegram bot token are credentials, not settings, and must never leave the server
— the same rule as server credentials and backup destinations.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.notification_channel import NotificationChannel
from app.models.user import User
from app.services import audit_service, channel_service
from app.services.channel_service import ChannelError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/channels", tags=["channels"])

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class ChannelIn(BaseModel):
    kind: str
    label: str = Field(min_length=1, max_length=80)
    config: dict[str, Any]


async def _own(db: AsyncSession, user: User, channel_id: str) -> NotificationChannel:
    """Fetch a channel the caller owns, or 404.

    404 rather than 403 for someone else's channel: a different status would confirm the
    id exists, which is a small leak with no upside.
    """
    row = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.id == channel_id,
            NotificationChannel.user_id == user.id,
        )
    )
    ch = row.scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=404, detail="That channel does not exist.")
    return ch


@router.get("")
async def list_channels(db: DBDep, current_user: CurrentUser) -> list[dict]:
    rows = await channel_service.list_for_user(db, current_user.id)
    return [channel_service.public(c) for c in rows]


@router.post("", status_code=201)
async def create_channel(body: ChannelIn, db: DBDep, current_user: CurrentUser) -> dict:
    try:
        ch = await channel_service.create(
            db, current_user.id, kind=body.kind, label=body.label, config=body.config)
    except ChannelError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await audit_service.audit(db, current_user, "channel.created",
                              target_type="channel", target_id=str(ch.id),
                              meta={"kind": ch.kind, "label": ch.label})
    return channel_service.public(ch)


@router.post("/{channel_id}/test")
async def test_channel(channel_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Prove the channel actually reaches somebody.

    The point of the whole feature: a channel is unverified until a real message has
    arrived, because alerting that silently goes nowhere is worse than none at all.
    """
    ch = await _own(db, current_user, channel_id)
    try:
        await channel_service.send_test(db, ch)
    except ChannelError as exc:
        # 422, not 500 — nothing is broken on our side; the channel's settings are wrong,
        # and the message says which.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return channel_service.public(ch)


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(channel_id: str, db: DBDep, current_user: CurrentUser) -> None:
    ch = await _own(db, current_user, channel_id)
    await audit_service.audit(db, current_user, "channel.deleted",
                              target_type="channel", target_id=str(ch.id),
                              meta={"kind": ch.kind, "label": ch.label})
    await channel_service.delete(db, ch)
