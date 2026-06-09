"""create scheduled_tasks table

Revision ID: 005
Revises: 004
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
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
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("task_type", sa.String(20)),
        sa.Column("payload", JSONB),
        sa.Column("cron_expression", sa.String(100), nullable=False),
        sa.Column("human_schedule", sa.String(255)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("last_run", sa.DateTime(timezone=True)),
        sa.Column("last_status", sa.String(20)),
        sa.Column("next_run", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_scheduled_tasks_server_id", "scheduled_tasks", ["server_id"])
    op.create_index("ix_scheduled_tasks_user_id", "scheduled_tasks", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_tasks_user_id", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_server_id", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
