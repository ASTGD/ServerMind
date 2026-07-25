"""Public status pages — show customers that the site is up, without showing them anything else.

A status page is served **unauthenticated** at ``/status/<slug>``, so the design rule is
strict: the public payload is built from an explicit allowlist and can only ever contain
what the owner deliberately chose to publish.

In particular a status page NEVER exposes:

- the monitored **URL** (a monitor may point at an internal admin path),
- the **server** it belongs to (name, host, IP),
- the internal **error text** (e.g. *"the expected text 'Welcome to my shop' was missing"*
  tells the world what we check for),
- who owns it.

Visitors see only: the page title, the display names the owner chose, up/down, and uptime
percentages. That is what a status page is for.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StatusPage(Base):
    __tablename__ = "status_pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # The public address: /status/<slug>. Unique across all users.
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    support_url: Mapped[str | None] = mapped_column(String(500))

    # Off by default: a page is only reachable once the owner deliberately publishes it.
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StatusPageItem(Base):
    """One monitor shown on a page, under a name the owner chooses."""

    __tablename__ = "status_page_items"
    __table_args__ = (UniqueConstraint("page_id", "monitor_id", name="uq_status_page_item"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("status_pages.id", ondelete="CASCADE"), index=True, nullable=False
    )
    monitor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("uptime_monitors.id", ondelete="CASCADE"), nullable=False
    )
    # The public label. Defaults to the monitor's name, but the owner can rename it so the
    # page says "Website" rather than an internal monitor name.
    display_name: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
