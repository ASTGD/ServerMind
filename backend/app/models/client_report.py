"""Scheduled client-report delivery.

An agency sends this to *their* client, so the recipient belongs to a **server** (each
server is usually one client's site) rather than to the account. One row = "email the
report for this server to this address, monthly".

Kept as its own table rather than columns on ``servers`` so a server can have several
recipients later without another migration.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClientReportSubscription(Base):
    __tablename__ = "client_report_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), index=True, nullable=False
    )

    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Optional label so the agency knows who this goes to ("Acme Ltd — Jane").
    recipient_name: Mapped[str | None] = mapped_column(String(255))

    # Day of month to send on (1–28, so every month has one).
    send_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_sent: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
