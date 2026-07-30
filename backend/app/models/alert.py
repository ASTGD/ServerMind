from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ServerMetric(Base):
    """Point-in-time server metric snapshot."""

    __tablename__ = "server_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    server_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    cpu_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    ram_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    ram_used_mb: Mapped[int | None] = mapped_column(Integer)
    ram_total_mb: Mapped[int | None] = mapped_column(Integer)
    disk_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    disk_used_gb: Mapped[float | None] = mapped_column(Numeric(10, 2))
    disk_total_gb: Mapped[float | None] = mapped_column(Numeric(10, 2))
    load_1: Mapped[float | None] = mapped_column(Numeric(6, 3))
    load_5: Mapped[float | None] = mapped_column(Numeric(6, 3))
    load_15: Mapped[float | None] = mapped_column(Numeric(6, 3))
    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Alert(Base):
    """Metric alert rule."""

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    server_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    metric: Mapped[str | None] = mapped_column(String(50))
    condition: Mapped[str | None] = mapped_column(String(20))
    threshold: Mapped[float | None] = mapped_column(Numeric(10, 2))
    channel: Mapped[str | None] = mapped_column(String(20))        # 'email' | 'webhook' | 'slack'
    channel_target: Mapped[str | None] = mapped_column(String(500))
    #: A named channel to use instead of the inline destination above.
    #:
    #: Both exist on purpose. Every rule created before channels kept its own copy of the
    #: destination, and rewriting them all in a migration would guess at which named channel
    #: the customer meant. So the sender prefers `channel_id` when set and falls back to the
    #: inline pair otherwise — no rule stops working, and new ones stop duplicating.
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_channels.id", ondelete="SET NULL"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_triggered: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Whether this rule was over its threshold at the previous check.
    #:
    #: Needed to send exactly one "back to normal" message on the way down.
    #: ``last_triggered`` cannot do that job — it stays set forever after the first breach,
    #: so recovering from it would mean sending a recovery notice on every sweep for the
    #: rest of the rule's life. Same state-change rule the uptime, service and threat
    #: monitors already follow: one message down, one message up, nothing in between.
    is_breaching: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False,
                                               server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
