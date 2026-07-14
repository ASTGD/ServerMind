"""add missions.incident_report — the AI-generated plain-language incident narrative

Revision ID: 033
Revises: 032
Create Date: 2026-07-14

Stores the "Explain this incident" report (headline + how-they-got-in + timeline +
impact + done/left + caveat) as a JSON string, synthesized from the mission's durable
transcript. Nullable — generated on demand and cached. See ai_service.explain_incident.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("missions", sa.Column("incident_report", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("missions", "incident_report")
