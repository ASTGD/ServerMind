"""dev_eval_cases — eval cases captured from the Dev Door

Revision ID: 031
Revises: 030
Create Date: 2026-07-12

An admin-captured eval case (Dev Door flywheel, docs/EVAL-DRIVEN-DEV.md), run alongside
the source-controlled corpus so a captured bug shows red/green at once.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dev_eval_cases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected", sa.String(length=120), nullable=False),
        sa.Column("os", sa.String(length=20), server_default="linux", nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("dev_eval_cases")
