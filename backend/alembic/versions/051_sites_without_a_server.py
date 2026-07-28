"""a site can exist without a server we manage

Revision ID: 051
Revises: 050

A customer's website is a real thing whether or not we can log into the machine it
runs on. Requiring a server meant the only sites we could track were ones we had
discovered ourselves — so a customer could not tell us about their own website.
"""
from alembic import op
import sqlalchemy as sa

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("sites", "server_id", existing_type=sa.dialects.postgresql.UUID(),
                    nullable=True)


def downgrade() -> None:
    # Rows added by hand have no server; they would violate the constraint, so they go.
    op.execute("DELETE FROM sites WHERE server_id IS NULL")
    op.alter_column("sites", "server_id", existing_type=sa.dialects.postgresql.UUID(),
                    nullable=False)
