"""Team service — membership, invitations, and server access resolution.

Access model:
- An *owner* is a user who owns servers and invites others.
- A *member* is invited with a role: ``viewer`` | ``operator`` | ``admin``.
- ``admin`` members get full access to all of the owner's servers.
- ``viewer`` / ``operator`` members only access servers explicitly granted via
  ``ServerAccess`` rows; ``can_execute`` additionally gates running commands.
- A ``viewer`` can never execute, regardless of any ``can_execute`` flag.

``get_access`` is the single source of truth used by routers and the WebSocket
layer to enforce permissions (CLAUDE.md security rule 7).
"""
from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.server import Server
from app.models.team import ServerAccess, TeamMember
from app.models.user import User

logger = logging.getLogger(__name__)

ROLES = {"viewer", "operator", "admin"}


@dataclass
class Access:
    """Resolved access of a user to a specific server."""

    server: Server
    role: str          # owner | admin | operator | viewer
    can_execute: bool
    can_view_logs: bool

    @property
    def can_manage(self) -> bool:
        """True if the user may change server config / manage the account."""
        return self.role in ("owner", "admin")


def _coerce_uuid(value) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


# ── Access resolution ────────────────────────────────────────────────────────

async def get_access(db: AsyncSession, user: User, server_id) -> Access | None:
    """Return the user's Access to a server, or None if they cannot access it."""
    sid = _coerce_uuid(server_id)
    if sid is None:
        return None

    server = (await db.execute(select(Server).where(Server.id == sid))).scalar_one_or_none()
    if server is None:
        return None

    # 1. Owner — full access.
    if server.user_id == user.id:
        return Access(server, "owner", can_execute=True, can_view_logs=True)

    # 2. Accepted team member of this server's owner.
    tm = (await db.execute(
        select(TeamMember).where(
            TeamMember.owner_id == server.user_id,
            TeamMember.member_id == user.id,
            TeamMember.invite_accepted == True,  # noqa: E712
        )
    )).scalar_one_or_none()
    if tm is None:
        return None

    # 3. Admins get full access to every server the owner has.
    if tm.role == "admin":
        return Access(server, "admin", can_execute=True, can_view_logs=True)

    # 4. viewer/operator need an explicit grant for this server.
    sa = (await db.execute(
        select(ServerAccess).where(
            ServerAccess.team_member_id == tm.id,
            ServerAccess.server_id == server.id,
        )
    )).scalar_one_or_none()
    if sa is None:
        return None

    # A viewer can never execute; an operator executes only when granted.
    can_exec = bool(sa.can_execute) and tm.role == "operator"
    return Access(server, tm.role or "viewer", can_execute=can_exec, can_view_logs=bool(sa.can_view_logs))


async def accessible_servers(db: AsyncSession, user: User) -> list[Server]:
    """All servers the user can see — owned plus team-granted (deduped)."""
    owned = list((await db.execute(
        select(Server).where(Server.user_id == user.id).order_by(Server.created_at)
    )).scalars().all())

    result = list(owned)
    seen = {s.id for s in owned}

    memberships = list((await db.execute(
        select(TeamMember).where(
            TeamMember.member_id == user.id,
            TeamMember.invite_accepted == True,  # noqa: E712
        )
    )).scalars().all())

    for tm in memberships:
        if tm.role == "admin":
            rows = (await db.execute(
                select(Server).where(Server.user_id == tm.owner_id)
            )).scalars().all()
        else:
            rows = (await db.execute(
                select(Server)
                .join(ServerAccess, ServerAccess.server_id == Server.id)
                .where(ServerAccess.team_member_id == tm.id)
            )).scalars().all()
        for s in rows:
            if s.id not in seen:
                seen.add(s.id)
                result.append(s)

    return result


# Cap on how many servers a mission / cross-server chat context carries — keeps the
# prompt bounded. (Lived in websocket/terminal.py as _MISSION_ROSTER_MAX; canonical here
# so build_chat_context can share it without importing the WS layer.)
MISSION_ROSTER_MAX = 15


async def mission_roster(
    db: AsyncSession,
    user: User,
    home_server: Server | None = None,
    cap: int = MISSION_ROSTER_MAX,
) -> list[Server]:
    """The servers a mission (or a chat's cross-server context) may act on: every server
    the user can EXECUTE on (Rule 7 — viewer overrides apply) with a shell connection
    (hosting panels excluded). ``home_server`` leads the list; it is capped to keep the
    prompt bounded."""
    roster: list[Server] = []
    for s in await accessible_servers(db, user):
        if s.connection_type == "hosting":
            continue
        access = await get_access(db, user, str(s.id))
        if access is not None and access.can_execute:
            roster.append(access.server)
    if home_server is not None:
        roster = [home_server] + [s for s in roster if str(s.id) != str(home_server.id)]
    return roster[:cap]


# ── Team management ────────────────────────────────────────────────────────────

async def list_members(db: AsyncSession, owner: User) -> list[TeamMember]:
    rows = await db.execute(
        select(TeamMember).where(TeamMember.owner_id == owner.id).order_by(TeamMember.created_at)
    )
    return list(rows.scalars().all())


async def invite(db: AsyncSession, owner: User, email: str, role: str) -> TeamMember:
    """Create an invitation. If a user with ``email`` exists, pre-link them."""
    existing_user = (await db.execute(
        select(User).where(User.email == email)
    )).scalar_one_or_none()

    member = TeamMember(
        owner_id=owner.id,
        member_id=existing_user.id if existing_user else None,
        role=role,
        invited_email=email,
        invite_token=secrets.token_urlsafe(32),
        invite_accepted=False,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def get_member(db: AsyncSession, owner: User, member_id) -> TeamMember | None:
    mid = _coerce_uuid(member_id)
    if mid is None:
        return None
    return (await db.execute(
        select(TeamMember).where(TeamMember.id == mid, TeamMember.owner_id == owner.id)
    )).scalar_one_or_none()


async def accept_invite(db: AsyncSession, user: User, token: str) -> TeamMember | None:
    """Accept an invite by token. The user's email must match the invitation."""
    tm = (await db.execute(
        select(TeamMember).where(TeamMember.invite_token == token)
    )).scalar_one_or_none()
    if tm is None:
        return None
    if tm.invited_email and tm.invited_email.lower() != (user.email or "").lower():
        raise PermissionError("This invitation was issued to a different email address.")
    tm.member_id = user.id
    tm.invite_accepted = True
    await db.commit()
    await db.refresh(tm)
    return tm


async def remove_member(db: AsyncSession, member: TeamMember) -> None:
    await db.delete(member)
    await db.commit()


async def get_member_access(db: AsyncSession, member: TeamMember) -> list[ServerAccess]:
    rows = await db.execute(
        select(ServerAccess).where(ServerAccess.team_member_id == member.id)
    )
    return list(rows.scalars().all())


async def set_member_access(
    db: AsyncSession,
    owner: User,
    member: TeamMember,
    items: list[dict],
) -> list[ServerAccess]:
    """Replace a member's server-access grants. Only the owner's servers are allowed."""
    # Which servers does the owner actually own?
    owned_ids = {
        s.id for s in (await db.execute(
            select(Server).where(Server.user_id == owner.id)
        )).scalars().all()
    }

    # Clear existing grants for this member.
    existing = await get_member_access(db, member)
    for sa in existing:
        await db.delete(sa)

    created: list[ServerAccess] = []
    for item in items:
        sid = _coerce_uuid(item.get("server_id"))
        if sid is None or sid not in owned_ids:
            continue  # ignore servers the owner doesn't own
        sa = ServerAccess(
            team_member_id=member.id,
            server_id=sid,
            can_execute=bool(item.get("can_execute", False)),
            can_view_logs=bool(item.get("can_view_logs", True)),
        )
        db.add(sa)
        created.append(sa)

    await db.commit()
    for sa in created:
        await db.refresh(sa)
    return created
