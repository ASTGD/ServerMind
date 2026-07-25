"""Offsite backup destinations — S3-compatible object storage.

A destination is a reusable, user-owned bucket configuration (AWS S3, Cloudflare R2,
Backblaze B2, DigitalOcean Spaces, Wasabi, MinIO — all speak the S3 API), which a backup
job can point at so archives leave the server they came from.

**The secret never reaches the customer's server.** Uploads use a short-lived *presigned
URL* generated here; the server only ever sees that URL, so a compromised server cannot
read the bucket or the other backups in it. ``encrypted_secret_key`` is AES-256-GCM at
rest and is never returned by the API.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BackupDestination(Base):
    __tablename__ = "backup_destinations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Cosmetic label for the UI — every provider below is driven through the S3 API.
    provider: Mapped[str] = mapped_column(String(20), default="s3")  # s3|r2|b2|spaces|wasabi|minio

    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(64))
    # Required for non-AWS providers (R2/B2/Spaces/MinIO); None means real AWS S3.
    endpoint_url: Mapped[str | None] = mapped_column(String(500))
    # Optional key prefix ("folder") inside the bucket.
    prefix: Mapped[str | None] = mapped_column(String(500))

    access_key_id: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_secret_key: Mapped[str] = mapped_column(Text, nullable=False)  # AES-256-GCM

    last_status: Mapped[str | None] = mapped_column(String(20))   # ok | failed
    last_error: Mapped[str | None] = mapped_column(Text)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
