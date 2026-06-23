"""add access_info column to playbooks

Revision ID: 010
Revises: 009
Create Date: 2026-06-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("playbooks", sa.Column("access_info", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("playbooks", "access_info")
