"""MCP admin — the user's Connected Applications (docs/MCP-SERVER-PLAN.md Phase 4).

Authed with the app's normal JWT (NOT the MCP bearer). Lets a user see which AI clients
(Claude, ChatGPT, Cursor…) they've connected to their ServerAlly account via MCP, and
revoke any of them — "connect and revoke without support". Credential-free: a connection
row carries only the client's name, scopes, and timestamps.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.mcp.oauth_provider import mcp_enabled_for
from app.models.oauth import OAuthClient, OAuthTokenRecord
from app.models.user import User
from app.services import audit_service, mcp_activity_service

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class MCPInfo(BaseModel):
    url: str
    enabled: bool


class MCPConnection(BaseModel):
    grant_id: str
    client_id: str
    client_name: str | None
    scopes: list[str]
    connected_at: str
    last_active: str


class MCPActivityItem(BaseModel):
    id: str
    client_name: str
    tool: str
    server_name: str | None
    status: str          # running | ok | blocked | error
    label: str
    command: str | None  # run_command text, secret-redacted
    exit_code: int | None
    detail: str | None
    started_at: str
    finished_at: str | None


@router.get("/activity", response_model=list[MCPActivityItem])
async def list_activity(
    limit: int = 60,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MCPActivityItem]:
    """Recent actions your connected AI clients took over MCP, newest first. Poll this to
    watch activity live — each action shows ``running`` then flips to its result. Scoped to
    your own account; credential-free (the command text is already secret-redacted)."""
    rows = await mcp_activity_service.recent(db, current_user.id, min(max(limit, 1), 200))
    return [MCPActivityItem(**mcp_activity_service.serialize(r)) for r in rows]


@router.get("/info", response_model=MCPInfo)
async def mcp_info(current_user: User = Depends(get_current_user)) -> MCPInfo:
    """The MCP endpoint URL to connect to, and whether the feature is on for this user
    (on unless plan limits gate a free plan)."""
    return MCPInfo(
        url=settings.MCP_BASE_URL.rstrip("/") + "/mcp",
        enabled=settings.MCP_REQUIRE_AUTH and mcp_enabled_for(current_user),
    )


@router.get("/connections", response_model=list[MCPConnection])
async def list_connections(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[MCPConnection]:
    """One row per connection (grant) for the signed-in user, newest activity first.

    A user has few connections, so we group in Python — the access + refresh tokens of a
    grant share client_id + scopes; connected_at is the earliest, last_active the latest.
    """
    subject = str(current_user.id)
    tokens = (await db.execute(
        select(OAuthTokenRecord).where(OAuthTokenRecord.subject == subject)
        .order_by(OAuthTokenRecord.created_at)
    )).scalars().all()

    grants: dict[str, dict] = {}
    for t in tokens:
        gid = str(t.grant_id)
        g = grants.get(gid)
        if g is None:
            grants[gid] = {
                "grant_id": gid, "client_id": t.client_id, "scopes": list(t.scopes or []),
                "connected_at": t.created_at, "last_active": t.created_at,
            }
        else:
            g["connected_at"] = min(g["connected_at"], t.created_at)
            g["last_active"] = max(g["last_active"], t.created_at)

    # Resolve client display names.
    client_ids = {g["client_id"] for g in grants.values()}
    names: dict[str, str | None] = {}
    if client_ids:
        for c in (await db.execute(
            select(OAuthClient).where(OAuthClient.client_id.in_(client_ids))
        )).scalars().all():
            names[c.client_id] = c.client_name

    out = [
        MCPConnection(
            grant_id=g["grant_id"], client_id=g["client_id"], client_name=names.get(g["client_id"]),
            scopes=g["scopes"], connected_at=g["connected_at"].isoformat(),
            last_active=g["last_active"].isoformat(),
        )
        for g in grants.values()
    ]
    out.sort(key=lambda c: c.last_active, reverse=True)
    return out


@router.delete("/connections/{grant_id}", status_code=204)
async def revoke_connection(
    grant_id: str, request: Request,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user),
) -> None:
    """Revoke a connection — delete every token in the grant. Scoped to the caller's own
    subject, so a user can only ever revoke their own connections. The client loses access
    immediately (tokens are validated by DB lookup)."""
    try:
        gid = uuid.UUID(grant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Connection not found")

    result = await db.execute(
        delete(OAuthTokenRecord).where(
            OAuthTokenRecord.grant_id == gid,
            OAuthTokenRecord.subject == str(current_user.id),
        )
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Connection not found")
    await audit_service.audit(
        db, current_user, "mcp.revoke_connection", meta={"grant_id": grant_id}, request=request
    )
