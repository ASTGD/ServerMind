"""add missions.result — the owner-facing structured outcome card

Revision ID: 032
Revises: 031
Create Date: 2026-07-13

Stores the plain-language mission outcome the workspace renders as a clear result card
(headline + Found / Did / Left-for-you), as a JSON string. Nullable — a mission with no
structured result falls back to the free-text summary. See docs/ALLY-MISSIONS.md.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("missions", sa.Column("result", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("missions", "result")
