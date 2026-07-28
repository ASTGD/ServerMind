"""A watched service on a server.

Deliberately mirrors ``UptimeMonitor``: same streak field, same status vocabulary, same
"alert on change" state. Two monitors that behave the same way should look the same in
the database, or the next person has to learn two models to reason about one idea.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ServiceMonitor(Base):
    __tablename__ = "service_monitors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"),
        nullable=False, index=True)

    unit: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failure_threshold: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    # Restart is opt-in and bounded. The window exists so a service that fails once a
    # week is not treated like one failing every ninety seconds.
    auto_restart: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_restarts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    restart_window_seconds: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)

    current_status: Mapped[str] = mapped_column(String(10), default="unknown", nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_state: Mapped[str | None] = mapped_column(String(20))
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_status_change: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    restart_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    restart_window_started: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_restart_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the bound is hit. A monitor that has stopped trying must say so loudly —
    # silence here would look identical to a service that is behaving.
    gave_up: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
