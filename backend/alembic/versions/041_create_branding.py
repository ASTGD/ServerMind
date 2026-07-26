"""branding — white-label for client-facing output

Revision ID: 041
Revises: 040
Create Date: 2026-07-26

Pro #3 (docs/PRO-FEATURES-PLAN.md). One row per user; applies to public status pages and
client reports — the things a customer of our customer sees.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "branding",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_name", sa.String(length=120), nullable=True),
        sa.Column("logo_url", sa.String(length=500), nullable=True),
        sa.Column("primary_color", sa.String(length=9), nullable=True),
        sa.Column("support_url", sa.String(length=500), nullable=True),
        sa.Column("support_email", sa.String(length=255), nullable=True),
        sa.Column("footer_text", sa.Text(), nullable=True),
        sa.Column("hide_serverally_branding", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_branding_user_id", "branding", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_branding_user_id", table_name="branding")
    op.drop_table("branding")
