"""Scheduler service — APScheduler integration for recurring tasks.

Manages scheduled tasks backed by PostgreSQL.
Uses APScheduler AsyncIOScheduler to fire tasks at their cron times.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter
from sqlalchemy import select
from sqlalchemy import update as sa_update

from app.database import AsyncSessionLocal
from app.models.scheduled_task import ScheduledTask
from app.models.server import Server

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


# ── Scheduler lifecycle ───────────────────────────────────────────────────────

def get_scheduler() -> AsyncIOScheduler:
    """Return the singleton APScheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def start() -> None:
    """Start the APScheduler (called on application startup)."""
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        logger.info("APScheduler started")


def shutdown() -> None:
    """Stop the APScheduler gracefully (called on application shutdown)."""
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
        logger.info("APScheduler stopped")


# ── Cron helpers ──────────────────────────────────────────────────────────────

def compute_next_run(cron_expression: str) -> datetime:
    """Return the next UTC fire time for a cron expression."""
    now = datetime.now(tz=timezone.utc)
    it = croniter(cron_expression, now)
    return it.get_next(datetime)


def validate_cron(cron_expression: str) -> bool:
    """Return True if the cron expression is valid."""
    try:
        croniter(cron_expression, datetime.now(tz=timezone.utc))
        return True
    except Exception:
        return False


# ── Job management ────────────────────────────────────────────────────────────

def schedule_task(task: ScheduledTask) -> None:
    """Add or replace a job in the scheduler for the given task."""
    if not task.is_active:
        return
    try:
        trigger = CronTrigger.from_crontab(task.cron_expression, timezone="UTC")
        get_scheduler().add_job(
            _execute_task,
            trigger=trigger,
            args=[str(task.id)],
            id=str(task.id),
            replace_existing=True,
        )
        logger.debug("Scheduled task %s (%s)", task.title, task.cron_expression)
    except Exception as exc:
        logger.warning("Could not schedule task %s: %s", task.id, exc)


def unschedule_task(task_id: str) -> None:
    """Remove a job from the scheduler (silently if not found)."""
    try:
        get_scheduler().remove_job(task_id)
    except Exception:
        pass


async def load_all_tasks() -> None:
    """Load every active task from the DB and register it with the scheduler."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduledTask).where(ScheduledTask.is_active == True)  # noqa: E712
        )
        tasks = result.scalars().all()

    count = 0
    for task in tasks:
        try:
            schedule_task(task)
            count += 1
        except Exception as exc:
            logger.warning("Skipped task %s during load: %s", task.id, exc)

    logger.info("Loaded %d scheduled tasks into APScheduler", count)


# ── Task execution ────────────────────────────────────────────────────────────

async def _execute_task(task_id: str) -> None:
    """Fire handler: look up task → run command on server → update status."""
    from app.models.playbook import Playbook, UserScript  # avoid circular at module level
    from app.services import connection_manager

    task_uuid = uuid.UUID(task_id)
    logger.info("Firing scheduled task %s", task_id)

    async with AsyncSessionLocal() as db:
        # Fetch task
        row = await db.execute(select(ScheduledTask).where(ScheduledTask.id == task_uuid))
        task = row.scalar_one_or_none()
        if not task:
            logger.warning("Scheduled task %s not found — skipping", task_id)
            return

        # Fetch server
        srv_row = await db.execute(select(Server).where(Server.id == task.server_id))
        server = srv_row.scalar_one_or_none()
        if not server:
            logger.warning("Server %s not found for task %s — skipping", task.server_id, task_id)
            return

        # Resolve the script / command to execute
        script: str | None = None
        payload = task.payload or {}

        if task.task_type == "command":
            script = payload.get("command")

        elif task.task_type == "playbook":
            pb_id = payload.get("playbook_id")
            if pb_id:
                pb_row = await db.execute(select(Playbook).where(Playbook.id == uuid.UUID(pb_id)))
                pb = pb_row.scalar_one_or_none()
                if pb:
                    script = (
                        pb.script_powershell
                        if server.shell == "powershell"
                        else pb.script_bash
                    )

        elif task.task_type == "user_script":
            us_id = payload.get("user_script_id")
            if us_id:
                us_row = await db.execute(select(UserScript).where(UserScript.id == uuid.UUID(us_id)))
                us = us_row.scalar_one_or_none()
                if us:
                    script = us.script_content

        # Execute
        now = datetime.now(tz=timezone.utc)
        last_status = "failed"

        if script:
            try:
                _stdout, _stderr, exit_code = await connection_manager.execute(server, script)
                last_status = "success" if exit_code == 0 else "failed"
                logger.info("Task %s finished with status=%s", task_id, last_status)
            except Exception as exc:
                logger.error("Task %s execution error: %s", task_id, exc)
        else:
            logger.warning("Task %s has no runnable script — marking failed", task_id)

        # Compute next run time
        try:
            next_run = compute_next_run(task.cron_expression)
        except Exception:
            next_run = None

        # Persist result
        await db.execute(
            sa_update(ScheduledTask)
            .where(ScheduledTask.id == task_uuid)
            .values(last_run=now, last_status=last_status, next_run=next_run)
        )
        await db.commit()
