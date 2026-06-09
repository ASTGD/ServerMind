"""Pydantic schemas for the Backups feature."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

BACKUP_TYPES = {"files", "mysql", "postgres"}


class BackupCreate(BaseModel):
    """Create a backup job. ``db_password`` (if given) is encrypted at rest
    and never returned."""

    name: str = Field(min_length=1, max_length=255)
    backup_type: str
    source: str = Field(min_length=1, max_length=1024)
    dest_dir: str = Field(default="/var/backups/servermind", max_length=1024)
    db_user: str | None = None
    db_password: str | None = None
    retention: int = Field(default=7, ge=1, le=365)
    cron_expression: str | None = None
    human_schedule: str | None = None
    is_active: bool = True


class BackupUpdate(BaseModel):
    """Patch a backup job. Omitted fields are unchanged. Send db_password=''
    to clear the stored credential."""

    name: str | None = Field(default=None, max_length=255)
    backup_type: str | None = None
    source: str | None = Field(default=None, max_length=1024)
    dest_dir: str | None = Field(default=None, max_length=1024)
    db_user: str | None = None
    db_password: str | None = None
    retention: int | None = Field(default=None, ge=1, le=365)
    cron_expression: str | None = None
    human_schedule: str | None = None
    is_active: bool | None = None


class BackupOut(BaseModel):
    """A backup job configuration (no secrets)."""

    id: uuid.UUID
    server_id: uuid.UUID
    name: str
    backup_type: str
    source: str
    dest_dir: str
    db_user: str | None = None
    has_db_cred: bool = False
    retention: int
    cron_expression: str | None = None
    human_schedule: str | None = None
    is_active: bool
    last_run: datetime | None = None
    last_status: str | None = None
    next_run: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BackupRunOut(BaseModel):
    """One backup/restore execution record."""

    id: uuid.UUID
    backup_id: uuid.UUID
    server_id: uuid.UUID
    action: str
    status: str
    artifact_path: str | None = None
    size_bytes: int | None = None
    output: str | None = None
    started_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class RestoreBody(BaseModel):
    """Restore request — restore from a specific run, or the latest backup."""

    run_id: uuid.UUID | None = None
