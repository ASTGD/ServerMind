"""Remember whether a metric alert is currently over its threshold.

Without this, there is no way to send exactly one "back to normal" message: an alert that
fired once has `last_triggered` set forever, so any recovery check based on it would send a
recovery notice on every sweep for the rest of the rule's life.

Existing rules default to false — "not currently breaching". That is the safe direction: a
rule that IS breaching right now will be marked on its next check and behave normally from
then on. The opposite default would fire a spurious "recovered" message to every customer
with an alert rule the first time the worker ran after deploy.

Revision ID: 053
Revises: 052
"""
from alembic import op
import sqlalchemy as sa

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alerts",
        sa.Column("is_breaching", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("alerts", "is_breaching")
