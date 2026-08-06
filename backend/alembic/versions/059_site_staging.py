"""Staging sites: a site can be a copy of another one.

Three columns, no new table — and that is the design, not a shortcut. A staging site is an
ORDINARY site row, so every screen already built (Files, Logs, Cron, Database, PHP, Daemons,
Deployments) works on it the day it exists.

``parent_site_id`` is ``ON DELETE SET NULL`` on purpose. Deleting the live site must leave
the staging copy standing: it is a real website with real files on a real server, and
cascading would delete somebody's work as a side effect of tidying up. It simply stops being
staging.

Revision ID: 059
Revises: 058
"""
from alembic import op
import sqlalchemy as sa

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("parent_site_id", sa.dialects.postgresql.UUID(as_uuid=True),
                                     nullable=True))
    op.create_foreign_key("fk_sites_parent_site", "sites", "sites",
                          ["parent_site_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_sites_parent_site_id", "sites", ["parent_site_id"])
    op.add_column("sites", sa.Column("environment", sa.String(20), nullable=False,
                                     server_default="production"))
    op.add_column("sites", sa.Column("no_index", sa.Boolean(), nullable=False,
                                     server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("sites", "no_index")
    op.drop_column("sites", "environment")
    op.drop_index("ix_sites_parent_site_id", table_name="sites")
    op.drop_constraint("fk_sites_parent_site", "sites", type_="foreignkey")
    op.drop_column("sites", "parent_site_id")
