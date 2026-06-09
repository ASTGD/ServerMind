"""Commands router — history and log retrieval."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.command_log import CommandLog
from app.models.server import Server
from app.models.user import User
from app.schemas.command import CommandLogOut

router = APIRouter(tags=["commands"])


async def _own_server(server_id: uuid.UUID, db: AsyncSession, user: User) -> Server:
    """Resolve a server the user can access (owner or team member)."""
    return await resolve_server(server_id, user, db)


@router.get("/api/servers/{server_id}/history", response_model=list[CommandLogOut])
async def list_history(
    server_id: uuid.UUID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CommandLog]:
    """Return the last N command logs for a server."""
    await _own_server(server_id, db, current_user)
    result = await db.execute(
        select(CommandLog)
        .where(CommandLog.server_id == server_id)
        .order_by(CommandLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get("/api/commands/{log_id}", response_model=CommandLogOut)
async def get_log(
    log_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommandLog:
    """Get a single command log entry."""
    result = await db.execute(
        select(CommandLog).where(
            CommandLog.id == log_id,
            CommandLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log not found")
    return log


@router.delete("/api/commands/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_log(
    log_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a command log entry."""
    result = await db.execute(
        select(CommandLog).where(
            CommandLog.id == log_id,
            CommandLog.user_id == current_user.id,
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log not found")
    await db.delete(log)
    await db.commit()
