"""create missions

Revision ID: 024
Revises: 023
Create Date: 2026-07-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "missions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("server_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("servers.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("server_name", sa.String(length=255), nullable=True),
        sa.Column("skill_slug", sa.String(length=100), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="running", nullable=False, index=True),
        sa.Column("verified", sa.Boolean(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("steps", sa.Text(), server_default="[]", nullable=False),
        sa.Column("steps_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("budget", sa.Integer(), server_default="20", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("missions")
