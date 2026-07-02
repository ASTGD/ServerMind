"""add ai_usage.skill (Ally Skills Phase A — which skill served a request)

Revision ID: 021
Revises: 020
Create Date: 2026-07-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ai_usage", sa.Column("skill", sa.String(40)))


def downgrade() -> None:
    op.drop_column("ai_usage", "skill")
