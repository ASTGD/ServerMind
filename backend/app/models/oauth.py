"""OAuth 2.1 authorization-server storage for the MCP server (docs/MCP-SERVER-PLAN.md §5).

Three tables back the MCP OAuth flow so a customer's own AI client (Claude, ChatGPT,
Cursor) can connect once in a browser and then call our tools with a bearer token:

- ``oauth_clients``              — clients registered via Dynamic Client Registration.
- ``oauth_authorization_codes``  — short-lived, single-use PKCE codes.
- ``oauth_tokens``               — issued access/refresh tokens, opaque + stored hashed.

Nothing here holds a *user* or *server* credential; these are OAuth artifacts. Tokens
and codes are stored as SHA-256 hashes (never the raw value), so a DB read cannot replay
them. Access + refresh issued together share a ``grant_id`` — the "connection" unit shown
in Settings and revoked as a whole; refresh rotation keeps ``grant_id`` stable.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OAuthClient(Base):
    """An OAuth client registered via Dynamic Client Registration (RFC 7591).

    Created when a customer's AI first connects. We keep the full client metadata
    (``data`` = the OAuthClientInformationFull dump) so ``get_client`` can rebuild it.
    Public clients — the MCP case (Claude Code, claude.ai) — carry no secret.
    """

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    client_name: Mapped[str | None] = mapped_column(String(255))
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthAuthorizationCode(Base):
    """A short-lived, single-use PKCE authorization code (deleted on exchange)."""

    __tablename__ = "oauth_authorization_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    redirect_uri_provided_explicitly: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    code_challenge: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    resource: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(String(64), nullable=False)  # ServerAlly user id
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthTokenRecord(Base):
    """An issued access or refresh token — opaque, stored hashed, revocable.

    ``grant_id`` ties the access + refresh issued together (the connection unit revoked
    as a whole); rotation keeps it stable. Named ``...Record`` to avoid clashing with the
    SDK's ``mcp.shared.auth.OAuthToken`` response model.
    """

    __tablename__ = "oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    token_type: Mapped[str] = mapped_column(String(10), nullable=False)  # 'access' | 'refresh'
    grant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # ServerAlly user id
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    resource: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
