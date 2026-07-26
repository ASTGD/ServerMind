"""Custom runbooks — an account's own expert procedures

Revision ID: 045
Revises: 044
Create Date: 2026-07-26

Pro #7 (docs/PRO-FEATURES-PLAN.md). ``uq_runbook_user_slug`` is per-account rather than
global, because two customers naturally name their procedures the same thing — and the slug
only ever has to be unique within the library it is matched against.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runbooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("triggers", ARRAY(sa.String(length=120)), nullable=False, server_default="{}"),
        sa.Column("os_family", sa.String(length=20), nullable=False, server_default="any"),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="guide"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("budget", sa.Integer(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "slug", name="uq_runbook_user_slug"),
    )
    op.create_index("ix_runbooks_user", "runbooks", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_runbooks_user", table_name="runbooks")
    op.drop_table("runbooks")
