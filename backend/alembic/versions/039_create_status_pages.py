"""status_pages + status_page_items — public "is the site up?" pages

Revision ID: 039
Revises: 038
Create Date: 2026-07-25

Pro feature #4 (docs/PRO-FEATURES-PLAN.md). Served unauthenticated at /status/<slug>, so
the public payload is an explicit allowlist: display name + status + uptime only. Never
the monitored URL, the server, or internal error text.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "status_pages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("support_url", sa.String(length=500), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_status_pages_slug", "status_pages", ["slug"], unique=True)
    op.create_index("ix_status_pages_user_id", "status_pages", ["user_id"])

    op.create_table(
        "status_page_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("page_id", UUID(as_uuid=True), sa.ForeignKey("status_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("monitor_id", UUID(as_uuid=True), sa.ForeignKey("uptime_monitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("page_id", "monitor_id", name="uq_status_page_item"),
    )
    op.create_index("ix_status_page_items_page_id", "status_page_items", ["page_id"])


def downgrade() -> None:
    op.drop_index("ix_status_page_items_page_id", table_name="status_page_items")
    op.drop_table("status_page_items")
    op.drop_index("ix_status_pages_user_id", table_name="status_pages")
    op.drop_index("ix_status_pages_slug", table_name="status_pages")
    op.drop_table("status_pages")
