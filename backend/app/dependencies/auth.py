from __future__ import annotations
"""FastAPI dependency — extract and validate the current user from JWT."""

import logging
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.auth_service import decode_token

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Require a valid access token. Raises 401 on failure."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise unauthorized

    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise unauthorized

    user_id = payload.get("sub")
    if not user_id:
        raise unauthorized

    try:
        user_uuid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise unauthorized

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise unauthorized

    # Token revocation: a token is invalid once the user's token_version has moved
    # past the value embedded in it (bumped on logout/password-change). Default 0
    # so pre-existing tokens (no "tv" claim) keep working until they expire.
    if payload.get("tv", 0) != user.token_version:
        raise unauthorized

    return user


async def require_verified(current_user: User = Depends(get_current_user)) -> User:
    """Like get_current_user, but 403s when email verification is required and the
    user has not verified their address (Update 14.4)."""
    if settings.REQUIRE_EMAIL_VERIFICATION and not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address to continue",
        )
    return current_user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require an internal-staff account. 403s for everyone else. Guards the Dev Door
    (docs/EVAL-DRIVEN-DEV.md) — the Prompt Inspector, dry-run, and eval endpoints must
    never be reachable by a customer, even one with a valid token."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Return current user or None — for endpoints that work both auth'd and anon."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None
