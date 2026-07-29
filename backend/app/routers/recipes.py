"""Recipes router — the one-click Mission gallery (read-only).

A Recipe is a goal-oriented, mission-mode skill promoted into a browsable gallery
(see docs/ALLY-RECIPES.md). This endpoint just lists the eligible skills and their
form variables; the frontend fills the variables into ``goal_template`` and sends the
resulting sentence through the normal chat → mission-offer → Start pipeline. There is
deliberately no "run recipe" endpoint here — nothing bypasses the chat/mission engine,
so all per-step safety validation, the verification gate, budgets, and persistence keep
working exactly as already built.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import skill_service

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


class RecipeVariable(BaseModel):
    name: str
    required: bool
    default: str = ""


class RecipeOut(BaseModel):
    slug: str
    title: str
    summary: str
    icon: str
    os_family: str
    budget: int
    variables: list[RecipeVariable]
    goal_template: str


@router.get("", response_model=list[RecipeOut])
async def list_recipes(
    os: str | None = Query(default=None, description="target server os_type to gate against"),
    server_id: str | None = Query(default=None,
                                  description="gate against a specific server as well"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RecipeOut]:
    """List goal-oriented recipes, gated against the target the customer has chosen.

    Passing a server gates on what that machine actually is, not just its OS — two
    recipes can answer "host a website" and only one of them applies to a server with a
    control panel. The same rule the chat router uses, so a customer is never offered a
    recipe that would refuse the moment it started.
    """
    panel = None
    if server_id:
        server = await resolve_server(server_id, current_user, db)
        os = os or server.os_type
        # `or ""` on purpose: a null panel on a real server means "no panel", not
        # "we do not know" — see skill_service.server_ok.
        panel = server.panel_type or ""
    return [
        RecipeOut(
            slug=s.slug,
            title=s.title,
            summary=s.summary or s.title,
            icon=s.icon,
            os_family=s.os_family,
            budget=skill_service.resolve_mission_budget(s),
            variables=[RecipeVariable(**v) for v in s.variables],
            goal_template=s.goal_template,
        )
        for s in skill_service.list_recipes(os)
        if skill_service.server_ok(s, panel)
    ]
