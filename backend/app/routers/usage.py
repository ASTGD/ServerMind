"""Usage router — the user's AI-action allowance (docs/AI-METERING.md, Brick 2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import metering_service

router = APIRouter(prefix="/api/usage", tags=["usage"])


class MyUsage(BaseModel):
    plan: str
    used: int
    limit: int
    resets_at: str
    enforced: bool


@router.get("/me", response_model=MyUsage)
async def my_usage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MyUsage:
    """This month's Ally-action usage for the signed-in user ("214 of 1,000")."""
    g = await metering_service.gate(db, current_user)
    return MyUsage(
        plan=(current_user.plan or "free"),
        used=g.used,
        limit=g.limit,
        resets_at=g.resets_at,
        enforced=g.enforced,
    )
