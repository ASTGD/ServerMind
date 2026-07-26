"""API keys + webhooks — the customer-facing integration surface

Revision ID: 044
Revises: 043
Create Date: 2026-07-26

Pro #8 (docs/PRO-FEATURES-PLAN.md). Notes on two columns:

- ``api_keys.key_hash`` is UNIQUE, which is both a lookup index and a correctness guarantee:
  two keys can never collide, so authenticating by hash always resolves to one owner.
- ``webhook_deliveries`` carries its own pending index on (status, next_attempt_at) because
  the retry worker asks exactly that question every minute.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("scopes", ARRAY(sa.String(length=20)), nullable=False, server_default="{}"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_api_keys_user", "api_keys", ["user_id"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"])
    op.create_index("ix_api_keys_hash", "api_keys", ["key_hash"], unique=True)

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("events", ARRAY(sa.String(length=40)), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disabled_reason", sa.String(length=255), nullable=True),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_endpoints_user", "webhook_endpoints", ["user_id"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("endpoint_id", UUID(as_uuid=True),
                  sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("payload", JSONB(), server_default="{}"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_deliveries_endpoint", "webhook_deliveries", ["endpoint_id"])
    op.create_index("ix_webhook_deliveries_created", "webhook_deliveries", ["created_at"])
    op.create_index("ix_webhook_deliveries_pending", "webhook_deliveries",
                    ["status", "next_attempt_at"])


def downgrade() -> None:
    for idx in ("ix_webhook_deliveries_pending", "ix_webhook_deliveries_created",
                "ix_webhook_deliveries_endpoint"):
        op.drop_index(idx, table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")
    op.drop_index("ix_webhook_endpoints_user", table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
    for idx in ("ix_api_keys_hash", "ix_api_keys_prefix", "ix_api_keys_user"):
        op.drop_index(idx, table_name="api_keys")
    op.drop_table("api_keys")
