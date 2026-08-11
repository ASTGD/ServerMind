"""ThreatScan model — stores the result of a server threat (IOC) scan."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ThreatScan(Base):
    """One threat scan against a server (indicators of compromise).

    Distinct from SecurityScan (hardening posture): this records whether a server
    shows signs of ACTIVE compromise. ``findings`` is the JSON-serialised list;
    per-severity counts and the verdict are denormalised for cheap history listing
    and for the proactive worker to compare scans without parsing every blob.
    """

    __tablename__ = "threat_scans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # clean | suspicious | at_risk | compromised | unknown
    verdict: Mapped[str] = mapped_column(String(20), default="unknown")
    status: Mapped[str] = mapped_column(String(20), default="completed")  # completed | failed
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    critical_count: Mapped[int] = mapped_column(Integer, default=0)
    high_count: Mapped[int] = mapped_column(Integer, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, default=0)
    low_count: Mapped[int] = mapped_column(Integer, default=0)
    info_count: Mapped[int] = mapped_column(Integer, default=0)
    pass_count: Mapped[int] = mapped_column(Integer, default=0)

    findings: Mapped[str] = mapped_column(Text, default="[]")  # JSON

    #: What the scan could actually read — root | sudo | none. NULL on rows written before
    #: this existed, and deliberately not back-filled: claiming an old scan had full access
    #: would be the same comfortable guess the verdict rule exists to prevent.
    privilege: Mapped[str | None] = mapped_column(String(10))
    #: Checks that did not run, and why. JSON. An empty list means nothing was skipped.
    skipped: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
