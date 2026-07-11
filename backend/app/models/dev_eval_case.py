"""DevEvalCase — an eval case captured from the Dev Door (docs/EVAL-DRIVEN-DEV.md).

Captured while iterating (from the Prompt Inspector, or added by hand) so a bug becomes a
red test in one click — the flywheel's human gate. Run alongside the source-controlled
corpus by the eval runner, so a captured case shows red/green immediately. Admin-only; it
belongs to the instance (not a user) — it's a test, not user data. A case proven useful is
promoted into ``app/evals/corpus.py`` in a commit (the source-controlled home).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DevEvalCase(Base):
    __tablename__ = "dev_eval_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # One of app.evals.model.DETERMINISTIC_CATEGORIES.
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)          # message or command (secret-scrubbed)
    expected: Mapped[str] = mapped_column(String(120), nullable=False)  # skill slug / status / verdict
    os: Mapped[str] = mapped_column(String(20), default="linux", server_default="linux")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
