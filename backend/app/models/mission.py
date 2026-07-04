"""Mission model — a durable, resumable agentic ops mission (Ally Missions Phase 3).

Missions used to live entirely on the WebSocket: if the socket dropped (browser
closed, network blip, server reload), the mission vanished mid-flight. Persisting
the mission — goal, skill, target, the full step transcript, and status — makes it
(a) survivable: a dropped mission is marked ``interrupted`` and can be RESUMED from
its saved transcript, and (b) reviewable: a history of what Ally did and changed.

``steps`` is the JSON-serialised transcript (the same list the engine plans from), so
resuming = reload it and continue. ``server_id`` is SET NULL on server delete (history
outlives the server); ``server_name`` is denormalised so the row still reads cleanly.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Lifecycle states. running/awaiting_approval are live; interrupted is resumable;
# complete/blocked/failed/stopped are terminal.
MISSION_STATUSES = (
    "running", "awaiting_approval", "blocked", "complete", "failed", "stopped", "interrupted",
)
RESUMABLE_STATUSES = ("interrupted",)


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Home server (where the mission started). NULL for a fleet mission, or once the
    # server is deleted — history survives either way.
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    server_name: Mapped[str | None] = mapped_column(String(255))  # denormalised for display

    skill_slug: Mapped[str | None] = mapped_column(String(100))
    goal: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False, index=True)
    verified: Mapped[bool | None] = mapped_column(Boolean)  # verification-gate outcome (null until done)
    summary: Mapped[str | None] = mapped_column(Text)        # final summary / block reason / caveat

    steps: Mapped[str] = mapped_column(Text, default="[]", nullable=False)  # JSON transcript
    steps_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # denormalised count
    budget: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
