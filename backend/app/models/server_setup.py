"""A record of setting one server up.

Persisted rather than held in memory because it takes ten minutes and the customer will
close the tab. The same reason missions are durable: the promise on screen is "it is safe
to leave this page", and that promise has to be true.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ServerSetup(Base):
    __tablename__ = "server_setups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"),
        nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    purpose: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|done|failed|stopped
    # Every step, with its own state — this IS the checklist the customer watches, so it is
    # stored rather than derived, and survives a restart exactly as they last saw it.
    steps: Mapped[list | None] = mapped_column(JSONB)
    current: Mapped[int] = mapped_column(Integer, default=0)
    failed_step: Mapped[str | None] = mapped_column(String(120))
    message: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
