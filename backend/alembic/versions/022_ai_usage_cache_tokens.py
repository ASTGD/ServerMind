"""add ai_usage cache token columns (prompt-caching telemetry — Ally Context C3)

Revision ID: 022
Revises: 021
Create Date: 2026-07-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_usage", sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ai_usage", sa.Column("cache_write_tokens", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("ai_usage", "cache_write_tokens")
    op.drop_column("ai_usage", "cache_read_tokens")
