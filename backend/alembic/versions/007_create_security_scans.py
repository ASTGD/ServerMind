"""create security_scans table

Revision ID: 007
Revises: 006
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "security_scans",
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
        sa.Column("score", sa.Integer, server_default=sa.text("0")),
        sa.Column("grade", sa.String(2), server_default=sa.text("'F'")),
        sa.Column("status", sa.String(20), server_default=sa.text("'completed'")),
        sa.Column("error", sa.Text),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("critical_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("high_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("medium_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("low_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("pass_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("info_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("findings", sa.Text, server_default=sa.text("'[]'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_security_scans_server_id", "security_scans", ["server_id"])
    op.create_index("ix_security_scans_created_at", "security_scans", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_security_scans_created_at", table_name="security_scans")
    op.drop_index("ix_security_scans_server_id", table_name="security_scans")
    op.drop_table("security_scans")
