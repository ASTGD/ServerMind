"""Remote Desktop router (Assets Phase E). Enable/disable RDP on a Windows asset, and issue
a short-lived desktop session. Access is enforced by the shared `resolve_server` gate:
opening a live desktop needs execute permission (a viewer role can never open one — RDP is
outside the AI-safety envelope), and toggling it needs manage permission."""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import rdp_service
from app.services.rdp_service import RdpError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/servers", tags=["rdp"])


class RdpEnableBody(BaseModel):
    enabled: bool


class RdpSessionOut(BaseModel):
    session_token: str
    host: str
    port: int
    expires_in: int
    streaming_available: bool


@router.post("/{server_id}/rdp/enable")
async def set_rdp_enabled(
    server_id: uuid.UUID,
    body: RdpEnableBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Turn Remote Desktop on/off for a Windows asset (manage permission)."""
    server = await resolve_server(server_id, current_user, db, need_manage=True)
    if server.connection_type != "winrm":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Remote Desktop is available on Windows assets only.")
    server.rdp_enabled = body.enabled
    await db.commit()
    logger.info("RDP %s for server %s by user %s", "enabled" if body.enabled else "disabled", server_id, current_user.id)
    return {"rdp_enabled": server.rdp_enabled}


@router.post("/{server_id}/rdp/session", response_model=RdpSessionOut)
async def open_rdp_session(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Mint a short-lived desktop session (execute permission — viewers are refused)."""
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    try:
        return rdp_service.issue_session(server, current_user)
    except RdpError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
