"""Autopilot — Ally works on a schedule, within limits you set.

The Pro flagship (docs/PRO-FEATURES-PLAN.md §4 #1+#2). An autopilot task is a *standing
instruction*: a goal, a schedule, and a **policy** saying how far Ally may go on its own.

The policy is the whole feature. It is consulted at exactly the point a human would
otherwise be asked to approve a step, so:

- The **absolute blocklist still runs first** and is unaffected — a blocked command is
  refused before approval is ever considered (``terminal._run_mission``), so no policy can
  authorise a catastrophic command.
- The policy can only decide *"may Ally proceed without me?"* — never *"is this allowed?"*
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# How far Ally may go without asking.
POLICY_REPORT_ONLY = "report_only"   # look and report; stop before changing anything
POLICY_SAFE_FIXES = "safe_fixes"     # make ordinary repairs; stop for risky ones
POLICY_FULL = "full"                 # proceed on anything the blocklist permits
POLICIES = {POLICY_REPORT_ONLY, POLICY_SAFE_FIXES, POLICY_FULL}


class AutopilotTask(Base):
    __tablename__ = "autopilot_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)      # the standing instruction

    policy: Mapped[str] = mapped_column(String(20), default=POLICY_REPORT_ONLY, nullable=False)

    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    human_schedule: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Where the run report goes (reuses notification_service).
    channel: Mapped[str | None] = mapped_column(String(20))       # email | webhook | slack
    channel_target: Mapped[str | None] = mapped_column(String(500))
    # Only tell me when something actually happened or needs me (vs every run).
    notify_on_change_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))   # mirrors the mission status
    last_mission_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
