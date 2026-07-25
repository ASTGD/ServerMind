"""Uptime sweep — probe every due monitor, announce real state changes.

Runs on APScheduler (ENABLE_SCHEDULER-gated, like the metrics and threat workers). Each
monitor carries its own ``interval_seconds``, so the sweep runs often and only checks the
monitors that are actually due.

**We announce transitions, not checks.** A monitor that has been down for six hours does
not send 72 emails — one when it goes down, one when it recovers. That is the same
"only when it newly worsens" rule the threat worker uses, and it is what keeps alerts
trustworthy enough to act on.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.uptime import UptimeCheck, UptimeMonitor
from app.services import notification_service, uptime_service

logger = logging.getLogger(__name__)

# Keep raw check history for a month — enough for a 30-day uptime figure.
CHECK_RETENTION_DAYS = 30
# Probe at most this many monitors concurrently, so a big fleet can't exhaust sockets.
_CONCURRENCY = 10


async def _announce(monitor: UptimeMonitor, went_down: bool) -> None:
    """Tell the owner a monitor changed state. Best-effort — never breaks the sweep."""
    if not monitor.channel or not monitor.channel_target:
        return
    if went_down:
        subject = f"🔴 {monitor.name} is DOWN"
        body = (
            f"{monitor.name} is not responding correctly.\n\n"
            f"URL: {monitor.url}\n"
            f"Problem: {monitor.last_error or 'unknown'}\n\n"
            "ServerAlly checks this from outside your server, so this is what a visitor sees."
        )
    else:
        subject = f"✅ {monitor.name} is back up"
        body = f"{monitor.name} is responding normally again.\n\nURL: {monitor.url}"

    try:
        if monitor.channel == "email":
            await notification_service.send_email(monitor.channel_target, subject, body)
        else:  # webhook | slack — both take a JSON post
            await notification_service.send_webhook(
                monitor.channel_target,
                {
                    "text": f"{subject}\n{body}",
                    "monitor": monitor.name,
                    "url": monitor.url,
                    "status": "down" if went_down else "up",
                    "error": monitor.last_error,
                },
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Uptime alert for %s could not be sent: %s", monitor.id, exc)


async def _check_one(monitor_id) -> None:
    """Probe one monitor and fold the result into its state, in its own session."""
    async with AsyncSessionLocal() as db:
        monitor = (await db.execute(
            select(UptimeMonitor).where(UptimeMonitor.id == monitor_id)
        )).scalar_one_or_none()
        if monitor is None or not monitor.is_active:
            return

        result = await uptime_service.probe(monitor)
        now = datetime.now(tz=timezone.utc)

        new_status, failures, changed = uptime_service.next_state(
            current_status=monitor.current_status or "unknown",
            consecutive_failures=monitor.consecutive_failures or 0,
            ok=result.ok,
            failure_threshold=monitor.failure_threshold or 2,
        )

        monitor.current_status = new_status
        monitor.consecutive_failures = failures
        monitor.last_checked = now
        monitor.last_response_ms = result.response_ms
        monitor.last_error = None if result.ok else result.error
        if changed:
            monitor.last_status_change = now

        db.add(UptimeCheck(
            monitor_id=monitor.id,
            status="up" if result.ok else "down",
            http_status=result.http_status,
            response_ms=result.response_ms,
            error=(result.error or None) if not result.ok else None,
        ))
        await db.commit()

        if changed:
            logger.info("Uptime: %s is now %s", monitor.name, new_status)
            await _announce(monitor, went_down=(new_status == "down"))


async def check_due_monitors() -> None:
    """Probe every monitor whose interval has elapsed. Safe to call every minute."""
    now = datetime.now(tz=timezone.utc)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(UptimeMonitor).where(UptimeMonitor.is_active.is_(True))
        )).scalars().all()

    due = [
        m.id for m in rows
        if m.last_checked is None
        or (now - m.last_checked).total_seconds() >= (m.interval_seconds or 300)
    ]
    if not due:
        return

    logger.info("Uptime sweep: checking %d monitor(s)", len(due))
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _guarded(mid):
        async with sem:
            try:
                await _check_one(mid)
            except Exception as exc:  # noqa: BLE001 — one bad monitor can't stop the sweep
                logger.warning("Uptime check failed for %s: %s", mid, exc)

    await asyncio.gather(*(_guarded(mid) for mid in due))


async def prune_old_checks() -> None:
    """Drop check history beyond the retention window."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=CHECK_RETENTION_DAYS)
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(UptimeCheck).where(UptimeCheck.checked_at < cutoff))
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Uptime history prune failed: %s", exc)
