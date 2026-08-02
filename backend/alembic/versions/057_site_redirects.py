"""Redirects belonging to a website.

The web-server config is what is LIVE; this table is what the owner asked for, and
`is_applied` is the difference between the two — so a redirect that was recorded but never
reached the server is never shown as if it were working.

Revision ID: 057
Revises: 056
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_redirects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # CASCADE: a redirect has no meaning without its site, and the site's own removal
        # takes the vhost with it, so there is nothing left for the row to describe.
        sa.Column("site_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("redirect_from", sa.String(500), nullable=False),
        sa.Column("redirect_to", sa.String(500), nullable=False),
        sa.Column("redirect_type", sa.String(20), nullable=False,
                  server_default="redirect"),
        sa.Column("is_applied", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("site_id", "redirect_from", name="uq_site_redirect_from"),
    )


def downgrade() -> None:
    op.drop_table("site_redirects")
