"""create backups and backup_runs tables

Revision ID: 008
Revises: 007
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backups",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("backup_type", sa.String(20), nullable=False),
        sa.Column("source", sa.String(1024), nullable=False),
        sa.Column("dest_dir", sa.String(1024), server_default=sa.text("'/var/backups/servermind'")),
        sa.Column("db_user", sa.String(255)),
        sa.Column("encrypted_db_cred", sa.Text),
        sa.Column("retention", sa.Integer, server_default=sa.text("7")),
        sa.Column("cron_expression", sa.String(100)),
        sa.Column("human_schedule", sa.String(255)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("last_run", sa.DateTime(timezone=True)),
        sa.Column("last_status", sa.String(20)),
        sa.Column("next_run", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_backups_server_id", "backups", ["server_id"])

    op.create_table(
        "backup_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "backup_id",
            UUID(as_uuid=True),
            sa.ForeignKey("backups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("action", sa.String(20), server_default=sa.text("'backup'")),
        sa.Column("status", sa.String(20), server_default=sa.text("'running'")),
        sa.Column("artifact_path", sa.String(1024)),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("output", sa.Text),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_backup_runs_backup_id", "backup_runs", ["backup_id"])


def downgrade() -> None:
    op.drop_index("ix_backup_runs_backup_id", table_name="backup_runs")
    op.drop_table("backup_runs")
    op.drop_index("ix_backups_server_id", table_name="backups")
    op.drop_table("backups")
