"""add users.ally_mode — Ally autonomy mode (proactivity Track D)

Revision ID: 029
Revises: 028
Create Date: 2026-07-08

How much Ally decides on its own: 'proactive' | 'normal' | 'careful'. Changes how
Ally ASKS and how much it assumes/auto-approves — it NEVER relaxes the hard safety
rails (the command blocklist, the read-only verification gate, injection defences, and
confirmation for truly destructive steps hold in every mode). Default 'normal'.
See docs/ALLY-PROACTIVITY-PLAN.md Track D.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("ally_mode", sa.String(length=10), server_default="normal", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "ally_mode")
