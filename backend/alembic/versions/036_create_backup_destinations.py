"""backup_destinations + offsite columns on backups/backup_runs

Revision ID: 036
Revises: 035
Create Date: 2026-07-25

Offsite backups (docs/MARKET-RESEARCH-2026-07.md §8.2, Wave 1). A destination is a
reusable S3-compatible bucket config; a backup job may point at one, and each run records
where the offsite copy landed. The bucket secret is AES-256-GCM encrypted at rest and is
never sent to the managed server — uploads use a short-lived presigned URL.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backup_destinations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False, server_default="s3"),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("endpoint_url", sa.String(length=500), nullable=True),
        sa.Column("prefix", sa.String(length=500), nullable=True),
        sa.Column("access_key_id", sa.String(length=255), nullable=False),
        sa.Column("encrypted_secret_key", sa.Text(), nullable=False),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_backup_destinations_user_id", "backup_destinations", ["user_id"])

    op.add_column("backups", sa.Column("destination_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_backups_destination_id", "backups", "backup_destinations",
        ["destination_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_backups_destination_id", "backups", ["destination_id"])
    op.add_column("backups", sa.Column("keep_local", sa.Boolean(), nullable=False, server_default=sa.true()))

    op.add_column("backup_runs", sa.Column("remote_key", sa.String(length=1024), nullable=True))
    op.add_column("backup_runs", sa.Column("offsite_status", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("backup_runs", "offsite_status")
    op.drop_column("backup_runs", "remote_key")
    op.drop_column("backups", "keep_local")
    op.drop_index("ix_backups_destination_id", table_name="backups")
    op.drop_constraint("fk_backups_destination_id", "backups", type_="foreignkey")
    op.drop_column("backups", "destination_id")
    op.drop_index("ix_backup_destinations_user_id", table_name="backup_destinations")
    op.drop_table("backup_destinations")
