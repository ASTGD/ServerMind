"""On-call escalation — the difference between an email you missed and waking up.

ServerAlly already *detects* things (uptime, threats, metric thresholds, expiring
certificates) and emails once, hoping someone reads it. Escalation adds the part that
actually gets a human: a **policy** (tell me, then text me, then text my colleague) and an
**incident** that keeps escalating until somebody acknowledges it.

The design in one line: **escalation is a layer, not a new alert source.** Sources raise an
incident; the policy decides who is told and what happens if nobody answers.

Two properties shape the whole model, because getting either wrong destroys trust in every
alert we ever send:

1. **Escalation always stops.** Acknowledging stops it, resolving stops it, and the repeat
   count bounds it. There is no path that pages forever.
2. **One incident per problem.** ``dedup_key`` is unique among open incidents, so a
   flapping monitor raises one incident, not one per check.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Severity, worst first. A policy only escalates at or above its `min_severity`; anything
# below still sends the ordinary one-shot email, so nothing gets quieter than it is today.
SEVERITIES = ("critical", "high", "warning", "info")

CHANNELS = ("email", "sms", "telegram", "slack", "webhook")

STATUS_OPEN = "open"
STATUS_ACKNOWLEDGED = "acknowledged"
STATUS_RESOLVED = "resolved"


class EscalationPolicy(Base):
    """Who to tell, and what to do when they don't answer."""

    __tablename__ = "escalation_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Used by any server that hasn't picked a policy of its own.
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Only escalate at or above this severity — "page me for outages, email me for warnings".
    min_severity: Mapped[str] = mapped_column(String(20), default="high", nullable=False)

    # After the last step, keep nudging every `repeat_minutes`, at most `max_repeats` times.
    # max_repeats is what guarantees escalation terminates even if nobody ever acknowledges.
    repeat_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    max_repeats: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EscalationStep(Base):
    """One rung of the ladder: "after N minutes, reach me here"."""

    __tablename__ = "escalation_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalation_policies.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Minutes from when the incident STARTED, not from the previous step — "text me 5
    # minutes in" is what a person means, and it makes the schedule trivial to reason about.
    after_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    # "My phone", "Ops Slack" — so the UI reads as people, not addresses.
    label: Mapped[str | None] = mapped_column(String(120))


class Incident(Base):
    """Something that needs a human, and the state of getting one."""

    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), index=True
    )

    # Which detector raised this: uptime | threat | metric | ssl | manual.
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    # Stable identity of the underlying problem, e.g. "uptime:<monitor_id>". Unique among
    # OPEN incidents (partial index below) so one problem is one incident.
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default="high", nullable=False)

    status: Mapped[str] = mapped_column(String(20), default=STATUS_OPEN, nullable=False, index=True)

    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalation_policies.id", ondelete="SET NULL")
    )
    # How far up the ladder we've climbed, and how many post-ladder nudges we've sent.
    step_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repeats_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # When the worker should look at this incident again. NULL = escalation is finished.
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notifications_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # SHA-256 of the acknowledge token, for O(1) lookup when someone follows the link.
    # An attacker who can silence your alerts is an attacker who can hide a break-in, so
    # the plaintext token is never stored.
    ack_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    # The token itself, AES-256-GCM. Every message in the ladder carries the acknowledge
    # link — step 3 reaches a *different person*, who also needs to be able to stop the
    # paging — so the worker must be able to re-read it. Hash for O(1) lookup, ciphertext
    # for re-use, plaintext never at rest.
    ack_token_enc: Mapped[str | None] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Free text: "Sharwat" (in-app) or "the link we sent to +8801…" (token).
    acknowledged_by: Mapped[str | None] = mapped_column(String(255))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the detector itself cleared, rather than a person closing it.
    auto_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_incidents_user_status", "user_id", "status"),
    )


class NotificationProvider(Base):
    """Account-level credentials for the channels that need one (Twilio, Telegram).

    The credential is per ACCOUNT, not per step — one Twilio account sends to every number
    in every policy. ``encrypted_config`` is AES-256-GCM at rest and is never returned by
    any endpoint, the same rule as server credentials and backup destinations.
    """

    __tablename__ = "notification_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # twilio | telegram
    encrypted_config: Mapped[str] = mapped_column(Text, nullable=False)

    # SMS costs real money, so it gets a hard ceiling per calendar month.
    monthly_limit: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    sent_this_month: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_notification_provider_user"),
    )
