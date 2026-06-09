"""Backup service — file/database backups over SSH with retention + restore.

Backups are produced by running standard tools on the server (``tar``,
``mysqldump``, ``pg_dump``) via :func:`connection_manager.execute`, gzipped into
``dest_dir``. Old archives beyond ``retention`` are pruned. Restores stream the
chosen archive back through ``tar -x`` / ``mysql`` / ``psql``.

Optional database passwords are passed via environment variables (``MYSQL_PWD`` /
``PGPASSWORD``) so they never appear in the process argument list.
"""
from __future__ import annotations

import logging
import re
import shlex
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.backup import Backup, BackupRun
from app.models.server import Server
from app.services import connection_manager, crypto_service, scheduler_service

logger = logging.getLogger(__name__)

_SIZE_RE = re.compile(r"__SMSIZE__=(\d+)")
_OUTPUT_CAP = 8000


def _q(value: str) -> str:
    """Shell-quote a value for safe interpolation."""
    return shlex.quote(value)


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]", "_", name).strip("_")
    return (s or "backup")[:64]


def _ext(backup_type: str) -> str:
    return "tar.gz" if backup_type == "files" else "sql.gz"


def _dest(backup: Backup) -> str:
    return (backup.dest_dir or "/var/backups/servermind").rstrip("/")


def _archive_path(backup: Backup, now: datetime) -> str:
    ts = now.strftime("%Y%m%d-%H%M%S")
    return f"{_dest(backup)}/{_slug(backup.name)}-{ts}.{_ext(backup.backup_type)}"


def _db_password(backup: Backup) -> str | None:
    if not backup.encrypted_db_cred:
        return None
    try:
        return crypto_service.decrypt(backup.encrypted_db_cred)
    except Exception:  # noqa: BLE001
        logger.warning("Could not decrypt DB credential for backup %s", backup.id)
        return None


# ── Command builders ────────────────────────────────────────────────────────

def _build_backup_command(backup: Backup, archive: str) -> str:
    dest = _dest(backup)
    btype = backup.backup_type

    if btype == "files":
        return (
            f"umask 077; mkdir -p {_q(dest)} || exit 1; "
            f"tar -czpf {_q(archive)} {_q(backup.source)} 2>&1; rc=$?; "
            f"echo __SMSIZE__=$(stat -c%s {_q(archive)} 2>/dev/null); exit $rc"
        )

    # Database backups
    pw = _db_password(backup)
    if btype == "mysql":
        env = f"MYSQL_PWD={_q(pw)} " if pw else ""
        userflag = f"-u {_q(backup.db_user)} " if backup.db_user else ""
        dump = f"{env}mysqldump {userflag}--single-transaction --quick {_q(backup.source)}"
    elif btype == "postgres":
        env = f"PGPASSWORD={_q(pw)} " if pw else ""
        userflag = f"-U {_q(backup.db_user)} " if backup.db_user else ""
        dump = f"{env}pg_dump {userflag}{_q(backup.source)}"
    else:
        raise ValueError(f"Unsupported backup_type: {btype}")

    return (
        f"umask 077; mkdir -p {_q(dest)} || exit 1; "
        f"set -o pipefail 2>/dev/null; ERR=$(mktemp); "
        f"{dump} 2>\"$ERR\" | gzip > {_q(archive)}; rc=$?; "
        f"[ $rc -ne 0 ] && cat \"$ERR\"; rm -f \"$ERR\"; "
        f"echo __SMSIZE__=$(stat -c%s {_q(archive)} 2>/dev/null); exit $rc"
    )


def _build_restore_command(backup: Backup, archive: str) -> str:
    btype = backup.backup_type
    if btype == "files":
        # Restores archived paths back to their original (absolute) locations.
        return f"tar -xzpf {_q(archive)} -C / 2>&1; exit $?"

    pw = _db_password(backup)
    if btype == "mysql":
        env = f"MYSQL_PWD={_q(pw)} " if pw else ""
        userflag = f"-u {_q(backup.db_user)} " if backup.db_user else ""
        target = f"{env}mysql {userflag}{_q(backup.source)}"
    elif btype == "postgres":
        env = f"PGPASSWORD={_q(pw)} " if pw else ""
        userflag = f"-U {_q(backup.db_user)} " if backup.db_user else ""
        target = f"{env}psql {userflag}-d {_q(backup.source)}"
    else:
        raise ValueError(f"Unsupported backup_type: {btype}")

    return (
        f"set -o pipefail 2>/dev/null; "
        f"gunzip -c {_q(archive)} | {target} 2>&1; exit $?"
    )


def _build_retention_command(backup: Backup) -> str:
    dest = _dest(backup)
    glob = f"{_slug(backup.name)}-*.{_ext(backup.backup_type)}"
    keep = max(1, backup.retention)
    # cd first so the glob isn't broken by spaces in dest; slug/ext are sanitised.
    return (
        f"cd {_q(dest)} 2>/dev/null && "
        f"ls -1t {glob} 2>/dev/null | tail -n +{keep + 1} | xargs -r rm -f"
    )


def _parse_size(stdout: str) -> int | None:
    m = _SIZE_RE.search(stdout or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _clean_output(stdout: str, stderr: str) -> str:
    text = _SIZE_RE.sub("", stdout or "").strip()
    if stderr and stderr.strip():
        text = (text + "\n" + stderr.strip()).strip()
    return text[:_OUTPUT_CAP]


# ── Core execution ──────────────────────────────────────────────────────────

async def perform_backup(db, server: Server, backup: Backup) -> BackupRun:
    """Run a backup, persist a BackupRun, apply retention, update job status."""
    now = datetime.now(tz=timezone.utc)
    archive = _archive_path(backup, now)

    run = BackupRun(
        backup_id=backup.id, server_id=server.id, user_id=backup.user_id,
        action="backup", status="running", artifact_path=archive,
    )
    db.add(run)
    await db.flush()

    status = "failed"
    size: int | None = None
    output = ""
    try:
        cmd = _build_backup_command(backup, archive)
        stdout, stderr, code = await connection_manager.execute(server, cmd)
        size = _parse_size(stdout)
        output = _clean_output(stdout, stderr)
        status = "success" if code == 0 else "failed"
    except NotImplementedError:
        output = f"Backups for '{server.connection_type}' connections are not supported yet."
    except Exception as exc:  # noqa: BLE001
        logger.warning("Backup %s failed: %s", backup.id, exc)
        output = f"Could not connect to the server: {exc}"

    run.status = status
    run.size_bytes = size
    run.output = output or None
    run.completed_at = datetime.now(tz=timezone.utc)

    backup.last_run = now
    backup.last_status = status
    if backup.cron_expression:
        try:
            backup.next_run = scheduler_service.compute_next_run(backup.cron_expression)
        except Exception:  # noqa: BLE001
            backup.next_run = None

    # Prune old archives only after a successful backup.
    if status == "success":
        try:
            await connection_manager.execute(server, _build_retention_command(backup))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Retention prune failed for backup %s: %s", backup.id, exc)

    await db.commit()
    await db.refresh(run)
    return run


async def perform_restore(db, server: Server, backup: Backup, source_run: BackupRun) -> BackupRun:
    """Restore the archive produced by ``source_run`` back onto the server."""
    archive = source_run.artifact_path
    run = BackupRun(
        backup_id=backup.id, server_id=server.id, user_id=backup.user_id,
        action="restore", status="running", artifact_path=archive,
    )
    db.add(run)
    await db.flush()

    status = "failed"
    output = ""
    if not archive:
        output = "Source run has no artifact to restore."
    else:
        try:
            cmd = _build_restore_command(backup, archive)
            stdout, stderr, code = await connection_manager.execute(server, cmd)
            output = _clean_output(stdout, stderr)
            status = "success" if code == 0 else "failed"
        except NotImplementedError:
            output = f"Restore for '{server.connection_type}' connections is not supported yet."
        except Exception as exc:  # noqa: BLE001
            logger.warning("Restore %s failed: %s", backup.id, exc)
            output = f"Could not connect to the server: {exc}"

    run.status = status
    run.output = output or None
    run.completed_at = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


# ── Scheduling integration (APScheduler, shared with scheduler_service) ───────

def _job_id(backup_id) -> str:
    return f"backup:{backup_id}"


def schedule_backup(backup: Backup) -> None:
    """Register (or replace) the cron job for an active, scheduled backup."""
    if not (backup.is_active and backup.cron_expression):
        unschedule_backup(backup.id)
        return
    try:
        from apscheduler.triggers.cron import CronTrigger

        trigger = CronTrigger.from_crontab(backup.cron_expression, timezone="UTC")
        scheduler_service.get_scheduler().add_job(
            _execute_backup_job,
            trigger=trigger,
            args=[str(backup.id)],
            id=_job_id(backup.id),
            replace_existing=True,
        )
        logger.debug("Scheduled backup %s (%s)", backup.name, backup.cron_expression)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not schedule backup %s: %s", backup.id, exc)


def unschedule_backup(backup_id) -> None:
    try:
        scheduler_service.get_scheduler().remove_job(_job_id(backup_id))
    except Exception:  # noqa: BLE001
        pass


async def load_all_backups() -> None:
    """Register every active, scheduled backup with APScheduler (on startup)."""
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(Backup).where(
                Backup.is_active == True,  # noqa: E712
                Backup.cron_expression.isnot(None),
            )
        )
        backups = rows.scalars().all()

    count = 0
    for b in backups:
        try:
            schedule_backup(b)
            count += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipped backup %s during load: %s", b.id, exc)
    logger.info("Loaded %d scheduled backups into APScheduler", count)


async def _execute_backup_job(backup_id: str) -> None:
    """APScheduler fire handler: look up the backup + server and run it."""
    logger.info("Firing scheduled backup %s", backup_id)
    async with AsyncSessionLocal() as db:
        b = (await db.execute(
            select(Backup).where(Backup.id == uuid.UUID(backup_id))
        )).scalar_one_or_none()
        if not b:
            logger.warning("Scheduled backup %s not found — skipping", backup_id)
            return
        s = (await db.execute(
            select(Server).where(Server.id == b.server_id)
        )).scalar_one_or_none()
        if not s:
            logger.warning("Server %s not found for backup %s — skipping", b.server_id, backup_id)
            return
        await perform_backup(db, s, b)
