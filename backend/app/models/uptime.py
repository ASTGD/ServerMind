"""Uptime monitoring — is the site actually reachable, from outside?

Two deliberate choices encoded here:

1. **Checks run from ServerAlly, not from the monitored server.** Uptime means "a visitor
   can reach it". A check run on the box itself passes while DNS is broken, the firewall
   blocks 443, or the whole server is off the internet — exactly the outages that matter.
2. **A 200 is not proof.** ``expected_keyword`` lets a monitor assert the page really is
   the site (a hacked or half-broken site very often returns 200 with a blank body or a
   PHP error). This mirrors the mission verification gate's content rule.

``consecutive_failures`` exists so one network blip never pages anyone: a monitor goes
DOWN only after ``failure_threshold`` checks in a row have failed.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UptimeMonitor(Base):
    __tablename__ = "uptime_monitors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Optional: ties the monitor to a server so a failure can point at the box to fix.
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    method: Mapped[str] = mapped_column(String(10), default="GET")
    expected_status: Mapped[int] = mapped_column(Integer, default=200)
    # Optional text that must appear in the body — the "200 is not proof" guard.
    expected_keyword: Mapped[str | None] = mapped_column(String(255))

    interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=15)
    failure_threshold: Mapped[int] = mapped_column(Integer, default=2)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Live state
    current_status: Mapped[str] = mapped_column(String(10), default="unknown")  # up|down|unknown
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_status_change: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_response_ms: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)

    # HTTPS certificate expiry, refreshed daily (ssl_service). Only meaningful for an
    # https:// monitor — a plain-http one simply has no certificate to inspect.
    cert_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cert_days_left: Mapped[int | None] = mapped_column(Integer)
    cert_issuer: Mapped[str | None] = mapped_column(String(255))
    cert_state: Mapped[str | None] = mapped_column(String(12))   # ok|warning|critical|expired|unknown
    cert_error: Mapped[str | None] = mapped_column(String(300))
    cert_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cert_warn_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)

    # Where a state change is announced (reuses notification_service).
    channel: Mapped[str | None] = mapped_column(String(20))          # email|webhook|slack
    channel_target: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UptimeCheck(Base):
    """One probe result — the history behind the uptime percentage."""

    __tablename__ = "uptime_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uptime_monitors.id", ondelete="CASCADE"),
        index=True, nullable=False,
    )
    status: Mapped[str] = mapped_column(String(10), nullable=False)   # up | down
    http_status: Mapped[int | None] = mapped_column(Integer)
    response_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(500))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
