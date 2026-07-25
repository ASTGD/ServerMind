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
    destination_id: uuid.UUID | None = None
    keep_local: bool = True


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
    destination_id: uuid.UUID | None = None
    keep_local: bool | None = None


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
    destination_id: uuid.UUID | None = None
    destination_name: str | None = None
    keep_local: bool = True
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
    remote_key: str | None = None
    offsite_status: str | None = None
    started_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class RestoreBody(BaseModel):
    """Restore request — restore from a specific run, or the latest backup."""

    run_id: uuid.UUID | None = None


# ── Offsite destinations (S3-compatible buckets) ─────────────────────────────

PROVIDERS = {"s3", "r2", "b2", "spaces", "wasabi", "minio"}


class DestinationCreate(BaseModel):
    """Create an offsite destination. ``secret_key`` is encrypted at rest and is NEVER
    returned by any endpoint."""

    name: str = Field(min_length=1, max_length=255)
    provider: str = "s3"
    bucket: str = Field(min_length=1, max_length=255)
    region: str | None = Field(default=None, max_length=64)
    endpoint_url: str | None = Field(default=None, max_length=500)
    prefix: str | None = Field(default=None, max_length=500)
    access_key_id: str = Field(min_length=1, max_length=255)
    secret_key: str = Field(min_length=1)


class DestinationUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    provider: str | None = None
    bucket: str | None = Field(default=None, max_length=255)
    region: str | None = Field(default=None, max_length=64)
    endpoint_url: str | None = Field(default=None, max_length=500)
    prefix: str | None = Field(default=None, max_length=500)
    access_key_id: str | None = Field(default=None, max_length=255)
    secret_key: str | None = None  # omit to keep the stored one


class DestinationOut(BaseModel):
    """Credential-free view — ``access_key_id`` is shown (it is not secret); the secret
    key never appears."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    provider: str
    bucket: str
    region: str | None = None
    endpoint_url: str | None = None
    prefix: str | None = None
    access_key_id: str
    last_status: str | None = None
    last_error: str | None = None
    last_checked: datetime | None = None
    created_at: datetime
