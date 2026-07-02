"""create ally_memories (Ally's long-term learned memory — Ally Brain Phase 5)

Revision ID: 020
Revises: 019
Create Date: 2026-07-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ally_memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", UUID(as_uuid=True), sa.ForeignKey("servers.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(12), nullable=False, server_default="fact"),
        sa.Column("content", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_ally_memories_user", "ally_memories", ["user_id"])
    op.create_index("ix_ally_memories_server", "ally_memories", ["server_id"])


def downgrade() -> None:
    op.drop_index("ix_ally_memories_server", table_name="ally_memories")
    op.drop_index("ix_ally_memories_user", table_name="ally_memories")
    op.drop_table("ally_memories")
