"""Checks every watched domain's email once a day, and says so when it gets worse.

Daily, not minutely: these are DNS records, and a domain's SPF does not change between
breakfast and lunch. Checking more often would be queries nobody reads.

The alert rule is the one used everywhere else in the product — **worse is news, the same
is not**. A domain that has been at risk for a month must not email about it every day, or
the message that matters gets filtered with the rest. Recovery is silent but re-arms, so
the next time it breaks it is heard.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.mail_health import MailHealthRecord
from app.models.user import User
from app.services import mail_service, notification_service

logger = logging.getLogger(__name__)

# One domain at a time is plenty — a check is a handful of small DNS queries — but a few
# in parallel keeps a large fleet from taking all morning.
CONCURRENCY = 6


async def check_one(record_id) -> None:
    async with AsyncSessionLocal() as db:
        record = await db.get(MailHealthRecord, record_id)
        if record is None or not record.is_active:
            return
        domain, previous = record.domain, record.verdict

    try:
        health = await mail_service.check_domain(domain)
    except Exception:  # noqa: BLE001 — a lookup failure must not stop the sweep
        logger.warning("Mail check failed for %s", domain, exc_info=True)
        return

    async with AsyncSessionLocal() as db:
        record = await db.get(MailHealthRecord, record_id)
        if record is None:
            return
        record.verdict = health.verdict
        record.score = health.score
        record.summary = mail_service.summarise(health)
        record.findings = [
            {"key": f.key, "severity": f.severity, "title": f.title,
             "detail": f.detail, "fix": f.fix} for f in health.findings
        ]
        record.has_mx = health.has_mx
        record.spf = health.spf
        record.dkim_selector = health.dkim_selector
        record.dmarc = health.dmarc
        record.sending_ip = health.sending_ip
        record.last_checked = datetime.now(timezone.utc)
        user_id = record.user_id
        await db.commit()

    if mail_service.should_alert(previous, health.verdict):
        await _tell_them(user_id, domain, health)


async def _tell_them(user_id, domain: str, health) -> None:
    """One message, naming what to fix. Best-effort: a mail failure never breaks a sweep."""
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if not user or not user.email:
                return
        worst = [f for f in health.findings if f.severity == "critical"] or health.findings
        lines = "\n".join(f"- {f.title}\n  {f.fix}" for f in worst[:5] if f.fix)
        await notification_service.send_email(
            user.email,
            f"Email problems on {domain}",
            f"{mail_service.summarise(health)}\n\n{lines}\n\n"
            "This is checked once a day. You will only hear from us again about this "
            "domain if it gets worse.")
    except Exception:  # noqa: BLE001
        logger.warning("Could not send the mail-health alert for %s", domain, exc_info=True)


async def check_many(ids: list) -> None:
    """Check a specific set of records now, at the same polite concurrency as the sweep.

    Used when a customer has just asked for a domain to be watched. Without this the first
    result would not appear until the next daily sweep, and the screen would be telling
    them something that is not true.
    """
    if not ids:
        return
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def guarded(rid):
        async with semaphore:
            try:
                await check_one(rid)
            except Exception:  # noqa: BLE001 — one bad domain must not stop the others
                logger.warning("First mail check failed for %s", rid, exc_info=True)

    await asyncio.gather(*(guarded(i) for i in ids))


async def sweep() -> dict:
    """Check every active domain. One slow domain must not hold up the rest."""
    async with AsyncSessionLocal() as db:
        ids = [r.id for r in (await db.execute(
            select(MailHealthRecord).where(MailHealthRecord.is_active.is_(True))
        )).scalars().all()]

    if not ids:
        return {"checked": 0}

    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def guarded(rid):
        async with semaphore:
            await check_one(rid)

    await asyncio.gather(*(guarded(i) for i in ids), return_exceptions=True)
    logger.info("Mail health sweep: %d domains checked", len(ids))
    return {"checked": len(ids)}
