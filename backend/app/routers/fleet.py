"""Fleet router — proactive fleet intelligence (Ally's "what needs attention").

Read-only + cheap (no AI, no SSH): analyzes the data ServerAlly already collects into
per-server health scores + ranked, plain-English findings, each with a one-click
action. Scoped to the signed-in user's accessible servers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import fleet_service, team_service

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


@router.get("/health")
async def fleet_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Every accessible server, worst-first, with a health score and ranked findings."""
    servers = await team_service.accessible_servers(db, current_user)
    fleet = await fleet_service.analyze_fleet(db, servers)
    return {
        "servers": [fleet_service.to_dict(h) for h in fleet],
        "summary": fleet_service.summarize(fleet),
    }
