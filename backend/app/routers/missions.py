"""Missions router — mission history + detail (Ally Missions Phase 3).

Read-only: the mission LOOP runs over the WebSocket (start/resume/stop are chat-socket
messages). These endpoints expose the persisted record so the UI can show a history
list, a detail view, and detect a resumable (``interrupted``) mission. Scoped to the
signed-in user's own missions.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import mission_service

router = APIRouter(prefix="/api/missions", tags=["missions"])


@router.get("")
async def list_missions(
    server_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """The user's mission history (newest first); optionally filtered to one server."""
    missions = await mission_service.list_for_user(db, current_user, limit=limit, server_id=server_id)
    return [mission_service.to_dict(m) for m in missions]


@router.get("/{mission_id}")
async def get_mission(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """One mission with its full step transcript."""
    m = await mission_service.get_for_user(db, current_user, mission_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission_service.to_dict(m, include_steps=True)
