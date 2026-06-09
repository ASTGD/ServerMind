"""Backups router — backup job CRUD, run, history, and restore."""
from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.backup import Backup, BackupRun
from app.models.server import Server
from app.models.user import User
from app.schemas.backup import (
    BACKUP_TYPES,
    BackupCreate,
    BackupOut,
    BackupRunOut,
    BackupUpdate,
    RestoreBody,
)
from app.services import backup_service, crypto_service, scheduler_service

router = APIRouter(prefix="/api", tags=["backups"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"{what} not found")


async def _get_server(
    server_id: str, user: User, db: AsyncSession, *, need_execute: bool = False
) -> Server:
    """Resolve a server the user can access (owner or team member)."""
    return await resolve_server(server_id, user, db, need_execute=need_execute)


async def _get_backup(backup_id: str, user: User, db: AsyncSession) -> Backup:
    row = await db.execute(
        select(Backup).where(Backup.id == _uuid(backup_id, "Backup"), Backup.user_id == user.id)
    )
    backup = row.scalar_one_or_none()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")
    return backup


def _to_out(backup: Backup) -> BackupOut:
    return BackupOut(
        id=backup.id,
        server_id=backup.server_id,
        name=backup.name,
        backup_type=backup.backup_type,
        source=backup.source,
        dest_dir=backup.dest_dir,
        db_user=backup.db_user,
        has_db_cred=bool(backup.encrypted_db_cred),
        retention=backup.retention,
        cron_expression=backup.cron_expression,
        human_schedule=backup.human_schedule,
        is_active=backup.is_active,
        last_run=backup.last_run,
        last_status=backup.last_status,
        next_run=backup.next_run,
        created_at=backup.created_at,
    )


def _validate_type(backup_type: str) -> None:
    if backup_type not in BACKUP_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"backup_type must be one of {sorted(BACKUP_TYPES)}",
        )


def _validate_cron(cron: str | None) -> None:
    if cron and not scheduler_service.validate_cron(cron):
        raise HTTPException(status_code=422, detail="Invalid cron expression")


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/servers/{server_id}/backups", response_model=list[BackupOut])
async def list_backups(
    server_id: str,
    db: DBDep,
    current_user: CurrentUser,
) -> list[BackupOut]:
    """List backup jobs for a server."""
    server = await _get_server(server_id, current_user, db)
    rows = await db.execute(
        select(Backup).where(Backup.server_id == server.id).order_by(Backup.created_at.desc())
    )
    return [_to_out(b) for b in rows.scalars().all()]


@router.post("/servers/{server_id}/backups", response_model=BackupOut, status_code=201)
async def create_backup(
    server_id: str,
    body: BackupCreate,
    db: DBDep,
    current_user: CurrentUser,
) -> BackupOut:
    """Create a backup job."""
    server = await _get_server(server_id, current_user, db, need_execute=True)
    _validate_type(body.backup_type)
    _validate_cron(body.cron_expression)

    backup = Backup(
        server_id=server.id,
        user_id=current_user.id,
        name=body.name,
        backup_type=body.backup_type,
        source=body.source,
        dest_dir=body.dest_dir or "/var/backups/servermind",
        db_user=body.db_user,
        encrypted_db_cred=crypto_service.encrypt(body.db_password) if body.db_password else None,
        retention=body.retention,
        cron_expression=body.cron_expression,
        human_schedule=body.human_schedule,
        is_active=body.is_active,
    )
    if backup.cron_expression:
        try:
            backup.next_run = scheduler_service.compute_next_run(backup.cron_expression)
        except Exception:  # noqa: BLE001
            backup.next_run = None

    db.add(backup)
    await db.commit()
    await db.refresh(backup)

    backup_service.schedule_backup(backup)
    return _to_out(backup)


@router.put("/backups/{backup_id}", response_model=BackupOut)
async def update_backup(
    backup_id: str,
    body: BackupUpdate,
    db: DBDep,
    current_user: CurrentUser,
) -> BackupOut:
    """Update a backup job. Send db_password='' to clear the stored credential."""
    backup = await _get_backup(backup_id, current_user, db)

    data = body.model_dump(exclude_unset=True)

    if "backup_type" in data and data["backup_type"] is not None:
        _validate_type(data["backup_type"])
    if "cron_expression" in data:
        _validate_cron(data["cron_expression"])

    # Handle the credential specially (encrypt / clear), never store plaintext.
    if "db_password" in data:
        pw = data.pop("db_password")
        backup.encrypted_db_cred = crypto_service.encrypt(pw) if pw else None

    for field, value in data.items():
        setattr(backup, field, value)

    if backup.cron_expression:
        try:
            backup.next_run = scheduler_service.compute_next_run(backup.cron_expression)
        except Exception:  # noqa: BLE001
            backup.next_run = None
    else:
        backup.next_run = None

    await db.commit()
    await db.refresh(backup)

    # Re-register (or remove) the schedule to reflect changes.
    backup_service.schedule_backup(backup)
    return _to_out(backup)


@router.delete("/backups/{backup_id}", status_code=204)
async def delete_backup(
    backup_id: str,
    db: DBDep,
    current_user: CurrentUser,
) -> None:
    """Delete a backup job and its run history (archives on the server remain)."""
    backup = await _get_backup(backup_id, current_user, db)
    backup_service.unschedule_backup(backup.id)
    await db.delete(backup)
    await db.commit()


# ── Run / History / Restore ─────────────────────────────────────────────────

@router.post("/backups/{backup_id}/run", response_model=BackupRunOut, status_code=201)
async def run_backup_now(
    backup_id: str,
    db: DBDep,
    current_user: CurrentUser,
) -> BackupRunOut:
    """Run a backup immediately and return the run record."""
    backup = await _get_backup(backup_id, current_user, db)
    server = await resolve_server(backup.server_id, current_user, db, need_execute=True)
    run = await backup_service.perform_backup(db, server, backup)
    return BackupRunOut.model_validate(run)


@router.get("/backups/{backup_id}/history", response_model=list[BackupRunOut])
async def backup_history(
    backup_id: str,
    db: DBDep,
    current_user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[BackupRunOut]:
    """List recent runs (backups and restores) for a backup job."""
    backup = await _get_backup(backup_id, current_user, db)
    rows = await db.execute(
        select(BackupRun)
        .where(BackupRun.backup_id == backup.id)
        .order_by(BackupRun.started_at.desc())
        .limit(limit)
    )
    return [BackupRunOut.model_validate(r) for r in rows.scalars().all()]


@router.post("/backups/{backup_id}/restore", response_model=BackupRunOut, status_code=201)
async def restore_backup(
    backup_id: str,
    body: RestoreBody,
    db: DBDep,
    current_user: CurrentUser,
) -> BackupRunOut:
    """Restore a backup. Restores from the given run, or the latest successful
    backup if none specified. This overwrites data on the server."""
    backup = await _get_backup(backup_id, current_user, db)
    server = await resolve_server(backup.server_id, current_user, db, need_execute=True)

    if body.run_id:
        row = await db.execute(
            select(BackupRun).where(
                BackupRun.id == body.run_id,
                BackupRun.backup_id == backup.id,
                BackupRun.action == "backup",
            )
        )
        source_run = row.scalar_one_or_none()
        if not source_run:
            raise HTTPException(status_code=404, detail="Backup run not found")
    else:
        row = await db.execute(
            select(BackupRun)
            .where(
                BackupRun.backup_id == backup.id,
                BackupRun.action == "backup",
                BackupRun.status == "success",
            )
            .order_by(BackupRun.started_at.desc())
            .limit(1)
        )
        source_run = row.scalar_one_or_none()
        if not source_run:
            raise HTTPException(status_code=404, detail="No successful backup to restore from")

    run = await backup_service.perform_restore(db, server, backup, source_run)
    return BackupRunOut.model_validate(run)
