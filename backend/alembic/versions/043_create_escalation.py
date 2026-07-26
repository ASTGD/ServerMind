"""On-call escalation — policies, steps, incidents, provider credentials

Revision ID: 043
Revises: 042
Create Date: 2026-07-26

Pro #5 (docs/PRO-FEATURES-PLAN.md). The one index that carries real meaning is
``uq_incident_open_dedup``: a PARTIAL unique index on (user_id, dedup_key) limited to open
incidents. It is what makes "one problem = one incident" a database guarantee rather than
a convention the callers have to remember — a flapping monitor cannot create a second open
incident even if two workers race, while the same key is free to reappear once resolved.

``servers.escalation_policy_id`` is nullable with ON DELETE SET NULL: deleting a policy
must never delete a server.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "escalation_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("min_severity", sa.String(length=20), nullable=False, server_default="high"),
        sa.Column("repeat_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("max_repeats", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_escalation_policies_user", "escalation_policies", ["user_id"])

    op.create_table(
        "escalation_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_id", UUID(as_uuid=True), sa.ForeignKey("escalation_policies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("after_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("target", sa.String(length=500), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
    )
    op.create_index("ix_escalation_steps_policy", "escalation_steps", ["policy_id"])

    op.create_table(
        "incidents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", UUID(as_uuid=True), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("dedup_key", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), server_default=""),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="high"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("policy_id", UUID(as_uuid=True), sa.ForeignKey("escalation_policies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repeats_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notifications_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ack_token_hash", sa.String(length=64), nullable=True),
        sa.Column("ack_token_enc", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_incidents_user_status", "incidents", ["user_id", "status"])
    op.create_index("ix_incidents_server", "incidents", ["server_id"])
    op.create_index("ix_incidents_next_action", "incidents", ["next_action_at"])
    op.create_index("ix_incidents_ack_token", "incidents", ["ack_token_hash"])
    # The guarantee: one OPEN incident per problem, enforced by the database.
    op.create_index(
        "uq_incident_open_dedup", "incidents", ["user_id", "dedup_key"],
        unique=True, postgresql_where=sa.text("status = 'open'"),
    )

    op.create_table(
        "notification_providers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("encrypted_config", sa.Text(), nullable=False),
        sa.Column("monthly_limit", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("sent_this_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "provider", name="uq_notification_provider_user"),
    )
    op.create_index("ix_notification_providers_user", "notification_providers", ["user_id"])

    # Per-server override; falls back to the user's default policy.
    op.add_column(
        "servers",
        sa.Column("escalation_policy_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_servers_escalation_policy", "servers", "escalation_policies",
        ["escalation_policy_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_servers_escalation_policy", "servers", type_="foreignkey")
    op.drop_column("servers", "escalation_policy_id")
    op.drop_index("ix_notification_providers_user", table_name="notification_providers")
    op.drop_table("notification_providers")
    for idx in ("uq_incident_open_dedup", "ix_incidents_ack_token", "ix_incidents_next_action",
                "ix_incidents_server", "ix_incidents_user_status"):
        op.drop_index(idx, table_name="incidents")
    op.drop_table("incidents")
    op.drop_index("ix_escalation_steps_policy", table_name="escalation_steps")
    op.drop_table("escalation_steps")
    op.drop_index("ix_escalation_policies_user", table_name="escalation_policies")
    op.drop_table("escalation_policies")
