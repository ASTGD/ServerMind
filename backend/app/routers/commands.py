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
from app.models.playbook import Playbook, PlaybookRun, UserScript
from app.models.server import Server
from app.models.user import User
from app.schemas.command import ActivityItem, CommandLogOut

router = APIRouter(tags=["commands"])


async def _own_server(server_id: uuid.UUID, db: AsyncSession, user: User) -> Server:
    """Resolve a server the user can access (owner or team member)."""
    return await resolve_server(server_id, user, db)


@router.get("/api/activity", response_model=list[ActivityItem])
async def list_activity(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ActivityItem]:
    """Unified recent activity (AI commands + playbook/script runs) for the user,
    newest first."""
    items: list[ActivityItem] = []

    cmd_rows = (
        await db.execute(
            select(CommandLog)
            .where(CommandLog.user_id == current_user.id)
            .order_by(CommandLog.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    for c in cmd_rows:
        items.append(
            ActivityItem(
                id=c.id,
                kind="command",
                server_id=c.server_id,
                title=c.user_input or "Command",
                status=c.status,
                risk_level=c.risk_level,
                duration_ms=c.execution_ms,
                created_at=c.created_at,
            )
        )

    run_rows = (
        await db.execute(
            select(PlaybookRun, Playbook.title, UserScript.title)
            .outerjoin(Playbook, PlaybookRun.playbook_id == Playbook.id)
            .outerjoin(UserScript, PlaybookRun.user_script_id == UserScript.id)
            .where(PlaybookRun.user_id == current_user.id)
            .order_by(PlaybookRun.started_at.desc())
            .limit(limit)
        )
    ).all()
    for run, pb_title, us_title in run_rows:
        duration_ms = None
        if run.completed_at and run.started_at:
            duration_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)
        items.append(
            ActivityItem(
                id=run.id,
                kind="playbook",
                server_id=run.server_id,
                title=pb_title or us_title or "Script",
                status=run.status,
                duration_ms=duration_ms,
                created_at=run.started_at,
            )
        )

    items.sort(key=lambda x: x.created_at, reverse=True)
    return items[:limit]


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
