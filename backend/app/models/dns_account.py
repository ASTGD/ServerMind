"""A connected DNS provider account.

Mirrors ``CloudAccount``: one row per connected provider, the credential as an
AES-256-GCM JSON blob, and nothing about the zones cached locally. Records are read
live on every request — a cached copy of DNS would drift from the authoritative answer,
and stale DNS shown as current is worse than no DNS screen at all.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DnsAccount(Base):
    __tablename__ = "dns_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True)

    provider: Mapped[str] = mapped_column(String(30), nullable=False)   # cloudflare
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    # Provider-shaped JSON, encrypted. Never returned by any endpoint.
    encrypted_credential: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
