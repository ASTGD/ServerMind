"""oauth_clients, oauth_authorization_codes, oauth_tokens — MCP OAuth 2.1 AS storage

Revision ID: 034
Revises: 033
Create Date: 2026-07-23

Backs the MCP server's OAuth flow (docs/MCP-SERVER-PLAN.md §5) so a customer's own AI
client connects once in a browser and then calls our tools with a bearer token. Codes
and tokens are stored as SHA-256 hashes; access + refresh share a grant_id (the revoke
unit).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(length=255), primary_key=True),
        sa.Column("client_name", sa.String(length=255), nullable=True),
        sa.Column("data", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "oauth_authorization_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_uri_provided_explicitly", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("code_challenge", sa.Text(), nullable=True),
        sa.Column("scopes", JSONB(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_oauth_authorization_codes_code_hash", "oauth_authorization_codes", ["code_hash"], unique=True)

    op.create_table(
        "oauth_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_type", sa.String(length=10), nullable=False),
        sa.Column("grant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=64), nullable=False),
        sa.Column("scopes", JSONB(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_oauth_tokens_token_hash", "oauth_tokens", ["token_hash"], unique=True)
    op.create_index("ix_oauth_tokens_grant_id", "oauth_tokens", ["grant_id"])
    op.create_index("ix_oauth_tokens_subject", "oauth_tokens", ["subject"])


def downgrade() -> None:
    op.drop_index("ix_oauth_tokens_subject", table_name="oauth_tokens")
    op.drop_index("ix_oauth_tokens_grant_id", table_name="oauth_tokens")
    op.drop_index("ix_oauth_tokens_token_hash", table_name="oauth_tokens")
    op.drop_table("oauth_tokens")
    op.drop_index("ix_oauth_authorization_codes_code_hash", table_name="oauth_authorization_codes")
    op.drop_table("oauth_authorization_codes")
    op.drop_table("oauth_clients")
