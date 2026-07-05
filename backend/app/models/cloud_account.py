from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CloudAccount(Base):
    """A connected cloud provider account (Assets Phase C). We store an encrypted,
    provider-shaped credential JSON and use it to discover + import instances as `servers`
    rows. Never a login to the instances themselves — the cloud API only lists them."""

    __tablename__ = "cloud_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # aws|digitalocean|hetzner|gcp|azure
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_credential: Mapped[str] = mapped_column(Text, nullable=False)  # AES-256-GCM JSON blob
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
