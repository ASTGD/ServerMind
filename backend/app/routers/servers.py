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
from app.services import audit_service, connection_manager, metering_service, metrics_service
from app.services import team_service
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


def infer_category(connection_type: str, panel_type: str | None) -> str:
    """The user-facing Assets category for an asset when the client didn't send one
    (older clients, or backfill). Bare-metal can't be inferred from transport → a plain
    SSH box defaults to 'vps'; the user can re-file it in Edit."""
    if connection_type == "winrm":
        return "windows"
    if connection_type == "rdp":
        return "windows_rdp"
    if connection_type == "hosting":
        return "hosting"
    if connection_type == "ssh" and panel_type:
        return "hosting"
    return "vps"


@router.post("", response_model=ServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(
    request: Request,
    body: ServerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_verified),
) -> Server:
    """Add a new server. Credential is encrypted before storage."""
    # Plan meter #2 (PRICING v2 — "open features, two meters"): the server cap. The
    # one and only feature-level gate; blocks only when ENFORCE_PLAN_LIMITS is on.
    sg = await metering_service.servers_gate(db, current_user)
    if not sg.allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=metering_service.servers_message(sg),
        )

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
        category=body.category or infer_category(body.connection_type, body.panel_type),
        encrypted_cred=encrypted,
        shell="powershell" if body.connection_type in ("winrm", "rdp") else "bash",
        tags=body.tags,
        notes=body.notes,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)

    # Probe the new server so its status (and OS) reflect reality immediately,
    # instead of sitting at "unknown" until the metrics worker runs.
    from app.services import metrics_service
    from app.services.ssh_service import is_auth_error
    try:
        result = await connection_manager.test_connection(server)
        if result.ok:
            server.status = "online"
            server.last_seen = datetime.now(timezone.utc)
            if result.fingerprint:
                server.fingerprint = result.fingerprint  # pin identity on first connect
            try:
                info = await metrics_service.detect_os(server)
                server.os_type = info.get("os_type")
                server.os_version = info.get("os_version")
                server.arch = info.get("arch")
                # A control panel on an SSH box makes it a hosting-panel asset (Hosting tab,
                # CLI-over-SSH) — file it under Hosting so it's one unified card, not a VPS.
                if server.connection_type == "ssh":
                    server.panel_type = info.get("panel")
                    if info.get("panel"):
                        server.category = "hosting"
            except Exception:  # noqa: BLE001 — OS detect is a bonus; status is already set
                pass
        elif result.host_key_changed:
            server.status = "host_changed"
        elif is_auth_error(message=result.error):
            server.status = "auth_failed"
        else:
            server.status = "offline"
        await db.commit()
        await db.refresh(server)
    except Exception:  # noqa: BLE001 — never let the probe fail the add
        logger.debug("Post-create probe failed for %s", server.id, exc_info=True)

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
    if body.category is not None:
        server.category = body.category

    conn_changed = False
    if body.host is not None and body.host != server.host:
        server.host = body.host; conn_changed = True
    if body.port is not None and body.port != server.port:
        server.port = body.port; conn_changed = True
    if body.username is not None and body.username != server.username:
        server.username = body.username; conn_changed = True
    if body.auth_type is not None and body.auth_type != server.auth_type:
        server.auth_type = body.auth_type; conn_changed = True
    if body.credential is not None:
        server.encrypted_cred = encrypt(body.credential); conn_changed = True  # new secret ⇒ always re-probe

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

    # Update status in DB — distinguish identity change / stale creds / unreachable.
    from app.services.ssh_service import is_auth_error
    if result.host_key_changed:
        server.status = "host_changed"
    elif result.ok:
        server.status = "online"
        server.last_seen = datetime.now(timezone.utc)
        if result.fingerprint and not server.fingerprint:
            server.fingerprint = result.fingerprint  # trust-on-first-use pin
        elif (result.fingerprint and server.fingerprint
              and result.fingerprint.endswith(server.fingerprint)
              and result.fingerprint != server.fingerprint):
            # The same key, now recorded WITH its type. An older pin is a bare fingerprint,
            # so every cold connection has to try each key type until one matches before it
            # can proceed. Writing the type back makes that a one-time cost instead of a
            # permanent one — and it is provably the same key, because the fingerprint the
            # connection verified against is the one already stored.
            server.fingerprint = result.fingerprint
    elif is_auth_error(message=result.error):
        server.status = "auth_failed"
    else:
        server.status = "offline"
    await db.commit()

    return {
        "ok": result.ok,
        "latency_ms": result.latency_ms,
        "error": result.error,
        "host_key_changed": result.host_key_changed,
    }


async def _forget_the_previous_machine(server, db: AsyncSession) -> None:
    """Drop what we believed about a server whose identity has just been replaced.

    Deliberately marks sites ABSENT rather than deleting them — the same rule the discovery
    scan follows, so "when did this disappear?" stays answerable during an incident. The
    timestamp is what lets a completed setup stop counting: it described the old machine.

    The panel is cleared rather than kept because it decides the whole menu and the shell
    guards; if the rebuilt machine really does run one, the Start-here look detects it again
    and records it, so this is self-healing rather than lossy.
    """
    from sqlalchemy import update

    from app.models.site import Site

    server.identity_changed_at = datetime.now(timezone.utc)
    server.panel_type = None
    server.category = "vps"
    await db.execute(
        update(Site).where(Site.server_id == server.id, Site.is_present == True)  # noqa: E712
        .values(is_present=False)
    )


@router.post("/{server_id}/trust-key")
async def trust_server_key(
    server_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Trust the server's CURRENT host key: clear the pinned fingerprint and re-pin
    on a fresh connect. Use after legitimately rebuilding or replacing a server whose
    identity changed. Requires manage rights; audited (security-sensitive)."""
    server = await resolve_server(server_id, current_user, db, need_manage=True)
    old_fp = server.fingerprint
    server.fingerprint = None
    await connection_manager.close(server)  # drop any cached connection
    result = await connection_manager.test_connection(server)

    from app.services.ssh_service import is_auth_error
    if result.ok and result.fingerprint:
        server.fingerprint = result.fingerprint
        server.status = "online"
        server.last_seen = datetime.now(timezone.utc)
    elif is_auth_error(message=result.error):
        server.status = "auth_failed"
    else:
        server.status = "offline"

    # This is the customer telling us it is a DIFFERENT machine, so everything we recorded
    # about the previous one stops applying. Without this a rebuilt server went on listing
    # websites that no longer exist and went on claiming ServerAlly was its control panel,
    # so it never offered the setup choice again.
    await _forget_the_previous_machine(server, db)
    await db.commit()
    await audit_service.audit(
        db, current_user, "server.trust_key",
        target_type="server", target_id=server.id,
        meta={"old_fingerprint": old_fp, "new_fingerprint": server.fingerprint},
        request=request,
    )
    return {"ok": result.ok, "fingerprint": server.fingerprint, "error": result.error}


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
    # A control panel on an SSH box IS a hosting-panel asset (managed via the panel CLI over
    # the same SSH, H1). File it under the Hosting Panel category so it's ONE unified card
    # (SSH + panel), not ALSO a separate VPS card.
    if server.connection_type == "ssh":
        server.panel_type = info.get("panel")
        if info.get("panel"):
            server.category = "hosting"
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
