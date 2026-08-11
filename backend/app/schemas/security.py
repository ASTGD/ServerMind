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


# ── Threat scan (indicators of compromise) ────────────────────────────────────

class ThreatFinding(BaseModel):
    """One threat-scan finding (an indicator of compromise, or a passing check)."""

    id: str
    title: str
    severity: str          # critical | high | medium | low | info | pass
    detail: str | None = None
    recommendation: str | None = None
    evidence: str | None = None


class SkippedCheck(BaseModel):
    """A check that did not run. Named, so "unknown" is never a mystery."""

    id: str
    title: str
    reason: str


class ThreatScanOut(BaseModel):
    """Full threat scan result returned to the client."""

    id: uuid.UUID
    server_id: uuid.UUID
    verdict: str           # clean | suspicious | at_risk | compromised | unknown
    status: str
    error: str | None = None
    duration_ms: int | None = None
    counts: ScanCounts
    findings: list[ThreatFinding]
    #: What the scan could read — root | sudo | none. None on scans from before this existed.
    privilege: str | None = None
    #: Checks that did not run, and why. Empty means nothing was skipped.
    skipped: list[SkippedCheck] = []
    #: One sentence for the customer, derived from `privilege` so the wording lives in one
    #: place. None when there is nothing to say.
    note: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
