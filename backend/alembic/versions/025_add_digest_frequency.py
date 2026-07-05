"""add users.digest_frequency

Revision ID: 025
Revises: 024
Create Date: 2026-07-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Proactive fleet-health email digest cadence: 'off' | 'weekly' | 'daily'.
    # Weekly by default so existing users start receiving it (opt-out in Settings).
    op.add_column(
        "users",
        sa.Column("digest_frequency", sa.String(length=10),
                  server_default="weekly", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "digest_frequency")
