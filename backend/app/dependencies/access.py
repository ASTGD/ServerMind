"""Shared server-access resolution for routers.

Wraps :func:`team_service.get_access` and raises the right HTTP errors so every
server-scoped router can enforce ownership / team permissions consistently.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.server import Server
from app.models.user import User
from app.services import team_service


async def resolve_server(
    server_id,
    user: User,
    db: AsyncSession,
    *,
    need_execute: bool = False,
    need_manage: bool = False,
) -> Server:
    """Return a server the user may access, or raise.

    - 404 if the server doesn't exist or the user has no access to it.
    - 403 if ``need_execute`` and the user lacks execute permission.
    - 403 if ``need_manage`` and the user is not owner/admin.
    """
    access = await team_service.get_access(db, user, server_id)
    if access is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    if need_manage and not access.can_manage:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to manage this server.",
        )
    if need_execute and not access.can_execute:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to run commands on this server.",
        )
    return access.server
