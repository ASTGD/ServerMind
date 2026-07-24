"""MCP activity — a durable record of every ACTION a connected AI client takes over MCP.

This is what powers the user-facing "MCP Activity" feed (Settings → Connected
applications): with MCP the AI runs in the customer's *own* app, so only the tool
*calls* reach us — we can't show the AI's reasoning, but we can show everything it
*does*, live. Each action is written twice: once at START (``status='running'``) and once
at FINISH (``ok`` / ``blocked`` / ``error``), so the feed shows a "⏳ running… → ✓ done"
transition even with a plain poll.

Only ACTIONS are recorded (run_command + the write tools) — passive reads
(list/get/read) are not, so the feed reads as "what the AI changed", not chatter.

Never stores a credential: ``command`` is the run_command text run through the same
secret redactor the file tools use, so a password in a command never lands here.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class McpActivity(Base):
    __tablename__ = "mcp_activity"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Owner of the connection (the bearer's subject). Scopes the feed to your own actions.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    client_id: Mapped[str | None] = mapped_column(String(255))
    client_name: Mapped[str | None] = mapped_column(String(255))     # e.g. "Claude"
    tool: Mapped[str] = mapped_column(String(64), nullable=False)     # e.g. "run_command"
    server_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    server_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="running")  # running|ok|blocked|error
    label: Mapped[str] = mapped_column(String(255), nullable=False)   # friendly summary ("Installing docker.io")
    command: Mapped[str | None] = mapped_column(Text)                 # run_command text, secret-redacted
    exit_code: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str | None] = mapped_column(Text)                  # short result note / block reason / error
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
