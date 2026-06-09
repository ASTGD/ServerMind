"""Backup models — backup job configurations and their run history."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Backup(Base):
    """A backup job configuration for a server.

    A job describes *what* to back up (``backup_type`` + ``source``), *where*
    to store archives on the server (``dest_dir``), how many to keep
    (``retention``), and optionally *when* to run automatically
    (``cron_expression``). Optional database credentials are stored
    AES-256-GCM encrypted and never returned in API responses.
    """

    __tablename__ = "backups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("servers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    backup_type: Mapped[str] = mapped_column(String(20), nullable=False)  # files | mysql | postgres
    source: Mapped[str] = mapped_column(String(1024), nullable=False)     # dir path | database name
    dest_dir: Mapped[str] = mapped_column(String(1024), default="/var/backups/servermind")

    db_user: Mapped[str | None] = mapped_column(String(255))
    encrypted_db_cred: Mapped[str | None] = mapped_column(Text)  # AES-256-GCM, optional

    retention: Mapped[int] = mapped_column(Integer, default=7)

    cron_expression: Mapped[str | None] = mapped_column(String(100))
    human_schedule: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))
    next_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BackupRun(Base):
    """One execution of a backup job — a backup or a restore."""

    __tablename__ = "backup_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    backup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("backups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    action: Mapped[str] = mapped_column(String(20), default="backup")  # backup | restore
    status: Mapped[str] = mapped_column(String(20), default="running")  # success | failed | running
    artifact_path: Mapped[str | None] = mapped_column(String(1024))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    output: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
