"""Custom runbooks — the account's own expert procedures.

**Authoring is owner/admin only.** A runbook is instructions an AI follows while it has the
ability to change servers, so writing one is closer to writing a program than to filling in a
form. An owner can already run any command themselves, so a runbook gives them nothing new;
an operator writing one that the owner later triggers unknowingly would be a privilege
boundary being crossed, which is what this restriction prevents. Everyone on the team can
*read* the library, because knowing the procedure you are working under is reasonable.
"""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.runbook import (
    BODY_MAX, MAX_RUNBOOKS, MAX_TRIGGERS, OS_FAMILIES, RUNBOOK_MODES, Runbook,
)
from app.models.team import TeamMember
from app.models.user import User
from app.services import runbook_service, skill_service

router = APIRouter(prefix="/api/runbooks", tags=["runbooks"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# Roles that may write a procedure Ally will follow.
_AUTHOR_ROLES = ("admin",)


class RunbookIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    triggers: list[str] = Field(default_factory=list, max_length=MAX_TRIGGERS)
    body: str = Field(min_length=1, max_length=BODY_MAX)
    mode: str = "guide"
    os_family: str = "any"
    budget: int | None = Field(default=None, ge=5, le=40)
    priority: int = Field(default=50, ge=0, le=100)
    is_active: bool = True


class RunbookPatch(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    triggers: list[str] | None = Field(default=None, max_length=MAX_TRIGGERS)
    body: str | None = Field(default=None, max_length=BODY_MAX)
    mode: str | None = None
    os_family: str | None = None
    budget: int | None = Field(default=None, ge=5, le=40)
    priority: int | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None


async def _account_id(db: AsyncSession, user: User):
    """The account whose library this user reads — theirs, or their team owner's."""
    return await runbook_service.owning_account_id(db, user)


async def _require_author(db: AsyncSession, user: User):
    """Only an account owner (or a team admin) may write a runbook.

    Returns the account id the runbook belongs to.
    """
    membership = (await db.execute(
        select(TeamMember).where(
            TeamMember.member_id == user.id,
            TeamMember.invite_accepted.is_(True),
        ).limit(1)
    )).scalar_one_or_none()

    if membership is None:
        return user.id  # their own account — the owner
    if membership.role not in _AUTHOR_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only the account owner or an admin can write runbooks. A runbook tells "
                   "Ally how to work on your servers, so it needs the highest permission.",
        )
    return membership.owner_id


async def _get(runbook_id: str, account_id, db: AsyncSession) -> Runbook:
    try:
        rid = uuid.UUID(runbook_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Runbook not found")
    row = (await db.execute(
        select(Runbook).where(Runbook.id == rid, Runbook.user_id == account_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Runbook not found")
    return row


def _validate(title: str, body: str, triggers: list[str], mode: str, os_family: str) -> None:
    problem = runbook_service.validate(title, body, triggers, mode, os_family)
    if problem:
        raise HTTPException(status_code=422, detail=problem)


async def _unique_slug(db: AsyncSession, account_id, title: str, exclude: uuid.UUID | None = None) -> str:
    """A slug that is free within this account. Numbered rather than rejected, because a
    duplicate title is a normal thing to do and not worth an error."""
    base = runbook_service.slugify(title)
    for attempt in range(1, 60):
        candidate = base if attempt == 1 else f"{base}-{attempt}"
        query = select(Runbook.id).where(
            Runbook.user_id == account_id, Runbook.slug == candidate
        )
        if exclude is not None:
            query = query.where(Runbook.id != exclude)
        if (await db.execute(query.limit(1))).scalar_one_or_none() is None:
            return candidate
    return f"{base}-{uuid.uuid4().hex[:6]}"


@router.get("")
async def list_runbooks(db: DBDep, current_user: CurrentUser) -> dict:
    account_id = await _account_id(db, current_user)
    rows = (await db.execute(
        select(Runbook).where(Runbook.user_id == account_id)
        .order_by(Runbook.priority.desc(), Runbook.created_at)
    )).scalars().all()
    return {
        "runbooks": [runbook_service.serialize(r) for r in rows],
        "limit": MAX_RUNBOOKS,
        "body_limit": BODY_MAX,
        "modes": list(RUNBOOK_MODES),
        "os_families": list(OS_FAMILIES),
        # Whether this user may write, so the UI can explain rather than fail on submit.
        "can_edit": await _can_edit(db, current_user),
    }


async def _can_edit(db: AsyncSession, user: User) -> bool:
    try:
        await _require_author(db, user)
        return True
    except HTTPException:
        return False


@router.post("", status_code=201)
async def create_runbook(body: RunbookIn, db: DBDep, current_user: CurrentUser) -> dict:
    account_id = await _require_author(db, current_user)
    _validate(body.title, body.body, body.triggers, body.mode, body.os_family)

    count = (await db.execute(
        select(func.count()).select_from(Runbook).where(Runbook.user_id == account_id)
    )).scalar() or 0
    if count >= MAX_RUNBOOKS:
        raise HTTPException(
            status_code=422,
            detail=f"You already have {MAX_RUNBOOKS} runbooks. Every runbook is offered to "
                   f"Ally on each message, so the library is capped — delete one you no "
                   f"longer use.",
        )

    row = Runbook(
        user_id=account_id, created_by=current_user.id,
        title=body.title.strip(),
        slug=await _unique_slug(db, account_id, body.title),
        description=(body.description or "").strip() or None,
        triggers=runbook_service.normalise_triggers(body.triggers),
        body=body.body, mode=body.mode, os_family=body.os_family,
        budget=body.budget, priority=body.priority, is_active=body.is_active,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("Runbook '%s' created for account %s", row.slug, account_id)
    return runbook_service.serialize(row)


@router.put("/{runbook_id}")
async def update_runbook(
    runbook_id: str, body: RunbookPatch, db: DBDep, current_user: CurrentUser
) -> dict:
    account_id = await _require_author(db, current_user)
    row = await _get(runbook_id, account_id, db)
    data = body.model_dump(exclude_unset=True)

    _validate(
        data.get("title", row.title), data.get("body", row.body),
        data.get("triggers", list(row.triggers or [])),
        data.get("mode", row.mode), data.get("os_family", row.os_family),
    )

    if "title" in data and data["title"]:
        row.title = data["title"].strip()
        row.slug = await _unique_slug(db, account_id, row.title, exclude=row.id)
    if "description" in data:
        row.description = (data["description"] or "").strip() or None
    if "triggers" in data and data["triggers"] is not None:
        row.triggers = runbook_service.normalise_triggers(data["triggers"])
    for field in ("body", "mode", "os_family", "budget", "priority", "is_active"):
        if field in data and data[field] is not None:
            setattr(row, field, data[field])

    await db.commit()
    await db.refresh(row)
    return runbook_service.serialize(row)


@router.delete("/{runbook_id}", status_code=204)
async def delete_runbook(runbook_id: str, db: DBDep, current_user: CurrentUser) -> None:
    account_id = await _require_author(db, current_user)
    row = await _get(runbook_id, account_id, db)
    await db.delete(row)
    await db.commit()


@router.post("/preview-match")
async def preview_match(
    db: DBDep, current_user: CurrentUser,
    message: str = Query(min_length=1, max_length=1000),
    os_type: str | None = Query(default=None),
) -> dict:
    """Which procedure would this message use?

    Free and instant — pure trigger matching, no model call. This is the difference between
    writing a runbook and *knowing* it will fire: without it, the only way to find out is to
    wait for the situation it was written for.
    """
    library = await runbook_service.load_for(db, current_user)
    matched = skill_service.match(message, os_type, extra=library)
    if matched is None:
        return {
            "matched": None,
            "explanation": "Nothing matches this wording. Ally would answer from its general "
                           "knowledge — add a phrase from this message to a runbook's triggers "
                           "if you want it used here.",
        }
    custom = skill_service.is_custom(matched)
    return {
        "matched": {
            "slug": matched.slug,
            "title": matched.title,
            "is_custom": custom,
            "is_mission": matched.mode == "mission",
        },
        "explanation": (
            f"Ally would follow your own “{matched.title}”."
            if custom else
            f"Ally would follow its built-in “{matched.title}”. Add a phrase from this "
            f"message to one of your runbooks to use yours instead."
        ),
    }


@router.get("/built-in")
async def built_in_procedures(os_type: str | None = Query(default=None)) -> dict:
    """The procedures ServerAlly ships, so an author can see what already exists rather than
    rewriting something we already do — or knowingly replace it."""
    return {
        "procedures": [
            {"slug": s.slug, "title": s.title, "is_mission": s.mode == "mission",
             "triggers": s.triggers[:6]}
            for s in skill_service.load_skills()
            if os_type is None or skill_service._os_ok(s, os_type)
        ],
    }
