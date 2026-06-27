"""Notifications router — the in-app bell (Update 17, Phase 2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationList

router = APIRouter(tags=["notifications"])


@router.get("/api/notifications", response_model=NotificationList)
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """The user's recent notifications (newest first) + unread count."""
    items = (
        await db.execute(
            select(Notification)
            .where(Notification.user_id == current_user.id)
            .order_by(Notification.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    unread = (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == current_user.id, Notification.read == False)  # noqa: E712
        )
    ).scalar_one()
    return {"items": list(items), "unread": unread}


@router.post("/api/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Mark all of the user's notifications as read."""
    await db.execute(
        sa_update(Notification)
        .where(Notification.user_id == current_user.id, Notification.read == False)  # noqa: E712
        .values(read=True)
    )
    await db.commit()
