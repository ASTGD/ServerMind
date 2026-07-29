"""The last mail-health result for a domain.

One row per domain, overwritten each check — not a history. What matters is "is my email
working now" and "has it got worse since last time"; nobody has ever asked what their SPF
record looked like in March. Keeping the previous verdict is enough to alert on a change,
and it keeps the table the size of the customer's domain list rather than growing forever.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MailHealthRecord(Base):
    __tablename__ = "mail_health"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True)
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), index=True)

    domain: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    verdict: Mapped[str] = mapped_column(String(12), default="unknown")  # ok|at risk|failing
    score: Mapped[int] = mapped_column(Integer, default=0)
    # The findings as shown, so the panel renders from what was actually measured rather
    # than re-deriving it from records that may have changed since.
    findings: Mapped[list | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)

    has_mx: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    spf: Mapped[str | None] = mapped_column(Text)
    dkim_selector: Mapped[str | None] = mapped_column(String(64))
    dmarc: Mapped[str | None] = mapped_column(Text)
    sending_ip: Mapped[str | None] = mapped_column(String(45))

    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
