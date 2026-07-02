"""AllyMemory model — Ally's long-term learned memory (Ally Brain Phase 5).

Short text notes Ally saves while working with the user: server facts, user
preferences, lessons from failures. Fully user-visible and user-deletable — no hidden
brain. Secrets never get here (memory_service filters before saving).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AllyMemory(Base):
    __tablename__ = "ally_memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Who saved it (the acting user in the conversation it came from).
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Set → a note about this server (shared with everyone who can access the server);
    # NULL → a note about the user themselves (preferences), injected in their chats.
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(12), default="fact")  # fact | preference | lesson
    content: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
