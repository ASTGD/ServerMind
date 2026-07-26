"""Webhook delivery worker — sends queued events, retries, and gives up sensibly.

Runs every minute. Picks up pending deliveries whose next attempt is due, posts them, and
records what happened so the customer can see it.

Two decisions worth naming:

- **A dead endpoint gets switched off.** After ``FAILURES_BEFORE_DISABLE`` consecutive failed
  deliveries the endpoint is deactivated with a reason. Retrying an abandoned URL forever
  costs us work every minute for the life of the account and helps nobody.
- **Success resets the failure count.** An endpoint that is merely flaky must not accumulate
  its way to being disabled over months of occasional blips.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.integration import WebhookDelivery, WebhookEndpoint
from app.services import webhook_service

logger = logging.getLogger(__name__)

_BATCH = 100
# Keep the delivery log long enough to debug a failure a customer noticed yesterday.
DELIVERY_RETENTION_DAYS = 14


async def deliver_one(db: AsyncSession, delivery: WebhookDelivery, now: datetime) -> bool:
    """Attempt one delivery. Returns True when it was accepted."""
    endpoint = await db.get(WebhookEndpoint, delivery.endpoint_id)
    if endpoint is None or not endpoint.is_active:
        delivery.status = "cancelled"
        delivery.error = "The endpoint was removed or switched off."
        delivery.next_attempt_at = None
        await db.commit()
        return False

    secret = webhook_service.read_secret(endpoint)
    if secret is None:
        delivery.status = "failed"
        delivery.error = "We couldn't read this endpoint's signing secret. Recreate it."
        delivery.next_attempt_at = None
        await db.commit()
        return False

    body = json.dumps(delivery.payload or {}).encode()
    headers = webhook_service.headers_for(delivery.event, str(delivery.id), secret, body)
    status, error = await asyncio.to_thread(
        webhook_service._post_sync, endpoint.url, body, headers
    )

    delivery.attempts += 1
    delivery.http_status = status or None
    endpoint.last_delivery_at = now

    if not error:
        delivery.status = "delivered"
        delivery.error = None
        delivery.delivered_at = now
        delivery.next_attempt_at = None
        endpoint.last_status = "delivered"
        # A flaky endpoint must not accumulate its way to being disabled.
        endpoint.failure_count = 0
        await db.commit()
        return True

    if 300 <= status < 400:
        error = webhook_service._redirect_note(status)

    delivery.error = error[:500]
    endpoint.last_status = "failed"

    retry_at = webhook_service.next_attempt(delivery.attempts, now)
    delivery.next_attempt_at = retry_at
    delivery.status = "pending" if retry_at else "failed"

    # Count a whole GIVEN-UP delivery, not each attempt. Counting attempts looked equivalent
    # but is far more aggressive: a delivery is five attempts, so a ten-minute outage on the
    # customer's side would spend two events, reach the limit, and switch their webhook off —
    # leaving them to notice and re-enable it by hand. One consecutive failure here means the
    # endpoint stayed unreachable across a full ~33-minute retry cycle.
    if retry_at is None:
        endpoint.failure_count += 1

    if endpoint.failure_count >= webhook_service.FAILURES_BEFORE_DISABLE:
        endpoint.is_active = False
        endpoint.disabled_reason = (
            f"Switched off after {endpoint.failure_count} failed deliveries. "
            f"Last problem: {error[:150]}"
        )
        logger.info("Webhook endpoint %s disabled after repeated failures", endpoint.id)

    await db.commit()
    return False


async def run_deliveries(now: datetime | None = None) -> int:
    """One tick. Returns how many deliveries were accepted."""
    now = now or datetime.now(tz=timezone.utc)
    async with AsyncSessionLocal() as db:
        due = list((await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.status == "pending",
                WebhookDelivery.next_attempt_at.isnot(None),
                WebhookDelivery.next_attempt_at <= now,
            ).order_by(WebhookDelivery.next_attempt_at).limit(_BATCH)
        )).scalars().all())
        if not due:
            return 0

        logger.info("Webhook tick: %d delivery(s) due", len(due))
        sent = 0
        for delivery in due:
            try:
                if await deliver_one(db, delivery, now):
                    sent += 1
            except Exception as exc:  # noqa: BLE001 — one bad delivery can't stop the rest
                logger.warning("Webhook delivery %s failed: %s", delivery.id, exc)
                await db.rollback()
        return sent


async def prune_deliveries() -> None:
    """Drop delivery history beyond each account's retention window.

    Delegates to ``retention_worker`` — the single owner of deletion.
    """
    from app.workers import retention_worker

    try:
        await retention_worker.sweep("webhooks")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Webhook delivery prune failed: %s", exc)
