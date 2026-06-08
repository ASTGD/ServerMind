import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CommandLog(Base):
    """Record of every AI-driven command execution."""

    __tablename__ = "command_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    server_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    user_input: Mapped[str] = mapped_column(Text, nullable=False)
    user_language: Mapped[str | None] = mapped_column(String(10))
    ai_plan: Mapped[dict | None] = mapped_column(JSONB)
    commands: Mapped[list | None] = mapped_column(JSONB)
    output: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(20))  # 'success'|'failed'|'partial'|'blocked'|'pending_approval'
    ai_explanation: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(String(10))
    execution_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
