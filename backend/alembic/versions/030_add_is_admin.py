"""add users.is_admin — gates the admin-only Dev Door

Revision ID: 030
Revises: 029
Create Date: 2026-07-12

Internal staff flag for the eval-driven Dev Door (Prompt Inspector / eval runner).
NEVER granted via signup or billing — set by hand on a trusted account. Guards every
/api/dev endpoint. Default false. See docs/EVAL-DRIVEN-DEV.md.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
