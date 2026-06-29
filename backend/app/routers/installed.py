"""Installed-software router — what ServerAlly installed on a server (from our own run
history) and a live read-only scan of the box."""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import audit_service, installed_service

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


@router.get("/servers/{server_id}/installed/{run_id}/reveal")
async def reveal_installed(
    server_id: str, run_id: str, db: DBDep, user: CurrentUser, request: Request
) -> dict:
    """Owner-only, audited: decrypt and return the credentials + install inputs for one
    install. The list endpoint stays masked — this is the explicit "reveal" action."""
    server = await resolve_server(server_id, user, db)
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Install not found")
    result = await installed_service.reveal_install(db, server, rid)
    if result is None:
        raise HTTPException(status_code=404, detail="Install not found")
    await audit_service.audit(
        db, user, "install.reveal_credentials",
        target_type="server", target_id=server.id,
        meta={"run_id": run_id, "playbook": result.get("playbook_title")},
        request=request,
    )
    return {"access": result["access"], "variables": result["variables"]}
