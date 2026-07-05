"""servers.rdp_enabled — the per-Windows-asset Remote Desktop opt-in (Assets Phase E)

Revision ID: 028
Revises: 027
Create Date: 2026-07-06

RDP is a capability toggle on a Windows asset, not a category. It sits OUTSIDE the
AI-safety envelope (a human drives the mouse), so it is opt-in per asset and every
"open desktop" is access-checked against team_members/server_access. Default off.
See docs/ASSETS-CATEGORIES-PLAN.md §RDP.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("rdp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("servers", "rdp_enabled")
