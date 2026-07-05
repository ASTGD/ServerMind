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
    _: User = Depends(get_current_user),
) -> list[RecipeOut]:
    """List goal-oriented recipes, optionally OS-gated against the selected target
    (all recipes when ``os`` is omitted). Read-only; auth required."""
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
    ]
