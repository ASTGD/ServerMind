"""create ai_usage ledger + users.plan (AI metering Brick 1 — docs/AI-METERING.md)

Revision ID: 019
Revises: 018
Create Date: 2026-07-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", UUID(as_uuid=True), sa.ForeignKey("servers.id", ondelete="SET NULL")),
        sa.Column("feature", sa.String(30), nullable=False),
        sa.Column("model", sa.String(60), nullable=False, server_default=""),
        sa.Column("fuel", sa.String(10), nullable=False, server_default="included"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("actions", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(15), nullable=False, server_default="ok"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    # The monthly counter query: SUM(actions) WHERE user_id=? AND created_at >= period.
    op.create_index("ix_ai_usage_user_created", "ai_usage", ["user_id", "created_at"])

    op.add_column(
        "users",
        sa.Column("plan", sa.String(10), nullable=False, server_default="free"),
    )


def downgrade() -> None:
    op.drop_column("users", "plan")
    op.drop_index("ix_ai_usage_user_created", table_name="ai_usage")
    op.drop_table("ai_usage")
