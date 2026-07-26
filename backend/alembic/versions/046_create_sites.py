"""sites — the websites discovered on each server

Revision ID: 046
Revises: 045
Create Date: 2026-07-26

The Sites section (docs/POSITIONING-CATEGORY.md §8). ``uq_site_server_domain`` is per SERVER,
not global: the same domain legitimately appears on two servers during a migration or when a
staging copy exists, and a global constraint would make that impossible to represent.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", UUID(as_uuid=True), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("aliases", ARRAY(sa.String(length=253)), nullable=False, server_default="{}"),
        sa.Column("doc_root", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("app_type", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("app_version", sa.String(length=40), nullable=True),
        sa.Column("has_ssl", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_present", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("server_id", "domain", name="uq_site_server_domain"),
    )
    op.create_index("ix_sites_user", "sites", ["user_id"])
    op.create_index("ix_sites_server", "sites", ["server_id"])
    op.create_index("ix_sites_domain", "sites", ["domain"])
    op.create_index("ix_sites_user_domain", "sites", ["user_id", "domain"])


def downgrade() -> None:
    for idx in ("ix_sites_user_domain", "ix_sites_domain", "ix_sites_server", "ix_sites_user"):
        op.drop_index(idx, table_name="sites")
    op.drop_table("sites")
