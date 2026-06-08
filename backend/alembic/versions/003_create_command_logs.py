"""create command_logs table

Revision ID: 003
Revises: 002
Create Date: 2026-06-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "command_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("server_id", UUID(as_uuid=True), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("user_language", sa.String(10), nullable=True),
        sa.Column("ai_plan", JSONB, nullable=True),
        sa.Column("commands", JSONB, nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(10), nullable=True),
        sa.Column("execution_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_command_logs_server_id", "command_logs", ["server_id"])
    op.create_index("ix_command_logs_user_id", "command_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_command_logs_user_id", table_name="command_logs")
    op.drop_index("ix_command_logs_server_id", table_name="command_logs")
    op.drop_table("command_logs")
