"""Servers router — CRUD, connection test, OS detection, and live metrics."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.server import Server
from app.models.user import User
from app.schemas.server import ServerCreate, ServerOut, ServerUpdate
from app.services import connection_manager, metrics_service
from app.services.crypto_service import encrypt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/servers", tags=["servers"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_server(
    server_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> Server:
    """Fetch a server owned by current_user or raise 404."""
    result = await db.execute(
        select(Server).where(Server.id == server_id, Server.user_id == current_user.id)
    )
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    return server


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ServerOut])
async def list_servers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Server]:
    """List all servers belonging to the current user."""
    result = await db.execute(
        select(Server).where(Server.user_id == current_user.id).order_by(Server.created_at)
    )
    return list(result.scalars().all())


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(
    body: ServerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
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
        tags=body.tags,
        notes=body.notes,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Server:
    """Update server name, tags, or notes."""
    server = await _get_server(server_id, db, current_user)
    if body.name is not None:
        server.name = body.name
    if body.tags is not None:
        server.tags = body.tags
    if body.notes is not None:
        server.notes = body.notes
    await db.commit()
    await db.refresh(server)
    return server


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a server and close its connection."""
    server = await _get_server(server_id, db, current_user)
    await connection_manager.close(server)
    await db.delete(server)
    await db.commit()
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
