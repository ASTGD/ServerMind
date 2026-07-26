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
    # Meter #2 (PRICING v2): the server cap.
    servers_used: int
    servers_limit: int


@router.get("/me", response_model=MyUsage)
async def my_usage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MyUsage:
    """Both plan meters for the signed-in user: Ally actions this month + servers."""
    g = await metering_service.gate(db, current_user)
    sg = await metering_service.servers_gate(db, current_user)
    return MyUsage(
        plan=(current_user.plan or "free"),
        used=g.used,
        limit=g.limit,
        resets_at=g.resets_at,
        enforced=g.enforced,
        servers_used=sg.used,
        servers_limit=sg.limit,
    )


@router.get("/retention")
async def my_retention(current_user: User = Depends(get_current_user)) -> dict:
    """How long this account's history is kept, and what Pro keeps.

    Includes the Pro figures so the comparison is honest, and the never-deleted list so
    retention does not read as "we throw your records away".
    """
    from app.services import retention_service

    return retention_service.describe(current_user.plan)


@router.get("/entitlements")
async def my_entitlements(current_user: User = Depends(get_current_user)) -> dict:
    """What this plan includes, so the UI can show a lock BEFORE a form is filled in.

    Served from ``entitlements.describe`` rather than duplicated in the frontend, so changing
    a plan never needs a matching frontend edit — and a lock can never disagree with the gate
    that actually refuses the request.
    """
    from app.services import entitlements

    return entitlements.describe(current_user)
