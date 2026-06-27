"""Servers router — CRUD, connection test, OS detection, and live metrics."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user, require_verified
from app.models.server import Server
from app.models.user import User
from app.schemas.server import ServerCreate, ServerOut, ServerUpdate
from app.services import audit_service, connection_manager, metrics_service, team_service
from app.services.crypto_service import encrypt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/servers", tags=["servers"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_server(
    server_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> Server:
    """Fetch a server the current user can access (owner or team member)."""
    return await resolve_server(server_id, current_user, db)


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ServerOut])
async def list_servers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Server]:
    """List all servers the current user can access (owned + team-granted)."""
    return await team_service.accessible_servers(db, current_user)


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(
    request: Request,
    body: ServerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_verified),
) -> Server:
    """Add a new server. Credential is encrypted before storage."""
    encrypted = encrypt(body.credential)
    server = Server(
        user_id=current_user.id,
        name=body.name,
        host=body.host,
        port=body.port,
        username=body.username,
        auth_type=body.auth_type,
        connection_type=body.connection_type,
        panel_type=body.panel_type,
        encrypted_cred=encrypted,
        shell="powershell" if body.connection_type == "winrm" else "bash",
        tags=body.tags,
        notes=body.notes,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    await audit_service.audit(
        db, current_user, "server.create",
        target_type="server", target_id=server.id,
        meta={"name": server.name, "host": server.host, "connection_type": server.connection_type},
        request=request,
    )
    logger.info("Server %s created by user %s", server.id, current_user.id)
    return server


@router.get("/{server_id}", response_model=ServerOut)
async def get_server(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Server:
    """Get a single server by ID."""
    return await _get_server(server_id, db, current_user)


@router.put("/{server_id}", response_model=ServerOut)
async def update_server(
    server_id: uuid.UUID,
    body: ServerUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Server:
    """Update a server. Name/tags/notes, and — when provided — the connection
    details and credential (password/key). Changing any connection detail drops the
    cached SSH connection and resets status, so the new details take effect at once."""
    server = await resolve_server(server_id, current_user, db, need_manage=True)
    if body.name is not None:
        server.name = body.name
    if body.tags is not None:
        server.tags = body.tags
    if body.notes is not None:
        server.notes = body.notes

    conn_changed = False
    if body.host is not None:
        server.host = body.host; conn_changed = True
    if body.port is not None:
        server.port = body.port; conn_changed = True
    if body.username is not None:
        server.username = body.username; conn_changed = True
    if body.auth_type is not None:
        server.auth_type = body.auth_type; conn_changed = True
    if body.credential is not None:
        server.encrypted_cred = encrypt(body.credential); conn_changed = True

    if conn_changed:
        # The pooled SSH connection (if any) was authenticated with the OLD creds —
        # drop it and force a fresh connect/test on next use.
        await connection_manager.close(server)
        server.status = "unknown"

    await db.commit()
    await db.refresh(server)
    if conn_changed:
        await audit_service.audit(
            db, current_user, "server.update",
            target_type="server", target_id=server.id,
            meta={"host": server.host, "credential_changed": body.credential is not None},
            request=request,
        )
    return server


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a server and close its connection."""
    server = await resolve_server(server_id, current_user, db, need_manage=True)
    server_name = server.name
    await connection_manager.close(server)
    await db.delete(server)
    await db.commit()
    await audit_service.audit(
        db, current_user, "server.delete",
        target_type="server", target_id=server_id, meta={"name": server_name},
        request=request,
    )
    logger.info("Server %s deleted by user %s", server_id, current_user.id)


# ── Connection test ───────────────────────────────────────────────────────────

@router.post("/{server_id}/test")
async def test_server(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Test SSH/WinRM connectivity and return latency."""
    server = await _get_server(server_id, db, current_user)
    try:
        result = await connection_manager.test_connection(server)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))

    # Update status in DB
    server.status = "online" if result.ok else "offline"
    if result.ok:
        server.last_seen = datetime.now(timezone.utc)
    await db.commit()

    return {
        "ok": result.ok,
        "latency_ms": result.latency_ms,
        "error": result.error,
    }


# ── OS detection ──────────────────────────────────────────────────────────────

@router.post("/{server_id}/detect")
async def detect_server_os(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Auto-detect OS, version, architecture and persist to the server record."""
    server = await _get_server(server_id, db, current_user)
    try:
        info = await metrics_service.detect_os(server)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))
    except Exception as exc:
        logger.warning("OS detection failed for server %s: %s", server_id, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Detection failed: {exc}")

    server.os_type = info.get("os_type")
    server.os_version = info.get("os_version")
    server.arch = info.get("arch")
    server.last_seen = datetime.now(timezone.utc)
    await db.commit()

    return info


# ── Live metrics ──────────────────────────────────────────────────────────────

@router.get("/{server_id}/metrics")
async def get_server_metrics(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Fetch live CPU/RAM/disk/load metrics from the server."""
    server = await _get_server(server_id, db, current_user)
    try:
        metrics = await metrics_service.get_metrics(server)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))
    except Exception as exc:
        logger.warning("Metrics collection failed for server %s: %s", server_id, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Metrics failed: {exc}")

    if not metrics:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not collect metrics")

    return metrics
