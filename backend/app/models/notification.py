from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notification(Base):
    """An in-app notification — e.g. a background playbook install finished
    (Update 17, Phase 2). Lightweight; ``server_id``/``ref_id`` are soft links
    (no FK) so deleting a server/run never breaks the bell."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)        # 'playbook_run'
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(20))               # success|failed|stalled|cancelled
    server_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # the run id
    read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
