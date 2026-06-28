from __future__ import annotations
"""JWT token creation/validation and password hashing."""

import logging
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Passwords ────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given password."""
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the bcrypt hash."""
    return _pwd_context.verify(plain, hashed)


# ── JWT ──────────────────────────────────────────────────────────────────────

def _create_token(data: dict, expires_delta: timedelta) -> str:
    """Create a signed JWT with an expiry."""
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, token_version: int = 0) -> str:
    """Create an access token carrying the user's token_version.

    In development the token is long-lived (30 days) so dev/testing sessions don't
    keep expiring; in production it uses the short ACCESS_TOKEN_EXPIRE_MINUTES.
    """
    expires = (
        timedelta(days=30)
        if settings.APP_ENV == "development"
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return _create_token(
        {"sub": user_id, "type": "access", "tv": token_version},
        expires,
    )


def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    """Create a long-lived refresh token carrying the user's token_version."""
    return _create_token(
        {"sub": user_id, "type": "refresh", "tv": token_version},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def create_verify_token(user_id: str) -> str:
    """Create a short-lived email-verification token (type='verify')."""
    return _create_token(
        {"sub": user_id, "type": "verify"},
        timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_HOURS),
    )


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT. Returns payload or None on failure."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        logger.debug("JWT decode failed: %s", exc)
        return None
