"""Named, reusable notification channels.

Replaces the per-rule destination, where an agency ended up with the same Slack URL copied
into dozens of alert rules and no way to change it in one place.

Additive only: `alerts.channel` / `alerts.channel_target` are left exactly as they are, so
every existing rule keeps working untouched. A rule may point at a channel instead, and the
sender prefers the channel when one is set. Removing the old columns would be a second,
separate decision once nothing relies on them.

Revision ID: 054
Revises: 053
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("encrypted_config", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(300)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "label", name="uq_notification_channel_label"),
    )

    # An alert may now name a channel instead of carrying its own destination.
    # ondelete=SET NULL, not CASCADE: deleting a channel must never silently delete the
    # customer's alert RULES. The rule survives and falls back to its inline destination.
    op.add_column(
        "alerts",
        sa.Column("channel_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("notification_channels.id", ondelete="SET NULL"),
                  nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alerts", "channel_id")
    op.drop_table("notification_channels")
