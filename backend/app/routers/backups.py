"""Backups router — backup job CRUD, run, history, and restore."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.backup import Backup, BackupRun
from app.models.backup_destination import BackupDestination
from app.models.server import Server
from app.models.user import User
from app.schemas.backup import (
    BACKUP_TYPES,
    PROVIDERS,
    BackupCreate,
    BackupOut,
    BackupRunOut,
    BackupUpdate,
    DestinationCreate,
    DestinationOut,
    DestinationUpdate,
    RestoreBody,
)
from app.services import backup_service, crypto_service, offsite_service, scheduler_service
from app.services.offsite_service import OffsiteError

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


def _to_out(backup: Backup, dest_name: str | None = None) -> BackupOut:
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
        destination_id=backup.destination_id,
        destination_name=dest_name,
        keep_local=backup.keep_local,
        created_at=backup.created_at,
    )


async def _dest_names(db, backups: list[Backup]) -> dict:
    """Map destination_id → name for a set of jobs, in one query (no N+1)."""
    ids = {b.destination_id for b in backups if b.destination_id}
    if not ids:
        return {}
    rows = (await db.execute(
        select(BackupDestination.id, BackupDestination.name).where(BackupDestination.id.in_(ids))
    )).all()
    return {r[0]: r[1] for r in rows}


async def _get_destination(dest_id, user: User, db: AsyncSession) -> BackupDestination:
    """Resolve a destination the caller owns. Own-scoped, so one user can never point a
    backup at another user's bucket."""
    row = await db.execute(
        select(BackupDestination).where(
            BackupDestination.id == dest_id, BackupDestination.user_id == user.id
        )
    )
    dest = row.scalar_one_or_none()
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")
    return dest


def _validate_provider(provider: str | None) -> None:
    if provider and provider not in PROVIDERS:
        raise HTTPException(status_code=422, detail=f"provider must be one of {sorted(PROVIDERS)}")


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
    backups = list(rows.scalars().all())
    names = await _dest_names(db, backups)
    return [_to_out(b, names.get(b.destination_id)) for b in backups]


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
    # Ownership check: you may only send a backup to a bucket you own.
    dest_name = None
    if body.destination_id:
        dest_name = (await _get_destination(body.destination_id, current_user, db)).name

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
        destination_id=body.destination_id,
        keep_local=body.keep_local,
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
    return _to_out(backup, dest_name)


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

    # Ownership check on a re-pointed destination (None clears it).
    if data.get("destination_id"):
        await _get_destination(data["destination_id"], current_user, db)

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
    names = await _dest_names(db, [backup])
    return _to_out(backup, names.get(backup.destination_id))


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


# ── Offsite destinations ─────────────────────────────────────────────────────
# A destination is user-owned and reusable across backup jobs. The secret key is
# AES-256-GCM encrypted at rest and is never returned by any endpoint here.

@router.get("/backup-destinations", response_model=list[DestinationOut])
async def list_destinations(db: DBDep, user: CurrentUser) -> list[DestinationOut]:
    """Your offsite storage destinations."""
    rows = (await db.execute(
        select(BackupDestination)
        .where(BackupDestination.user_id == user.id)
        .order_by(BackupDestination.created_at.desc())
    )).scalars().all()
    return [DestinationOut.model_validate(r) for r in rows]


@router.post("/backup-destinations", response_model=DestinationOut, status_code=201)
async def create_destination(body: DestinationCreate, db: DBDep, user: CurrentUser) -> DestinationOut:
    """Add a bucket. We verify we can actually WRITE to it before saving — a list-only
    check would pass on a read-only key and then fail at 2am during a real backup."""
    _validate_provider(body.provider)
    dest = BackupDestination(
        user_id=user.id,
        name=body.name,
        provider=body.provider,
        bucket=body.bucket,
        region=body.region,
        endpoint_url=body.endpoint_url,
        prefix=body.prefix,
        access_key_id=body.access_key_id,
        encrypted_secret_key=crypto_service.encrypt(body.secret_key),
    )
    try:
        await offsite_service.verify(dest)
    except OffsiteError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    dest.last_status = "ok"
    dest.last_checked = datetime.now(tz=timezone.utc)
    db.add(dest)
    await db.commit()
    await db.refresh(dest)
    return DestinationOut.model_validate(dest)


@router.put("/backup-destinations/{dest_id}", response_model=DestinationOut)
async def update_destination(
    dest_id: str, body: DestinationUpdate, db: DBDep, user: CurrentUser
) -> DestinationOut:
    """Update a destination. Omit ``secret_key`` to keep the stored one. Re-verified
    before saving, so a broken edit can't be persisted."""
    dest = await _get_destination(_uuid(dest_id, "Destination"), user, db)
    _validate_provider(body.provider)

    for field in ("name", "provider", "bucket", "region", "endpoint_url", "prefix", "access_key_id"):
        value = getattr(body, field)
        if value is not None:
            setattr(dest, field, value)
    if body.secret_key:
        dest.encrypted_secret_key = crypto_service.encrypt(body.secret_key)

    try:
        await offsite_service.verify(dest)
    except OffsiteError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    dest.last_status = "ok"
    dest.last_error = None
    dest.last_checked = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(dest)
    return DestinationOut.model_validate(dest)


@router.post("/backup-destinations/{dest_id}/test", response_model=DestinationOut)
async def test_destination(dest_id: str, db: DBDep, user: CurrentUser) -> DestinationOut:
    """Re-check a destination now (keys rotate, buckets get deleted, permissions change)."""
    dest = await _get_destination(_uuid(dest_id, "Destination"), user, db)
    try:
        await offsite_service.verify(dest)
        dest.last_status, dest.last_error = "ok", None
    except OffsiteError as exc:
        dest.last_status, dest.last_error = "failed", str(exc)
    dest.last_checked = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(dest)
    return DestinationOut.model_validate(dest)


@router.delete("/backup-destinations/{dest_id}", status_code=204)
async def delete_destination(dest_id: str, db: DBDep, user: CurrentUser) -> None:
    """Remove a destination. Jobs pointing at it keep their history and fall back to
    local-only backups (the FK is ON DELETE SET NULL) — we never delete a customer's
    stored archives."""
    dest = await _get_destination(_uuid(dest_id, "Destination"), user, db)
    await db.delete(dest)
    await db.commit()
