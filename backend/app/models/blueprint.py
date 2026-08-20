"""A blueprint run — a ready-made long job, executed step by step.

NOT a mission. A mission is our own AI planning each step; a blueprint is a FIXED list of
steps ServerAlly already knows how to do, with no model call anywhere in the run. The
customer's AI (over MCP) or the app starts one; this row is the durable record the screen
reads, checkpointed after every step so a restart or a reload loses nothing.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BlueprintRun(Base):
    __tablename__ = "blueprint_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), index=True, nullable=False)

    blueprint_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Only non-secret inputs are ever stored here (a domain, a site type). A blueprint that
    # one day needs a secret input must encrypt it the way playbook runs do — never widen
    # this column's meaning instead.
    inputs: Mapped[dict] = mapped_column(JSONB, default=dict)

    # running → done | failed | stopped. There is deliberately NO 'waiting' run status:
    # a step that waits for the human is a per-step state, and the run continues past it.
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    current: Mapped[int] = mapped_column(Integer, default=0)
    # [{key,label,state,note,started_at,finished_at}] — state: pending|running|done|
    # failed|skipped|waiting
    steps: Mapped[list] = mapped_column(JSONB, default=list)

    message: Mapped[str | None] = mapped_column(Text)
    # Plain sentences the run learned about the machine ("4 GB memory, 78 GB free").
    found: Mapped[list] = mapped_column(JSONB, default=list)
    # What only a human can do, collected from 'waiting' steps ("point shop.com at ...").
    left_for_you: Mapped[list] = mapped_column(JSONB, default=list)

    source: Mapped[str] = mapped_column(String(16), default="app")   # 'app' | 'mcp'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
