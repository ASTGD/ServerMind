"""cloud_accounts + servers cloud link (Assets Phase C)

Revision ID: 027
Revises: 026
Create Date: 2026-07-06

A Cloud Account connects a whole provider account (AWS first) by API key so its
instances can be discovered and imported as normal `servers` rows. The credential is
AES-256-GCM encrypted (a provider-shaped JSON blob), same pattern as servers.encrypted_cred.
Imported instances link back via `cloud_account_id`; `cloud_instance_id` dedupes re-imports.
See docs/ASSETS-CATEGORIES-PLAN.md Phase C.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cloud_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),  # aws|digitalocean|hetzner|gcp|azure
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("encrypted_credential", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cloud_accounts_user_id", "cloud_accounts", ["user_id"])
    # Imported instances link back to their account + carry the provider instance id (dedupe).
    op.add_column("servers", sa.Column("cloud_account_id", UUID(as_uuid=True),
                                       sa.ForeignKey("cloud_accounts.id", ondelete="SET NULL"), nullable=True))
    op.add_column("servers", sa.Column("cloud_instance_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("servers", "cloud_instance_id")
    op.drop_column("servers", "cloud_account_id")
    op.drop_index("ix_cloud_accounts_user_id", table_name="cloud_accounts")
    op.drop_table("cloud_accounts")
