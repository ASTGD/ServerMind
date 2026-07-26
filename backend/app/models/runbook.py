"""Custom runbooks — teaching Ally the account's own procedures.

ServerAlly ships expert procedures as files in ``app/skills``. This lets a customer add
their own: "when a client's WooCommerce checkout breaks, check these five things in this
order". Matched, ranked and injected through exactly the same machinery as the built-in
skills, so a runbook is as capable as ours — which is the point, and also the risk.

**A runbook is effectively a program Ally executes**, so who may write one is the whole
security question:

- Only an **account owner or admin** may author one. An owner can already run any command
  themselves, so a runbook grants them nothing new. If an *operator* could author one, they
  could write a procedure the owner later triggers unknowingly — that is a privilege boundary
  being crossed, and it is why authoring is restricted rather than open.
- A runbook belongs to the **owner's account** and applies to their team's sessions. That
  direction is legitimate delegation: the owner already outranks their operators. The
  dangerous direction is the one that is blocked.
- A runbook **cannot loosen the rails**. The command blocklist, the approval gate for
  destructive steps, the mission verification gate and ``ally_mode`` all sit below the prompt
  and are unaffected by anything a runbook says. The injected block states this explicitly,
  and a test asserts the wording stays.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# 'guide'   — injected into normal chat planning as an expert procedure.
# 'mission' — a step-by-step runbook the mission engine works through adaptively.
MODE_GUIDE = "guide"
MODE_MISSION = "mission"
RUNBOOK_MODES = (MODE_GUIDE, MODE_MISSION)

OS_FAMILIES = ("any", "linux", "windows")

# Same ceiling the built-in skills are held to, so a runbook cannot crowd out the rest of the
# prompt (server profile, memories, live snapshot) that Ally needs in order to be accurate.
BODY_MAX = 14_000
MAX_TRIGGERS = 20
# Per account. A runbook rides in the prompt menu, so an unbounded library would cost tokens
# on every single message.
MAX_RUNBOOKS = 30


class Runbook(Base):
    __tablename__ = "runbooks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The OWNING account, not the author's session — a team's runbooks live with the owner.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Who wrote it, for the audit trail. Kept even if that member later leaves.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    # Namespaced with a "my-" prefix when rendered, so a custom runbook can never be confused
    # with a built-in slug in a prompt, a ledger row or a log line.
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))

    # Phrases that make this runbook the match. Lowercased on save.
    triggers: Mapped[list[str]] = mapped_column(ARRAY(String(120)), default=list, nullable=False)
    os_family: Mapped[str] = mapped_column(String(20), default="any", nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default=MODE_GUIDE, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Mission mode: how many steps this procedure needs. Clamped by skill_service.
    budget: Mapped[int | None] = mapped_column(Integer)
    # Beats a built-in skill on an equal trigger count — "teach Ally YOUR procedure" only
    # means anything if the customer's version wins.
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    times_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_runbook_user_slug"),
    )
