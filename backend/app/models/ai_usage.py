"""AiUsage model — the AI token ledger (docs/AI-METERING.md §3.1, Brick 1).

One append-only row per model call. Stores counts and labels only — NEVER prompt or
response content (no secrets by construction). Source of truth for both the per-user
monthly action counter and our own cost accounting.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiUsage(Base):
    __tablename__ = "ai_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Who the call is billed to (team pooling: per-server chat bills the server owner).
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="SET NULL")
    )
    # 'chat' | 'fleet_chat' | 'script_gen' | 'explain' | 'schedule_parse' | 'batch'
    feature: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(60), default="")
    # 'included' (our key / plan quota) | 'byok' (user's own key — unmetered)
    fuel: Mapped[str] = mapped_column(String(10), default="included")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    # Plan-quota units consumed: the first call of a user request carries 1 (or the
    # batch per-server 1); follow-up calls in the same request (explain, inline script
    # generation) carry 0.
    actions: Mapped[int] = mapped_column(SmallInteger, default=0)
    status: Mapped[str] = mapped_column(String(15), default="ok")  # ok | provider_error
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
