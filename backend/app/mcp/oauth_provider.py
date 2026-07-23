"""OAuth 2.1 authorization-server provider + bearer verifier for the MCP server.

Implements the MCP SDK's ``OAuthAuthorizationServerProvider`` and ``TokenVerifier``.
The SDK owns the protocol (PKCE S256, DCR, metadata shapes, the 401 handshake); this
module owns storage, token issuance, and the consent hand-off.

Design (docs/MCP-SERVER-PLAN.md §5, §10):
- Tokens + codes are opaque (``secrets.token_urlsafe``) and stored SHA-256-hashed, so a
  DB read can't replay them.
- Access + refresh issued together share a ``grant_id`` — the connection unit revoked as
  a whole. Refresh rotation keeps ``grant_id`` stable and invalidates the old pair, so a
  replayed refresh token fails (``load_refresh_token`` → None → ``invalid_grant``).
- Per-user by construction: a token's ``subject`` is a ServerAlly user id; tools scope
  every read to that user's ``accessible_servers`` (Rule 7).
- The consent hand-off is storage-free: ``authorize`` hands the browser a short-lived
  SIGNED transaction (JWT), and the consent route mints the code once the user approves.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from jose import JWTError, jwt
from pydantic import AnyUrl
from sqlalchemy import delete, select

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenVerifier,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.oauth import OAuthAuthorizationCode, OAuthClient, OAuthTokenRecord

logger = logging.getLogger(__name__)

# Scopes (Phase 4): read tools need mcp:read, write tools need mcp:write. A "Read-only"
# connection carries just mcp:read (the safe first-connection default); "Full" carries both.
SCOPE_READ = "mcp:read"
SCOPE_WRITE = "mcp:write"
ALL_SCOPES = [SCOPE_READ, SCOPE_WRITE]
DEFAULT_SCOPES = [SCOPE_READ]  # read-only by default — the safe first connection
SCOPE = SCOPE_READ  # back-compat alias (the base scope every connection has)

_TXN_TTL_SECONDS = 600  # signed consent transaction — 10 minutes
_TXN_TYPE = "mcp_consent"


# ── small helpers ─────────────────────────────────────────────────────────────

def mcp_enabled_for(user) -> bool:
    """MCP is a paid-tier platform feature (docs/MCP-SERVER-PLAN.md §8). When plan limits
    are enforced (cloud), free plans are gated; otherwise (dev / self-hosted) it's on for
    everyone."""
    if not settings.ENFORCE_PLAN_LIMITS:
        return True
    return (getattr(user, "plan", None) or "free").lower() != "free"


def _hash(value: str) -> str:
    """SHA-256 hex — how every code/token is stored + looked up."""
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """asyncpg returns aware datetimes for timestamptz; guard just in case."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _expired(dt: datetime) -> bool:
    return _aware(dt) < _now()


def _epoch(dt: datetime) -> int:
    return int(_aware(dt).timestamp())


# ── signed consent transaction (no pending-auth table) ────────────────────────

def sign_txn(data: dict) -> str:
    """Encode a pending authorization request into a short-lived signed token."""
    payload = {**data, "typ": _TXN_TYPE, "exp": int(time.time()) + _TXN_TTL_SECONDS}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_txn(token: str) -> dict | None:
    """Decode + validate a consent transaction; None if invalid/expired/tampered."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("typ") != _TXN_TYPE:
        return None
    return payload


# ── provider ──────────────────────────────────────────────────────────────────

class ServerAllyOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken],
    TokenVerifier,
):
    """DB-backed OAuth 2.1 provider (AS side) + bearer verifier (RS side).

    Each method opens its own session (stateless singleton), mirroring the tool layer.
    """

    # ── clients (Dynamic Client Registration) ─────────────────────────────────

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OAuthClient).where(OAuthClient.client_id == client_id)
            )).scalar_one_or_none()
        if row is None:
            return None
        return OAuthClientInformationFull.model_validate(row.data)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        async with AsyncSessionLocal() as db:
            db.add(OAuthClient(
                client_id=client_info.client_id,
                client_name=client_info.client_name,
                data=client_info.model_dump(mode="json"),
            ))
            await db.commit()
        logger.info(
            "MCP OAuth: registered client %s (%s)", client_info.client_id, client_info.client_name
        )

    # ── authorization ─────────────────────────────────────────────────────────

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """Return the URL to redirect the browser to — our consent page, carrying a
        signed description of this request. The SDK's /authorize handler has already
        validated the client, redirect_uri, and PKCE challenge."""
        txn = sign_txn({
            "client_id": client.client_id,
            "client_name": client.client_name,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "code_challenge": params.code_challenge,
            "scopes": params.scopes or DEFAULT_SCOPES,
            "state": params.state,
            "resource": params.resource,
        })
        base = settings.MCP_BASE_URL.rstrip("/")
        return f"{base}/oauth/consent?txn={txn}"

    async def create_authorization_code(
        self, txn: dict, user_id: str, scopes: list[str] | None = None
    ) -> str:
        """Called by the consent route once the user has logged in AND approved.

        Mints a single-use code bound to this user + request, and returns the redirect
        URL back to the client (``redirect_uri?code=…&state=…``). ``scopes`` is the access
        level the user chose on the consent page (read-only vs full); it overrides whatever
        the client requested.
        """
        code = secrets.token_urlsafe(32)
        scopes = list(scopes or txn.get("scopes") or DEFAULT_SCOPES)
        async with AsyncSessionLocal() as db:
            db.add(OAuthAuthorizationCode(
                code_hash=_hash(code),
                client_id=txn["client_id"],
                redirect_uri=txn["redirect_uri"],
                redirect_uri_provided_explicitly=bool(txn.get("redirect_uri_provided_explicitly", True)),
                code_challenge=txn.get("code_challenge"),
                scopes=scopes,
                resource=txn.get("resource"),
                subject=str(user_id),
                expires_at=_now() + timedelta(seconds=settings.MCP_CODE_TTL_SECONDS),
            ))
            await db.commit()

        redirect_uri = txn["redirect_uri"]
        query = {"code": code}
        if txn.get("state") is not None:
            query["state"] = txn["state"]
        sep = "&" if "?" in redirect_uri else "?"
        return f"{redirect_uri}{sep}{urlencode(query)}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OAuthAuthorizationCode).where(
                    OAuthAuthorizationCode.code_hash == _hash(authorization_code)
                )
            )).scalar_one_or_none()
        if row is None or row.client_id != client.client_id or _expired(row.expires_at):
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=list(row.scopes or []),
            expires_at=_aware(row.expires_at).timestamp(),
            client_id=row.client_id,
            code_challenge=row.code_challenge or "",
            redirect_uri=AnyUrl(row.redirect_uri),
            redirect_uri_provided_explicitly=row.redirect_uri_provided_explicitly,
            resource=row.resource,
            subject=row.subject,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        async with AsyncSessionLocal() as db:
            # Single-use: consume the code.
            await db.execute(
                delete(OAuthAuthorizationCode).where(
                    OAuthAuthorizationCode.code_hash == _hash(authorization_code.code)
                )
            )
            token = await self._issue_grant(
                db,
                client_id=client.client_id,
                subject=authorization_code.subject or "",
                scopes=list(authorization_code.scopes or DEFAULT_SCOPES),
                resource=authorization_code.resource,
                grant_id=uuid.uuid4(),
            )
            await db.commit()
        return token

    # ── refresh (with rotation) ────────────────────────────────────────────────

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OAuthTokenRecord).where(
                    OAuthTokenRecord.token_hash == _hash(refresh_token),
                    OAuthTokenRecord.token_type == "refresh",
                )
            )).scalar_one_or_none()
        if row is None or row.client_id != client.client_id or _expired(row.expires_at):
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=row.client_id,
            scopes=list(row.scopes or []),
            expires_at=_epoch(row.expires_at),
            subject=row.subject,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        """Rotate: invalidate the old grant (both tokens) and issue a new pair, keeping
        ``grant_id`` stable so the connection persists across refreshes."""
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OAuthTokenRecord).where(
                    OAuthTokenRecord.token_hash == _hash(refresh_token.token),
                    OAuthTokenRecord.token_type == "refresh",
                )
            )).scalar_one_or_none()
            if row is None or row.client_id != client.client_id or _expired(row.expires_at):
                raise ValueError("invalid_grant")  # SDK maps to an OAuth error response
            grant_id = row.grant_id
            subject = row.subject
            use_scopes = list(scopes) if scopes else list(row.scopes or DEFAULT_SCOPES)
            resource = row.resource
            # Rotation: drop the whole old grant (old access + old refresh).
            await db.execute(delete(OAuthTokenRecord).where(OAuthTokenRecord.grant_id == grant_id))
            token = await self._issue_grant(
                db,
                client_id=client.client_id,
                subject=subject,
                scopes=use_scopes,
                resource=resource,
                grant_id=grant_id,
            )
            await db.commit()
        return token

    # ── access tokens (RS-side verification) ───────────────────────────────────

    async def load_access_token(self, token: str) -> AccessToken | None:
        return await self._load_access(token)

    async def verify_token(self, token: str) -> AccessToken | None:
        """TokenVerifier — the /mcp bearer check. Same lookup as load_access_token."""
        return await self._load_access(token)

    async def _load_access(self, token: str) -> AccessToken | None:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OAuthTokenRecord).where(
                    OAuthTokenRecord.token_hash == _hash(token),
                    OAuthTokenRecord.token_type == "access",
                )
            )).scalar_one_or_none()
        if row is None or _expired(row.expires_at):
            return None
        return AccessToken(
            token=token,
            client_id=row.client_id,
            scopes=list(row.scopes or []),
            expires_at=_epoch(row.expires_at),
            resource=row.resource,
            subject=row.subject,
        )

    # ── revocation ─────────────────────────────────────────────────────────────

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """Revoke the WHOLE connection (both access + refresh) — RFC 7009 + the plan's
        'revoke → client immediately loses access'."""
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(OAuthTokenRecord).where(OAuthTokenRecord.token_hash == _hash(token.token))
            )).scalar_one_or_none()
            if row is not None:
                await db.execute(
                    delete(OAuthTokenRecord).where(OAuthTokenRecord.grant_id == row.grant_id)
                )
                await db.commit()

    # ── issuance helper ────────────────────────────────────────────────────────

    async def _issue_grant(
        self, db, *, client_id: str, subject: str, scopes: list[str], resource, grant_id: uuid.UUID
    ) -> OAuthToken:
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        now = _now()
        db.add(OAuthTokenRecord(
            token_hash=_hash(access), token_type="access", grant_id=grant_id,
            client_id=client_id, subject=subject, scopes=scopes, resource=resource,
            expires_at=now + timedelta(seconds=settings.MCP_ACCESS_TTL_SECONDS),
        ))
        db.add(OAuthTokenRecord(
            token_hash=_hash(refresh), token_type="refresh", grant_id=grant_id,
            client_id=client_id, subject=subject, scopes=scopes, resource=resource,
            expires_at=now + timedelta(seconds=settings.MCP_REFRESH_TTL_SECONDS),
        ))
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=settings.MCP_ACCESS_TTL_SECONDS,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )


# Singleton — used as BOTH the AS provider (create_auth_routes) and the RS token
# verifier (BearerAuthBackend). One instance, one source of truth.
oauth_provider = ServerAllyOAuthProvider()
