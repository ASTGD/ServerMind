"""Blueprint runs — ready-made long jobs, checkpointed step by step.

A blueprint is a FIXED list of steps ServerAlly already knows how to do (no model call
anywhere in the run). This table is the durable record the live screen reads; every step
writes its state here as it happens, so a restart or a page reload loses nothing.

Revision ID: 064
Revises: 063
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blueprint_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("server_id", UUID(as_uuid=True),
                  sa.ForeignKey("servers.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("blueprint_key", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("inputs", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("current", sa.Integer, nullable=False, server_default="0"),
        sa.Column("steps", JSONB, nullable=False, server_default="[]"),
        sa.Column("message", sa.Text),
        sa.Column("found", JSONB, nullable=False, server_default="[]"),
        sa.Column("left_for_you", JSONB, nullable=False, server_default="[]"),
        sa.Column("source", sa.String(16), nullable=False, server_default="app"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("blueprint_runs")
