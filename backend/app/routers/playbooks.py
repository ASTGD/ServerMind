"""Playbooks router — browse, detail, and run history."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.playbook import Playbook, PlaybookRun
from app.models.user import User
from app.schemas.playbook import PlaybookOut, PlaybookDetailOut, PlaybookRunOut

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
