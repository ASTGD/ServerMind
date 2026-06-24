"""Playbooks router — browse, detail, and run history."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.playbook import Playbook, PlaybookRun
from app.models.user import User
from app.schemas.playbook import PlaybookOut, PlaybookDetailOut, PlaybookRunOut
from app.services.redis_service import get_redis
from app.workers.playbook_tasks import run_log_key

router = APIRouter(prefix="/api/playbooks", tags=["playbooks"])


@router.get("", response_model=list[PlaybookOut])
async def list_playbooks(
    os_family: str | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[Playbook]:
    """List all public/official playbooks with optional filters."""
    stmt = select(Playbook).where(Playbook.is_public == True)
    if os_family:
        from sqlalchemy import or_
        stmt = stmt.where(or_(Playbook.os_family == os_family, Playbook.os_family == "both"))
    if category:
        stmt = stmt.where(Playbook.category == category)
    if q:
        from sqlalchemy import or_
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Playbook.title.ilike(pattern),
                Playbook.description.ilike(pattern),
            )
        )
    stmt = stmt.order_by(Playbook.category, Playbook.title)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/categories")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[str]:
    """Return distinct playbook categories."""
    from sqlalchemy import distinct
    result = await db.execute(
        select(distinct(Playbook.category))
        .where(Playbook.is_public == True, Playbook.category != None)
        .order_by(Playbook.category)
    )
    return [row[0] for row in result.all()]


@router.get("/runs/{run_id}", response_model=PlaybookRunOut)
async def get_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PlaybookRun:
    """Get a single playbook run record."""
    result = await db.execute(
        select(PlaybookRun).where(
            PlaybookRun.id == run_id,
            PlaybookRun.user_id == current_user.id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Request cancellation of a running playbook execution. Signals the executor
    (Redis flag) to stop, marks the run cancelled, and emits a final message so a
    tailing WebSocket resolves immediately."""
    run = (
        await db.execute(select(PlaybookRun).where(PlaybookRun.id == run_id))
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    # Must be able to execute on the run's server to cancel it.
    await resolve_server(run.server_id, current_user, db, need_execute=True)
    if run.status not in ("running", "queued"):
        return None  # already finished — no-op

    redis = get_redis()
    await redis.setex(f"run:{run_id}:cancel", settings.EXECUTION_LOG_TTL, "1")
    run.status = "cancelled"
    run.completed_at = datetime.now(timezone.utc)
    await db.commit()
    key = run_log_key(str(run_id))
    await redis.rpush(key, json.dumps({"type": "output", "data": "⏹ Cancelled by user\n"}))
    await redis.rpush(key, json.dumps({"type": "complete", "run_id": str(run_id), "status": "cancelled"}))
    await redis.expire(key, settings.EXECUTION_LOG_TTL)
    return None


@router.get("/{playbook_id}", response_model=PlaybookDetailOut)
async def get_playbook(
    playbook_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Playbook:
    """Get a single playbook with full script content."""
    result = await db.execute(
        select(Playbook).where(Playbook.id == playbook_id, Playbook.is_public == True)
    )
    playbook = result.scalar_one_or_none()
    if not playbook:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    return playbook
