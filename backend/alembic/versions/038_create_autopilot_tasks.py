"""autopilot_tasks — Ally works on a schedule, within limits you set

Revision ID: 038
Revises: 037
Create Date: 2026-07-25

The Pro flagship (docs/PRO-FEATURES-PLAN.md §4 #1+#2): a standing instruction (goal +
schedule) plus a POLICY saying how far Ally may go alone. The policy is consulted at the
same point a human would approve a step; the absolute blocklist runs before it and is
unaffected, so no policy can authorise a catastrophic command.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "autopilot_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", UUID(as_uuid=True), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("policy", sa.String(length=20), nullable=False, server_default="report_only"),
        sa.Column("cron_expression", sa.String(length=100), nullable=False),
        sa.Column("human_schedule", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("channel", sa.String(length=20), nullable=True),
        sa.Column("channel_target", sa.String(length=500), nullable=True),
        sa.Column("notify_on_change_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("last_mission_id", UUID(as_uuid=True), nullable=True),
        sa.Column("next_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_autopilot_tasks_user_id", "autopilot_tasks", ["user_id"])
    op.create_index("ix_autopilot_tasks_server_id", "autopilot_tasks", ["server_id"])


def downgrade() -> None:
    op.drop_index("ix_autopilot_tasks_server_id", table_name="autopilot_tasks")
    op.drop_index("ix_autopilot_tasks_user_id", table_name="autopilot_tasks")
    op.drop_table("autopilot_tasks")
