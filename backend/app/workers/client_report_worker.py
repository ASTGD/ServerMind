"""Monthly client-report delivery.

Runs once a day (APScheduler, ENABLE_SCHEDULER-gated) and emails the report for every
subscription whose send day is today. Deterministic and free — ``client_report_service``
does no AI work — so a missed run costs nothing but a late email.

Two rules make this safe to run unattended:

- **Send once per month.** ``is_due`` refuses if we already sent in the same calendar
  month, so a restart, a re-run, or a second scheduler instance cannot double-send to a
  paying agency's client.
- **One failure never stops the sweep.** A bad recipient or an SMTP hiccup marks that one
  subscription failed and the loop continues.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.branding import Branding
from app.models.client_report import ClientReportSubscription
from app.models.server import Server
from app.services import branding_service, client_report_service, notification_service

logger = logging.getLogger(__name__)


def is_due(sub: ClientReportSubscription, today: datetime) -> bool:
    """Should this subscription send today?

    A month has as few as 28 days, so a send_day above the month's length would silently
    never fire — day 28 is the cap at write time, and we also fire on the last day of the
    month for anything higher that predates that cap.
    """
    if not sub.is_active:
        return False

    day = today.day
    if sub.send_day != day:
        # Catch a day that this month does not have (defensive — the API caps at 28).
        import calendar
        last = calendar.monthrange(today.year, today.month)[1]
        if not (sub.send_day > last and day == last):
            return False

    # Already sent this calendar month → never send twice.
    if sub.last_sent:
        sent = sub.last_sent
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
        if (sent.year, sent.month) == (today.year, today.month):
            return False
    return True


async def send_one(db, sub: ClientReportSubscription) -> bool:
    """Build and email one subscription's report. Returns True when it was sent."""
    server = await db.get(Server, sub.server_id)
    if server is None:
        logger.info("Client report %s skipped — server is gone", sub.id)
        return False

    report = await client_report_service.build(db, server, sub.period_days)
    report["summary"] = client_report_service.plain_summary(report)
    branding = branding_service.public_branding(
        (await db.execute(
            select(Branding).where(Branding.user_id == sub.user_id)
        )).scalar_one_or_none()
    )
    email = client_report_service.render_email(
        report, branding, server.name, sub.recipient_name
    )
    await notification_service.send_email(
        sub.recipient_email, email["subject"], email["text"], html=email["html"]
    )
    return True


async def send_due_reports(today: datetime | None = None) -> int:
    """Send every subscription due today. Returns how many were emailed."""
    today = today or datetime.now(tz=timezone.utc)

    async with AsyncSessionLocal() as db:
        subs = (await db.execute(
            select(ClientReportSubscription).where(
                ClientReportSubscription.is_active.is_(True)
            )
        )).scalars().all()
        due = [s for s in subs if is_due(s, today)]

    logger.info("Client reports: %d due of %d active", len(due), len(subs))

    sent = 0
    for sub in due:
        try:
            async with AsyncSessionLocal() as db:
                fresh = await db.get(ClientReportSubscription, sub.id)
                if fresh is None or not is_due(fresh, today):
                    continue
                ok = await send_one(db, fresh)
                fresh.last_sent = today
                fresh.last_status = "sent" if ok else "skipped"
                await db.commit()
                sent += 1 if ok else 0
        except Exception as exc:  # noqa: BLE001 — one client must not stop the rest
            logger.warning("Client report failed for subscription %s: %s", sub.id, exc)
            try:
                async with AsyncSessionLocal() as db:
                    fresh = await db.get(ClientReportSubscription, sub.id)
                    if fresh:
                        fresh.last_status = "failed"
                        await db.commit()
            except Exception:  # noqa: BLE001
                pass
    logger.info("Client reports complete: %d emailed", sent)
    return sent
