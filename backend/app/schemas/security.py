"""Pydantic schemas for the Security Audit feature."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """A single security audit finding."""

    id: str
    title: str
    category: str          # ssh | firewall | updates | accounts | filesystem | services | hardening | kernel
    severity: str          # critical | high | medium | low | pass | info | unknown
    status: str            # pass | fail | warn | info | unknown
    description: str
    detail: str | None = None          # observed value / evidence
    recommendation: str | None = None  # what the user should do
    fix_command: str | None = None     # suggested command (NEVER auto-executed)


class ScanCounts(BaseModel):
    """Per-severity tally for a scan."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    passed: int = Field(default=0, serialization_alias="pass", validation_alias="pass")
    info: int = 0

    model_config = {"populate_by_name": True}


class SecurityScanOut(BaseModel):
    """Full security scan result returned to the client."""

    id: uuid.UUID
    server_id: uuid.UUID
    score: int
    grade: str
    status: str
    error: str | None = None
    duration_ms: int | None = None
    counts: ScanCounts
    findings: list[Finding]
    created_at: datetime

    model_config = {"from_attributes": True}
