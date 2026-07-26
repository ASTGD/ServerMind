"""API keys and webhooks — letting a customer's own code work with ServerAlly.

Two directions:

- **API keys (inbound)** — a long-lived credential so a deploy script, CI job or cron can
  call us. A browser login expires in 15 minutes, so today there is no way for a machine to
  authenticate at all.
- **Webhooks (outbound)** — we POST to their URL when something happens, so events can flow
  into their own dashboard or ticket system.

The one rule that shapes the key model: **an API key must never be able to become account
control.** It cannot change a password, touch 2FA, read a server credential, mint another
key, or delete anything. That is enforced structurally — the key only authenticates a
separate, bounded ``/api/v1`` surface, so the routes that could escalate are not merely
guarded, they are unreachable.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Deliberately only two. An "admin" scope would recreate the escalation path the whole
# design avoids.
SCOPE_READ = "read"
SCOPE_WRITE = "write"
API_SCOPES = (SCOPE_READ, SCOPE_WRITE)

# Events a customer can subscribe to. Named after what happened in their world, not after
# our internal tables.
WEBHOOK_EVENTS = (
    "incident.opened",
    "incident.acknowledged",
    "incident.resolved",
    "uptime.down",
    "uptime.up",
    "threat.detected",
    "playbook.finished",
    "mission.finished",
    "backup.failed",
    "certificate.expiring",
)


class ApiKey(Base):
    """A customer's key for the ServerAlly API."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # The first characters of the key, in clear. Shown in the UI ("sa_live_a1b2…") so a
    # customer can tell three keys apart and revoke the right one — the full secret is shown
    # exactly once, at creation, and never again.
    prefix: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # SHA-256 of the whole key. A key is a bearer credential: a database read must not yield
    # one, and unlike a password there is nothing to be gained from a slow hash because the
    # secret is 256 random bits rather than something a human chose.
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    scopes: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, nullable=False)

    # Purely informational, and deliberately coarse: writing an exact timestamp on every
    # request would turn each API call into a database write.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookEndpoint(Base):
    """Where to POST when something happens."""

    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)

    # The signing secret, AES-256-GCM at rest. The receiver needs it to verify our HMAC, so
    # unlike an API key it must be readable back — and it is shown to its owner on request,
    # because a signature they cannot verify is a signature that protects nothing.
    encrypted_secret: Mapped[str] = mapped_column(Text, nullable=False)

    events: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Consecutive failures. A dead endpoint is switched off rather than retried forever —
    # otherwise one abandoned URL generates work for as long as the account exists.
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    disabled_reason: Mapped[str | None] = mapped_column(String(255))
    last_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookDelivery(Base):
    """One attempt to deliver one event — the customer's debugging trail.

    Without this, "your webhook isn't firing" is unanswerable by either side.
    """

    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )

    event: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    # Why it failed, in the customer's language. Never the response body — that is their
    # server's output and could contain anything.
    error: Mapped[str | None] = mapped_column(String(500))

    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_webhook_deliveries_pending", "status", "next_attempt_at"),
    )
