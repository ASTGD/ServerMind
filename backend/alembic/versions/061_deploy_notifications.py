"""Tell me when THIS site deploys — Ploi's per-site Notifications.

A subscription, not a second notification system: it joins a deploy target to a channel the
customer already made, and the sending is `channel_service.deliver`, which is the one
implementation of "talk to Slack".

Attached to the deploy TARGET rather than the site, because the target is the thing that
emits the events — a site with no target has nothing to be notified about, and a target that
belongs to no site (a server-level deploy) deserves this just as much.

Revision ID: 061
Revises: 060
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "061"
down_revision = "060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deploy_notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # The target owns this: delete the deploy setup and its notifications go with it,
        # because there is nothing left that could ever fire them.
        sa.Column("target_id", UUID(as_uuid=True),
                  sa.ForeignKey("deploy_targets.id", ondelete="CASCADE"), nullable=False),
        # SET NULL, never CASCADE. Deleting a channel must not silently delete the rule that
        # used it — the customer would lose the fact that they wanted to be told at all, and
        # find out by not being told. A rule with no channel is shown as needing one.
        sa.Column("channel_id", UUID(as_uuid=True),
                  sa.ForeignKey("notification_channels.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("events", JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_deploy_notifications_target", "deploy_notifications", ["target_id"])
    # One rule per channel per target. Two rules to the same place means two messages for
    # one deploy, which reads as a bug in us.
    op.create_unique_constraint("uq_deploy_notification_target_channel",
                                "deploy_notifications", ["target_id", "channel_id"])


def downgrade() -> None:
    op.drop_constraint("uq_deploy_notification_target_channel", "deploy_notifications")
    op.drop_index("ix_deploy_notifications_target", "deploy_notifications")
    op.drop_table("deploy_notifications")
