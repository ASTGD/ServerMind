"""client_report_subscriptions — monthly delivery of the client report

Revision ID: 042
Revises: 041
Create Date: 2026-07-26

Completes Pro #3 (docs/PRO-FEATURES-PLAN.md): the report existed on demand; this delivers
it. Recipient belongs to a SERVER, because an agency's server is usually one client's site.
send_day is capped at 28 so every month actually has that day.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_report_subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", UUID(as_uuid=True), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("send_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("period_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_sent", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_client_report_subs_user", "client_report_subscriptions", ["user_id"])
    op.create_index("ix_client_report_subs_server", "client_report_subscriptions", ["server_id"])


def downgrade() -> None:
    op.drop_index("ix_client_report_subs_server", table_name="client_report_subscriptions")
    op.drop_index("ix_client_report_subs_user", table_name="client_report_subscriptions")
    op.drop_table("client_report_subscriptions")
