"""Fleet-health digest worker.

Runs once a day (APScheduler, ENABLE_SCHEDULER-gated) and emails each user whose
cadence is due their proactive fleet-health digest: weekly users on Mondays, daily
users every day, 'off' users never. Deterministic + cheap (fleet_service scoring — no
AI, no SSH); one user's failure never stops the sweep.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import User
from app.services import digest_service

logger = logging.getLogger(__name__)


async def send_due_digests(weekday: int | None = None) -> int:
    """Send digests to every active user whose cadence is due today. ``weekday`` (Mon=0)
    defaults to the current UTC weekday — passed in tests for determinism. Returns the
    number of digests actually emailed."""
    if weekday is None:
        weekday = datetime.now(tz=timezone.utc).weekday()

    async with AsyncSessionLocal() as db:
        users = (
            await db.execute(
                select(User).where(
                    User.is_active == True,  # noqa: E712
                    User.digest_frequency != "off",
                )
            )
        ).scalars().all()

    due = [u for u in users if digest_service.is_due(u.digest_frequency, weekday)]
    logger.info("Digest run (weekday=%d): %d users due of %d subscribed", weekday, len(due), len(users))

    sent = 0
    for user in due:
        try:
            async with AsyncSessionLocal() as db:
                fresh = await db.get(User, user.id)
                if fresh and await digest_service.send_for_user(db, fresh):
                    sent += 1
        except Exception as exc:  # noqa: BLE001 — one user must not stop the sweep
            logger.warning("Digest failed for user %s: %s", user.id, exc)
    logger.info("Digest run complete: %d emailed", sent)
    return sent
