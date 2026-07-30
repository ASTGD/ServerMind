"""A site becomes something you create, not only something we find.

Until now `sites` was purely a discovery table: a scan wrote rows, and nothing else did.
That is why creating a website felt bolted on — the installer wrote a vhost and the site
appeared minutes later when the next scan ran, with no record in between of what was asked
for, whether it worked, or why it did not.

Existing rows default to `live`, which is correct rather than convenient: every row that
exists today got here by being observed on a server, and that is exactly what live means.

Revision ID: 055
Revises: 054
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("status", sa.String(20), nullable=False,
                                     server_default="live"))
    op.add_column("sites", sa.Column("install_error", sa.String(500)))
    op.add_column("sites", sa.Column("requested_type", sa.String(30)))
    # SET NULL, not CASCADE: history is pruned by the retention job, and losing an old run
    # must never delete the customer's SITE.
    op.add_column(
        "sites",
        sa.Column("install_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("playbook_runs.id", ondelete="SET NULL"), nullable=True),
    )
    # The Sites page filters by status constantly, and an agency has thousands of rows.
    op.create_index("ix_sites_user_status", "sites", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_sites_user_status", table_name="sites")
    op.drop_column("sites", "install_run_id")
    op.drop_column("sites", "requested_type")
    op.drop_column("sites", "install_error")
    op.drop_column("sites", "status")
