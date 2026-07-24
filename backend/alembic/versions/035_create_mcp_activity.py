"""mcp_activity — durable feed of actions a connected AI takes over MCP

Revision ID: 035
Revises: 034
Create Date: 2026-07-24

Powers the user-facing "MCP Activity" feed (Settings → Connected applications). Each
action is written at START (status='running') and updated at FINISH, so the feed shows a
live running→done transition. Only actions (run_command + writes) are recorded. Never
stores a credential (the command text is secret-redacted before insert).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_activity",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=True),
        sa.Column("client_name", sa.String(length=255), nullable=True),
        sa.Column("tool", sa.String(length=64), nullable=False),
        sa.Column("server_id", UUID(as_uuid=True), nullable=True),
        sa.Column("server_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="running"),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("command", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mcp_activity_user_started", "mcp_activity", ["user_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_mcp_activity_user_started", table_name="mcp_activity")
    op.drop_table("mcp_activity")
