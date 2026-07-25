"""Backup service — file/database backups over SSH with retention + restore.

Backups are produced by running standard tools on the server (``tar``,
``mysqldump``, ``pg_dump``) via :func:`connection_manager.execute`, gzipped into
``dest_dir``. Old archives beyond ``retention`` are pruned. Restores stream the
chosen archive back through ``tar -x`` / ``mysql`` / ``psql``.

Optional database passwords are passed via environment variables (``MYSQL_PWD`` /
``PGPASSWORD``) so they never appear in the process argument list.

A job may also carry an **offsite destination** (S3-compatible bucket). After a successful
local backup the archive is uploaded straight from the server to that bucket using a
short-lived presigned URL — the bucket credentials never reach the server. See
:mod:`app.services.offsite_service`.
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
from app.models.backup_destination import BackupDestination
from app.models.server import Server
from app.services import connection_manager, crypto_service, offsite_service, scheduler_service
from app.services.offsite_service import OffsiteError

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


# ── Offsite copy ────────────────────────────────────────────────────────────

async def _load_destination(db, backup: Backup) -> BackupDestination | None:
    if not backup.destination_id:
        return None
    return (await db.execute(
        select(BackupDestination).where(BackupDestination.id == backup.destination_id)
    )).scalar_one_or_none()


async def _copy_offsite(
    db, server: Server, backup: Backup, archive: str, size: int | None
) -> tuple[str, str, str | None]:
    """Upload a finished archive to the job's offsite bucket.

    Returns ``(offsite_status, note, remote_key)`` where status is
    ``uploaded`` | ``failed`` | ``skipped``. Never raises — the caller decides what a
    failure means for the run. The local archive is deleted ONLY after a confirmed
    upload and only when ``keep_local`` is off, so a failed upload can never lose data.
    """
    dest = await _load_destination(db, backup)
    if dest is None:
        return "failed", "Offsite copy skipped: the destination was deleted. Re-select one on this job.", None

    if size is not None and size > offsite_service.MAX_SINGLE_PUT_BYTES:
        gb = size / (1024 ** 3)
        return (
            "skipped",
            f"Offsite copy skipped: this archive is {gb:.1f} GB and the 5 GB single-upload "
            "limit applies. The archive is still on the server.",
            None,
        )

    filename = archive.rsplit("/", 1)[-1]
    key = offsite_service.object_key(dest, _slug(backup.name), filename)
    try:
        url = await offsite_service.presign_put(dest, key)
    except OffsiteError as exc:
        return "failed", f"Offsite copy failed: {exc} The archive is still on the server.", None

    try:
        stdout, stderr, code = await connection_manager.execute(
            server, offsite_service.build_upload_command(archive, url)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Offsite upload failed for backup %s: %s", backup.id, exc)
        return "failed", f"Offsite copy failed: {type(exc).__name__}. The archive is still on the server.", None

    http_code = offsite_service.parse_upload_code(stdout)
    if code != 0 or http_code != 200:
        detail = offsite_service.scrub_urls(_clean_output(stdout, stderr))[:300]
        return (
            "failed",
            f"Offsite copy failed (HTTP {http_code or '?'}). The archive is still on the "
            f"server. {detail}".strip(),
            None,
        )

    note = f"Offsite copy uploaded to {dest.name}."

    # Local cleanup only now that the remote copy is confirmed.
    if not backup.keep_local:
        try:
            await connection_manager.execute(server, f"rm -f {_q(archive)}")
            note += " Local archive removed (keep-local is off)."
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not remove local archive for backup %s: %s", backup.id, exc)

    # Retention applies offsite too, or the bucket grows forever.
    try:
        prefix = offsite_service.object_key(dest, _slug(backup.name), "")
        removed = await offsite_service.prune_remote(dest, prefix, max(1, backup.retention))
        if removed:
            note += f" Pruned {removed} old copy/copies offsite."
    except OffsiteError as exc:
        logger.warning("Offsite prune failed for backup %s: %s", backup.id, exc)
        note += f" (Could not prune old offsite copies: {exc})"

    return "uploaded", note, key


async def _ensure_local_archive(
    db, server: Server, backup: Backup, source_run: BackupRun, archive: str
) -> str:
    """Make sure ``archive`` exists on the server before a restore reads it.

    With ``keep_local`` off — or after local retention pruned it — the only surviving copy
    is offsite, so fetch it back. Returns a note for the run output ('' when the local file
    was already there). Raises OffsiteError if the archive is only offsite and unreachable.
    """
    if not source_run.remote_key:
        return ""

    try:
        _out, _err, code = await connection_manager.execute(server, f"test -f {_q(archive)}")
        if code == 0:
            return ""  # local copy is still there — nothing to do
    except Exception:  # noqa: BLE001 — fall through and try the offsite copy
        pass

    dest = await _load_destination(db, backup)
    if dest is None:
        raise OffsiteError("the destination for this job no longer exists")

    url = await offsite_service.presign_get(dest, source_run.remote_key)
    stdout, stderr, code = await connection_manager.execute(
        server, offsite_service.build_download_command(url, archive)
    )
    if code != 0:
        detail = offsite_service.scrub_urls(_clean_output(stdout, stderr))[:300]
        raise OffsiteError(f"download from {dest.name} failed. {detail}".strip())
    return f"Fetched the archive back from {dest.name}."


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

    # ── Offsite copy ─────────────────────────────────────────────────────────
    # Only after a good local archive. A configured-but-failed upload marks the whole run
    # failed (the job's goal was "a copy somewhere else", and it wasn't met) and NEVER
    # deletes the local archive — so a failure loses nothing.
    if status == "success" and backup.destination_id:
        offsite_status, note, key = await _copy_offsite(db, server, backup, archive, size)
        run.remote_key = key
        run.offsite_status = offsite_status
        if offsite_status != "uploaded":
            status = "failed"
        output = (output + "\n" + note).strip() if output else note

    run.status = status
    run.size_bytes = size
    run.output = offsite_service.scrub_urls(output) or None
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
            # The archive may live only offsite (keep_local off, or it was pruned locally).
            # Fetch it back before restoring.
            fetch_note = await _ensure_local_archive(db, server, backup, source_run, archive)
            if fetch_note:
                output = fetch_note
            cmd = _build_restore_command(backup, archive)
            stdout, stderr, code = await connection_manager.execute(server, cmd)
            output = (output + "\n" + _clean_output(stdout, stderr)).strip()
            status = "success" if code == 0 else "failed"
        except OffsiteError as exc:
            output = f"Could not fetch the backup from offsite storage: {exc}"
        except NotImplementedError:
            output = f"Restore for '{server.connection_type}' connections is not supported yet."
        except Exception as exc:  # noqa: BLE001
            logger.warning("Restore %s failed: %s", backup.id, exc)
            output = f"Could not connect to the server: {exc}"

    run.status = status
    run.output = offsite_service.scrub_urls(output) or None
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
