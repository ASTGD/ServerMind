"""White-label branding — make client-facing output look like the agency's, not ours.

One row per user. It applies to everything a *customer of our customer* might see:
public status pages and client reports. It deliberately does NOT change the app itself —
an agency's own staff still know they are using ServerAlly.

``hide_serverally_branding`` is the actual white-label switch. Everything else (name, logo,
colour, support link) is additive branding that is useful even without it.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Branding(Base):
    __tablename__ = "branding"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, index=True, nullable=False,
    )

    company_name: Mapped[str | None] = mapped_column(String(120))
    logo_url: Mapped[str | None] = mapped_column(String(500))
    # Hex like #4F46E5. Validated on write — it is interpolated into client-facing CSS.
    primary_color: Mapped[str | None] = mapped_column(String(9))
    support_url: Mapped[str | None] = mapped_column(String(500))
    support_email: Mapped[str | None] = mapped_column(String(255))
    footer_text: Mapped[str | None] = mapped_column(Text)

    # The white-label switch: drop "Monitored by ServerAlly" from client-facing output.
    hide_serverally_branding: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
