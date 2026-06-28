"""Commands router — history and log retrieval."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.command_log import CommandLog
from app.models.playbook import Playbook, PlaybookRun, UserScript
from app.models.server import Server
from app.models.user import User
from app.schemas.command import ActivityItem, CommandLogOut
from app.services.redis_service import get_redis
from app.workers.playbook_tasks import run_log_key

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
                failure_reason=run.failure_reason,
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


@router.get("/api/servers/{server_id}/active-runs")
async def list_active_runs(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Playbook/script runs still in progress on this server (recent only), so the
    run window can rejoin one instead of starting a duplicate (Update 17)."""
    await _own_server(server_id, db, current_user)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    rows = (
        await db.execute(
            select(PlaybookRun)
            .where(
                PlaybookRun.server_id == server_id,
                PlaybookRun.status == "running",
                PlaybookRun.started_at >= cutoff,
            )
            .order_by(PlaybookRun.started_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "playbook_id": str(r.playbook_id) if r.playbook_id else None,
            "user_script_id": str(r.user_script_id) if r.user_script_id else None,
            "started_at": r.started_at.isoformat() if r.started_at else None,
        }
        for r in rows
    ]


@router.get("/api/active-runs")
async def list_all_active_runs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """All of the user's playbook/script runs currently in progress (recent), across
    every server — the dashboard "running now" panel (Update 17, Phase 3)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    rows = (
        await db.execute(
            select(PlaybookRun, Server.name, Playbook.title, UserScript.title)
            .outerjoin(Server, PlaybookRun.server_id == Server.id)
            .outerjoin(Playbook, PlaybookRun.playbook_id == Playbook.id)
            .outerjoin(UserScript, PlaybookRun.user_script_id == UserScript.id)
            .where(
                PlaybookRun.user_id == current_user.id,
                PlaybookRun.status == "running",
                PlaybookRun.started_at >= cutoff,
            )
            .order_by(PlaybookRun.started_at.desc())
        )
    ).all()
    return [
        {
            "id": str(run.id),
            "server_id": str(run.server_id),
            "server_name": server_name or "server",
            "title": pb_title or us_title or "Playbook",
            "started_at": run.started_at.isoformat() if run.started_at else None,
        }
        for run, server_name, pb_title, us_title in rows
    ]


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


@router.post("/api/commands/{log_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_command(
    log_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Request cancellation of a running AI-chat command execution (durable path).
    Signals the worker (Redis flag) to stop, marks the log cancelled, and emits a
    final execution_complete so the tailing WebSocket resolves immediately."""
    log = (
        await db.execute(select(CommandLog).where(CommandLog.id == log_id))
    ).scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log not found")
    # Must be able to execute on the log's server to cancel it.
    await resolve_server(log.server_id, current_user, db, need_execute=True)
    if log.status != "running":
        return None  # not in progress — no-op

    redis = get_redis()
    await redis.setex(f"run:{log_id}:cancel", settings.EXECUTION_LOG_TTL, "1")
    log.status = "cancelled"
    await db.commit()
    key = run_log_key(str(log_id))
    await redis.rpush(key, json.dumps({"type": "output", "data": "⏹ Cancelled by user\n", "stream": "stdout"}))
    await redis.rpush(key, json.dumps({
        "type": "execution_complete", "log_id": str(log_id), "status": "cancelled",
        "explanation": "Cancelled by user.", "follow_up_suggestions": [],
    }))
    await redis.expire(key, settings.EXECUTION_LOG_TTL)
    return None


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
