"""Webhooks — telling the customer's systems what happened, verifiably.

Three things make a webhook trustworthy rather than merely present:

1. **The receiver can prove it was us.** Every request carries an HMAC-SHA256 signature over
   ``timestamp.body`` with a per-endpoint secret. Without a signature, a webhook is an
   unauthenticated POST from the internet claiming to be ServerAlly — anyone who learns the
   URL could fake "your server is compromised". The timestamp is inside the signed material
   so a captured request cannot be replayed later.
2. **We stop knocking on a dead door.** Retries back off, and an endpoint that keeps failing
   is switched off with a reason the customer can read. Otherwise one abandoned URL generates
   work for as long as the account exists.
3. **The payload carries no secrets.** Each event is built from an explicit allowlist, so a
   new column on a model can never quietly start appearing in someone's Slack channel.

The URL itself is guarded by ``outbound_guard`` — see that module for why a customer-supplied
URL is an SSRF vector and what is done about it.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import requests as _requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import WEBHOOK_EVENTS, WebhookDelivery, WebhookEndpoint
from app.services import crypto_service, outbound_guard

logger = logging.getLogger(__name__)

_TIMEOUT = 10
# Anything larger than this is our bug, not the customer's problem — cap it so we never post
# a megabyte of command output to someone's endpoint.
MAX_PAYLOAD_BYTES = 60_000

SIGNATURE_HEADER = "X-ServerAlly-Signature"
EVENT_HEADER = "X-ServerAlly-Event"
DELIVERY_HEADER = "X-ServerAlly-Delivery"

# Attempt N waits this long. Five attempts over ~30 minutes covers a deploy or a restart on
# the receiving side without hammering it.
RETRY_BACKOFF_MINUTES = (1, 2, 5, 10, 15)
MAX_ATTEMPTS = len(RETRY_BACKOFF_MINUTES)
# Consecutive failed *deliveries* before the endpoint is switched off.
FAILURES_BEFORE_DISABLE = 10

# A signature older than this is refused by a correct receiver. Documented here because it is
# the number their verification code needs.
TOLERANCE_SECONDS = 300


def generate_secret() -> str:
    """A signing secret. ``whsec_`` prefixed so it is recognisable in the customer's config."""
    return f"whsec_{secrets.token_urlsafe(32)}"


def sign(secret: str, timestamp: int, body: bytes) -> str:
    """The value of the signature header.

    Format ``t=<unix>,v1=<hex>`` over ``<t>.<body>``. Signing the timestamp *with* the body
    is what stops a captured request being replayed tomorrow — a signature over the body
    alone stays valid forever.
    """
    signed = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify(secret: str, header: str, body: bytes, now: int | None = None,
           tolerance: int = TOLERANCE_SECONDS) -> bool:
    """Verify a signature the way a receiver should.

    Kept here, next to ``sign``, so the documentation we give customers is generated from
    code that is actually tested rather than from prose someone wrote once.
    """
    now = now if now is not None else int(datetime.now(tz=timezone.utc).timestamp())
    parts = dict(
        piece.split("=", 1) for piece in (header or "").split(",") if "=" in piece
    )
    try:
        timestamp = int(parts.get("t", ""))
    except ValueError:
        return False
    if abs(now - timestamp) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    # Constant time: a fast "wrong" answer leaks how much of the digest matched.
    return hmac.compare_digest(expected, parts.get("v1", ""))


def read_secret(endpoint: WebhookEndpoint) -> str | None:
    try:
        return crypto_service.decrypt(endpoint.encrypted_secret)
    except Exception:  # noqa: BLE001
        logger.error("Could not read the signing secret for endpoint %s", endpoint.id)
        return None


def valid_events(events: list[str] | None) -> list[str]:
    """Keep only events we actually emit.

    Silently dropping an unknown event would leave the customer waiting for something that
    can never arrive, so the router rejects unknown names instead — this is the last line.
    """
    return sorted({e for e in (events or []) if e in WEBHOOK_EVENTS})


def public_endpoint(endpoint: WebhookEndpoint, *, include_secret: bool = False) -> dict:
    """What the API may say about an endpoint.

    The secret is included only when explicitly asked for, from a dedicated authenticated
    route: the receiver genuinely needs it to verify signatures, but it should not ride along
    in every list response where it would end up in logs and browser history.
    """
    out = {
        "id": str(endpoint.id),
        "name": endpoint.name,
        "url": endpoint.url,
        "events": list(endpoint.events or []),
        "is_active": endpoint.is_active,
        "failure_count": endpoint.failure_count,
        "disabled_reason": endpoint.disabled_reason,
        "last_delivery_at": endpoint.last_delivery_at.isoformat() if endpoint.last_delivery_at else None,
        "last_status": endpoint.last_status,
        "created_at": endpoint.created_at.isoformat() if endpoint.created_at else None,
    }
    if include_secret:
        out["secret"] = read_secret(endpoint)
    return out


def public_delivery(row: WebhookDelivery) -> dict:
    return {
        "id": str(row.id),
        "event": row.event,
        "status": row.status,
        "attempts": row.attempts,
        "http_status": row.http_status,
        "error": row.error,
        "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ── Queueing an event ────────────────────────────────────────────────────────

async def emit(db: AsyncSession, user_id: uuid.UUID, event: str, data: dict) -> int:
    """Queue ``event`` for every active endpoint of this user subscribed to it.

    Returns how many deliveries were queued. **Never raises** — a webhook is a side effect of
    something more important (an incident, a finished playbook), and failing to queue one must
    not fail that.
    """
    if event not in WEBHOOK_EVENTS:
        logger.warning("Refusing to emit unknown webhook event '%s'", event)
        return 0
    try:
        endpoints = (await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.user_id == user_id,
                WebhookEndpoint.is_active.is_(True),
                WebhookEndpoint.events.any(event),
            )
        )).scalars().all()
        if not endpoints:
            return 0

        payload = build_payload(event, data)
        now = datetime.now(tz=timezone.utc)
        for endpoint in endpoints:
            db.add(WebhookDelivery(
                endpoint_id=endpoint.id, event=event, payload=payload,
                status="pending", next_attempt_at=now,
            ))
        await db.commit()
        return len(endpoints)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not queue webhook '%s': %s", event, exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0


def build_payload(event: str, data: dict) -> dict:
    """The event envelope. ``data`` is expected to be already-safe, allowlisted fields."""
    body = {
        "event": event,
        "occurred_at": datetime.now(tz=timezone.utc).isoformat(),
        "data": data,
    }
    # Truncate rather than refuse: a customer would rather receive a trimmed event than
    # silently receive nothing because one field was long.
    if len(json.dumps(body)) > MAX_PAYLOAD_BYTES:
        body["data"] = _trim(data)
    return body


# How much of any one string survives trimming. Enough to be useful in a Slack message,
# small enough that no realistic number of fields can re-inflate the payload.
_FIELD_MAX = 500


def _trim(data: dict) -> dict:
    """Shrink an oversized event body.

    The obvious version — "keep the first few scalar fields" — does not work, because the
    field that made the payload huge is itself usually a string (a playbook's output), so
    keeping it keeps the problem. Every string value is therefore capped individually.
    """
    trimmed: dict = {
        "truncated": True,
        "note": "This event was too large to send in full; fetch the details from the API.",
    }
    for key, value in list(data.items())[:8]:
        if isinstance(value, str):
            trimmed[key] = value[:_FIELD_MAX] + ("…" if len(value) > _FIELD_MAX else "")
        elif isinstance(value, (int, float, bool)) or value is None:
            trimmed[key] = value
    return trimmed


# ── Delivering ───────────────────────────────────────────────────────────────

def _post_sync(url: str, body: bytes, headers: dict) -> tuple[int, str]:
    """Blocking POST. Returns ``(status, error)``; error is empty on success."""
    try:
        # The guard runs here, immediately before the socket, so a hostname that has been
        # repointed at an internal address since it was saved is still refused.
        outbound_guard.check_url(url)
    except outbound_guard.BlockedURL as exc:
        return 0, str(exc)

    try:
        resp = _requests.post(url, data=body, headers=headers, timeout=_TIMEOUT,
                              allow_redirects=False)
    except _requests.exceptions.Timeout:
        return 0, f"Your endpoint didn't answer within {_TIMEOUT} seconds."
    except _requests.exceptions.SSLError:
        return 0, "We couldn't make a secure connection — check the HTTPS certificate."
    except _requests.exceptions.ConnectionError:
        return 0, "We couldn't connect to that address."
    except Exception as exc:  # noqa: BLE001
        return 0, f"Could not send: {type(exc).__name__}"

    if 200 <= resp.status_code < 300:
        return resp.status_code, ""
    # Deliberately not the response body — that is the customer's server output and could
    # contain anything, including their own secrets.
    return resp.status_code, f"Your endpoint answered {resp.status_code}."


def headers_for(event: str, delivery_id: str, secret: str, body: bytes,
                timestamp: int | None = None) -> dict:
    timestamp = timestamp or int(datetime.now(tz=timezone.utc).timestamp())
    return {
        "Content-Type": "application/json",
        "User-Agent": "ServerAlly-Webhooks/1",
        EVENT_HEADER: event,
        DELIVERY_HEADER: delivery_id,
        SIGNATURE_HEADER: sign(secret, timestamp, body),
    }


def next_attempt(attempts: int, now: datetime) -> datetime | None:
    """When to try again after ``attempts`` failures, or None once we give up."""
    if attempts >= MAX_ATTEMPTS:
        return None
    return now + timedelta(minutes=RETRY_BACKOFF_MINUTES[attempts])


def _redirect_note(status: int) -> str:
    return ("Your endpoint redirected us. Redirects aren't followed (a redirect could point "
            "somewhere private), so please use the final address.")
