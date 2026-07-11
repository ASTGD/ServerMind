from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """Application user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    preferred_language: Mapped[str] = mapped_column(String(10), default="en")
    # How often Ally emails a proactive fleet-health digest: 'off' | 'weekly' | 'daily'.
    # Deterministic (fleet_service scoring — no AI cost); reuses the notification email
    # plumbing. Weekly by default so users hear what needs attention without opening the app.
    digest_frequency: Mapped[str] = mapped_column(
        String(10), default="weekly", server_default="weekly"
    )
    # How much Ally decides on its own: 'proactive' | 'normal' | 'careful' (Track D).
    # Shapes how Ally ASKS and how much it assumes/auto-approves; NEVER relaxes the hard
    # safety rails (blocklist, verify gate, injection defence, destructive-step confirm).
    ally_mode: Mapped[str] = mapped_column(
        String(10), default="normal", server_default="normal"
    )
    # Subscription plan ('free' | 'pro'). Set manually until a billing provider is
    # chosen (docs/AI-METERING.md §8 — the billing webhook is deliberately not built).
    plan: Mapped[str] = mapped_column(String(10), default="free", server_default="free")
    # Internal staff flag — gates the admin-only Dev Door (Prompt Inspector / eval
    # runner). NEVER granted through signup or billing; set by hand on a trusted
    # account. Guards every /api/dev endpoint. See docs/EVAL-DRIVEN-DEV.md.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_secret: Mapped[str | None] = mapped_column(String(255))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # JSON array of SHA-256 hashes of one-time 2FA recovery codes (never plaintext).
    totp_recovery_codes: Mapped[list | None] = mapped_column(JSONB)
    # Bumped on logout/password-change to invalidate all previously issued tokens
    # (tokens carry a "tv" claim that must match). See dependencies/auth.py.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
