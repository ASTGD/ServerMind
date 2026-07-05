"""add servers.category (Assets, Phase A)

Revision ID: 026
Revises: 025
Create Date: 2026-07-05

The user-facing "Assets" model groups a `servers` row by what it IS
(bare_metal | vps | hosting | windows | cloud) rather than by its transport. Purely
descriptive — no execution-path change; the DB name stays `servers` (see
docs/ASSETS-CATEGORIES-PLAN.md, "How the rename goes"). Existing rows are backfilled from
their transport so nothing is left uncategorised (bare_metal can't be inferred → default
plain SSH to 'vps'; the user can re-file in Edit).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("category", sa.String(length=20), nullable=True))
    op.execute(
        """
        UPDATE servers SET category = CASE
            WHEN connection_type = 'winrm' THEN 'windows'
            WHEN connection_type = 'hosting' THEN 'hosting'
            WHEN connection_type = 'ssh' AND panel_type IS NOT NULL THEN 'hosting'
            ELSE 'vps'
        END
        WHERE category IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("servers", "category")
