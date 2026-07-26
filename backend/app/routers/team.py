"""Team router — membership, invitations, and per-server access grants."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.team import (
    AcceptResult,
    ServerAccessOut,
    SetAccessBody,
    TeamInvite,
    TeamMemberOut,
    TeamMemberUpdate,
)
from app.services import audit_service, team_service
from app.services import entitlements

router = APIRouter(prefix="/api/team", tags=["team"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _validate_role(role: str) -> None:
    if role not in team_service.ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role must be one of {sorted(team_service.ROLES)}",
        )


# ── Membership ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[TeamMemberOut])
async def list_team(db: DBDep, current_user: CurrentUser) -> list[TeamMemberOut]:
    """List the members the current user (as owner) has invited."""
    members = await team_service.list_members(db, current_user)
    return [TeamMemberOut.model_validate(m) for m in members]


@router.post("/invite", response_model=TeamMemberOut, status_code=201)
async def invite_member(
    request: Request,
    body: TeamInvite,
    db: DBDep,
    current_user: CurrentUser,
) -> TeamMemberOut:
    """Invite someone by email with a role. Returns the invite (incl. token)."""
    entitlements.require(current_user, entitlements.TEAM)
    seats = len(await team_service.list_members(db, current_user))
    allowed, limit = entitlements.count_gate(current_user, "max_team_members", seats)
    if not allowed:
        raise HTTPException(
            status_code=402,
            detail=entitlements.count_message(current_user, "team logins", limit),
        )
    _validate_role(body.role)
    email = body.email.strip().lower()
    member = await team_service.invite(db, current_user, email, body.role)
    await audit_service.audit(
        db, current_user, "team.invite",
        target_type="team_member", target_id=member.id,
        meta={"email": email, "role": body.role}, request=request,
    )
    return TeamMemberOut.model_validate(member)


@router.put("/{member_id}", response_model=TeamMemberOut)
async def update_member(
    member_id: str,
    request: Request,
    body: TeamMemberUpdate,
    db: DBDep,
    current_user: CurrentUser,
) -> TeamMemberOut:
    """Change a member's role."""
    _validate_role(body.role)
    member = await team_service.get_member(db, current_user, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    member.role = body.role
    await db.commit()
    await db.refresh(member)
    await audit_service.audit(
        db, current_user, "team.role_change",
        target_type="team_member", target_id=member_id, meta={"role": body.role},
        request=request,
    )
    return TeamMemberOut.model_validate(member)


@router.delete("/{member_id}", status_code=204)
async def delete_member(
    member_id: str,
    request: Request,
    db: DBDep,
    current_user: CurrentUser,
) -> None:
    """Remove a member from the team (revokes all their access)."""
    member = await team_service.get_member(db, current_user, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    await team_service.remove_member(db, member)
    await audit_service.audit(
        db, current_user, "team.remove",
        target_type="team_member", target_id=member_id, request=request,
    )


# ── Per-server access ───────────────────────────────────────────────────────

@router.get("/{member_id}/access", response_model=list[ServerAccessOut])
async def get_access(
    member_id: str,
    db: DBDep,
    current_user: CurrentUser,
) -> list[ServerAccessOut]:
    """List a member's per-server access grants."""
    member = await team_service.get_member(db, current_user, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    rows = await team_service.get_member_access(db, member)
    return [ServerAccessOut.model_validate(r) for r in rows]


@router.put("/{member_id}/access", response_model=list[ServerAccessOut])
async def set_access(
    member_id: str,
    body: SetAccessBody,
    db: DBDep,
    current_user: CurrentUser,
) -> list[ServerAccessOut]:
    """Replace a member's per-server access grants (owner's servers only)."""
    member = await team_service.get_member(db, current_user, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")
    items = [i.model_dump() for i in body.items]
    rows = await team_service.set_member_access(db, current_user, member, items)
    return [ServerAccessOut.model_validate(r) for r in rows]


# ── Accept invitation ───────────────────────────────────────────────────────

@router.post("/accept/{token}", response_model=AcceptResult)
async def accept_invitation(
    token: str,
    db: DBDep,
    current_user: CurrentUser,
) -> AcceptResult:
    """Accept an invitation as the currently logged-in user."""
    try:
        member = await team_service.accept_invite(db, current_user, token)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not member:
        raise HTTPException(status_code=404, detail="Invitation not found")
    return AcceptResult(
        message="Invitation accepted.",
        owner_id=member.owner_id,
        role=member.role,
    )
