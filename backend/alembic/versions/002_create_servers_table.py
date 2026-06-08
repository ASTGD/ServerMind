"""create servers table

Revision ID: 002
Revises: 001
Create Date: 2026-06-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "servers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="22"),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("auth_type", sa.String(20), nullable=False),
        sa.Column("connection_type", sa.String(20), nullable=False),
        sa.Column("panel_type", sa.String(20), nullable=True),
        sa.Column("encrypted_cred", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=True),
        sa.Column("os_type", sa.String(50), nullable=True),
        sa.Column("os_version", sa.String(50), nullable=True),
        sa.Column("arch", sa.String(20), nullable=True),
        sa.Column("shell", sa.String(20), nullable=False, server_default="bash"),
        sa.Column("status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("tags", ARRAY(sa.String()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_servers_user_id", "servers", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_servers_user_id", table_name="servers")
    op.drop_table("servers")
