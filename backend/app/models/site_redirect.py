"""A redirect belonging to one website.

Kept here as well as in the web-server config for the reason every list in this product is:
the page has to open, and say something true, when the server is unreachable. The config is
what is LIVE; this table is what was asked for, and `is_applied` is the difference — which
is the dot on the row.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SiteRedirect(Base):
    __tablename__ = "site_redirects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    redirect_from: Mapped[str] = mapped_column(String(500), nullable=False)
    redirect_to: Mapped[str] = mapped_column(String(500), nullable=False)
    #: nginx's own rewrite flag: "redirect" (302) or "permanent" (301).
    redirect_type: Mapped[str] = mapped_column(String(20), nullable=False,
                                               default="redirect")

    #: Whether it is really in the web server's configuration. False means it is recorded
    #: and not live — never shown as if it were working.
    is_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

    __table_args__ = (
        # The same path twice on one site is two rules where the second can never run.
        UniqueConstraint("site_id", "redirect_from", name="uq_site_redirect_from"),
    )
