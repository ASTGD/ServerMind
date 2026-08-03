"""When a server's identity was last replaced.

Trusting a new host key is the customer telling us, explicitly, that this is a different
machine. Everything we had recorded about the previous one — the websites we found, the
fact that we set it up — describes hardware that no longer exists, and until now all of it
survived: a rebuilt server kept listing three sites that were gone, and kept claiming
ServerAlly was its control panel, so it never offered the setup choice again.

Recorded rather than inferred because the alternative is asking the machine on every page
load, and this is a fact that changes about once in a server's life.

Revision ID: 058
Revises: 057
"""
from alembic import op
import sqlalchemy as sa

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("servers", sa.Column("identity_changed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("servers", "identity_changed_at")
