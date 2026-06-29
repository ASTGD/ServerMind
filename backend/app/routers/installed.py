"""Installed-software router — what ServerAlly installed on a server (from our own run
history) and a live read-only scan of the box."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import installed_service

router = APIRouter(prefix="/api", tags=["installed"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/servers/{server_id}/installed")
async def list_installed(server_id: str, db: DBDep, user: CurrentUser) -> dict:
    """What ServerAlly has installed on this server, from our run history (read-only)."""
    server = await resolve_server(server_id, user, db)
    items = await installed_service.installed_from_records(db, server)
    return {"items": items}


@router.post("/servers/{server_id}/installed/scan")
async def scan_installed(server_id: str, db: DBDep, user: CurrentUser) -> dict:
    """Live read-only scan of the server for installed software (runs commands → execute)."""
    server = await resolve_server(server_id, user, db, need_execute=True)
    return await installed_service.scan_server(server)
