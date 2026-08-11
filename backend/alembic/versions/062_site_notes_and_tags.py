"""Site notes and tags — Ploi's "Site notes" and "Project grouping".

Two things an agency running fifty sites needs and cannot get from the server: a note about
THIS site ("client pays annually, renewal March", "do not touch the theme, they edit it
live") and a way to group sites that belong together.

Both are plain text the customer owns. Neither is derived from anything, so neither can be
recovered by a scan — which is exactly why they need a home in our database rather than a
file on the server that a redeploy would take away.

Revision ID: 062
Revises: 061
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("sites", sa.Column(
        "tags", postgresql.ARRAY(sa.String(40)), nullable=False,
        server_default=sa.text("'{}'::varchar[]")))
    # Grouping is the point of tags, so the lookup that groups has to be cheap.
    op.create_index("ix_sites_tags", "sites", ["tags"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_sites_tags", table_name="sites")
    op.drop_column("sites", "tags")
    op.drop_column("sites", "notes")
