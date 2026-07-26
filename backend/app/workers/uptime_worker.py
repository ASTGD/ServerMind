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
from app.models.server import Server
from app.models.uptime import UptimeCheck, UptimeMonitor
from app.services import incident_service, notification_service, uptime_service, webhook_service

logger = logging.getLogger(__name__)

# Keep raw check history for a month — enough for a 30-day uptime figure.
CHECK_RETENTION_DAYS = 30
# Probe at most this many monitors concurrently, so a big fleet can't exhaust sockets.
_CONCURRENCY = 10


async def _escalate_down(db, monitor: UptimeMonitor) -> bool:
    """Open an on-call incident for a downed monitor.

    Returns True when escalation took over, in which case the plain one-shot email is
    skipped — the ladder's first step already tells the owner, and sending both would
    double-notify for the same outage.
    """
    server = await db.get(Server, monitor.server_id) if monitor.server_id else None
    raised = await incident_service.raise_for(
        db, user_id=monitor.user_id, server=server, source="uptime",
        dedup_key=f"uptime:{monitor.id}",
        title=f"{monitor.name} is down",
        message=(f"{monitor.url}\nProblem: {monitor.last_error or 'not responding'}\n\n"
                 "ServerAlly checks this from outside your server, so this is what a "
                 "visitor sees."),
        severity="critical",
    )
    return raised is not None


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
            went_down = new_status == "down"
            escalated = False
            try:
                if went_down:
                    escalated = await _escalate_down(db, monitor)
                else:
                    # The site is back. Close the incident so nobody is paged about a
                    # problem that has already fixed itself — the single fastest way to
                    # lose trust in an alerting system.
                    await incident_service.resolve_key(
                        db, monitor.user_id, f"uptime:{monitor.id}")
            except Exception as exc:  # noqa: BLE001 — escalation must not break the sweep
                logger.warning("Uptime escalation for %s failed: %s", monitor.id, exc)
            # A webhook fires on the transition regardless of escalation — it is the
            # customer's own integration, not a notification we might have replaced.
            await webhook_service.emit(
                db, monitor.user_id, "uptime.down" if went_down else "uptime.up",
                {"monitor_id": str(monitor.id), "name": monitor.name, "url": monitor.url,
                 "status": new_status, "error": monitor.last_error,
                 "response_ms": monitor.last_response_ms},
            )
            if not escalated:
                await _announce(monitor, went_down=went_down)


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


# ── Certificate expiry (daily) ───────────────────────────────────────────────
# Certificates change rarely, so this is its own daily job rather than part of the
# minute-by-minute uptime sweep. Alerts fire only when the state gets WORSE, so a cert
# 10 days out does not email for 10 days running.

async def _check_cert(monitor_id) -> None:
    from app.services import ssl_service

    async with AsyncSessionLocal() as db:
        monitor = (await db.execute(
            select(UptimeMonitor).where(UptimeMonitor.id == monitor_id)
        )).scalar_one_or_none()
        if monitor is None or not monitor.is_active:
            return
        target = ssl_service.host_and_port(monitor.url)
        if target is None:
            return  # plain http — nothing to inspect, and that is not a problem

        result = await ssl_service.inspect(monitor.url)
        now = datetime.now(tz=timezone.utc)

        if result.get("expired"):
            # Verification failed *because* it expired — the case we most need to report.
            days, state = -1, "expired"
        else:
            days = ssl_service.days_left(result.get("expires_at"), now)
            state = ssl_service.severity(days, monitor.cert_warn_days or ssl_service.DEFAULT_WARN_DAYS)

        previous = monitor.cert_state
        monitor.cert_expires_at = result.get("expires_at")
        monitor.cert_days_left = days
        monitor.cert_issuer = result.get("issuer")
        monitor.cert_state = state
        monitor.cert_error = (result.get("error") or None)
        monitor.cert_checked_at = now
        await db.commit()

        if state == "ok":
            # Renewed. Close any open certificate incident rather than leaving a solved
            # problem sitting in the owner's list.
            try:
                await incident_service.resolve_key(db, monitor.user_id, f"ssl:{monitor.id}")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Certificate incident close failed for %s: %s", monitor.id, exc)

        if ssl_service.should_alert(previous, state):
            host = target[0]
            subject, body = ssl_service.message(host, days, state)
            escalated = False
            try:
                # "expired" and "critical" (<=3 days) are outages in waiting; a plain
                # "warning" stays an email, because paging someone about routine renewal
                # is how people learn to ignore pages.
                if state in ("expired", "critical"):
                    server = await db.get(Server, monitor.server_id) if monitor.server_id else None
                    escalated = await incident_service.raise_for(
                        db, user_id=monitor.user_id, server=server, source="ssl",
                        dedup_key=f"ssl:{monitor.id}", title=subject.replace("[ServerAlly] ", ""),
                        message=body, severity="critical" if state == "expired" else "high",
                    ) is not None
            except Exception as exc:  # noqa: BLE001
                logger.warning("Certificate escalation for %s failed: %s", monitor.id, exc)

            await webhook_service.emit(
                db, monitor.user_id, "certificate.expiring",
                {"monitor_id": str(monitor.id), "name": monitor.name, "host": host,
                 "days_left": days, "state": state, "issuer": monitor.cert_issuer},
            )
            if escalated or not (monitor.channel and monitor.channel_target):
                return
            try:
                if monitor.channel == "email":
                    await notification_service.send_email(monitor.channel_target, subject, body)
                else:
                    await notification_service.send_webhook(
                        monitor.channel_target,
                        {"text": f"{subject}\n{body}", "host": host,
                         "days_left": days, "state": state},
                    )
                logger.info("Certificate alert sent for %s (%s, %s days)", host, state, days)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Certificate alert for %s could not be sent: %s", monitor.id, exc)


async def check_certificates() -> None:
    """Refresh certificate expiry for every active HTTPS monitor."""
    from app.services import ssl_service

    async with AsyncSessionLocal() as db:
        monitors = (await db.execute(
            select(UptimeMonitor).where(UptimeMonitor.is_active.is_(True))
        )).scalars().all()

    https = [m.id for m in monitors if ssl_service.host_and_port(m.url) is not None]
    if not https:
        return
    logger.info("Certificate sweep: checking %d monitor(s)", len(https))
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _guarded(mid):
        async with sem:
            try:
                await _check_cert(mid)
            except Exception as exc:  # noqa: BLE001 — one bad cert can't stop the sweep
                logger.warning("Certificate check failed for %s: %s", mid, exc)

    await asyncio.gather(*(_guarded(mid) for mid in https))
