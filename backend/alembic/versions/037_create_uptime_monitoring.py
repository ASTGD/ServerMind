"""uptime_monitors + uptime_checks — is the site reachable from outside?

Revision ID: 037
Revises: 036
Create Date: 2026-07-25

Wave 1 #3 (docs/MARKET-RESEARCH-2026-07.md §8.2). Until now alerts could only fire on
CPU/RAM/disk — never on the one thing an owner actually cares about, "my site is down".
Checks run from ServerAlly (not the server), and may assert page CONTENT, not just a
status code.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uptime_monitors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", UUID(as_uuid=True), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False, server_default="GET"),
        sa.Column("expected_status", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("expected_keyword", sa.String(length=255), nullable=True),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("failure_threshold", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("current_status", sa.String(length=10), nullable=False, server_default="unknown"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_change", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_response_ms", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=True),
        sa.Column("channel_target", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_uptime_monitors_user_id", "uptime_monitors", ["user_id"])
    op.create_index("ix_uptime_monitors_server_id", "uptime_monitors", ["server_id"])
    # The worker's hot query: active monitors ordered by when they were last checked.
    op.create_index("ix_uptime_monitors_due", "uptime_monitors", ["is_active", "last_checked"])

    op.create_table(
        "uptime_checks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("monitor_id", UUID(as_uuid=True), sa.ForeignKey("uptime_monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_uptime_checks_monitor_time", "uptime_checks", ["monitor_id", "checked_at"])


def downgrade() -> None:
    op.drop_index("ix_uptime_checks_monitor_time", table_name="uptime_checks")
    op.drop_table("uptime_checks")
    op.drop_index("ix_uptime_monitors_due", table_name="uptime_monitors")
    op.drop_index("ix_uptime_monitors_server_id", table_name="uptime_monitors")
    op.drop_index("ix_uptime_monitors_user_id", table_name="uptime_monitors")
    op.drop_table("uptime_monitors")
