from __future__ import annotations
"""Authentication endpoints — register, login, refresh, me, password, language."""

import logging

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.services.rate_limit_service import limiter
from app.services.redis_service import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

# Precomputed hash used to equalize login timing when an email is unknown,
# preventing user-enumeration via response-time differences.
_DUMMY_HASH = hash_password("servermind-timing-equalizer")


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class LanguageRequest(BaseModel):
    language: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.REGISTER_RATE_LIMIT)
async def register(request: Request, body: UserCreate, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Register a new user. Email verification skipped — user is active immediately."""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        name=body.name,
        preferred_language=body.preferred_language,
        is_verified=True,  # Skip email verification for Phase 1
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("New user registered: %s", user.email)
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.token_version),
        refresh_token=create_refresh_token(str(user.id), user.token_version),
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Authenticate with email + password."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Always run a hash verification (against a dummy when the email is unknown)
    # so the response time doesn't reveal whether an account exists.
    if user is None:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.token_version),
        refresh_token=create_refresh_token(str(user.id), user.token_version),
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Exchange a refresh token for new access + refresh tokens."""
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    try:
        sub = uuid.UUID(payload.get("sub", ""))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    result = await db.execute(select(User).where(User.id == sub))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if payload.get("tv", 0) != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    return TokenResponse(
        access_token=create_access_token(str(user.id), user.token_version),
        refresh_token=create_refresh_token(str(user.id), user.token_version),
        user=UserOut.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Logout — invalidate every token issued to this user by bumping token_version."""
    current_user.token_version += 1
    await db.commit()
    return None


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Return the authenticated user's profile."""
    return UserOut.model_validate(current_user)


@router.put("/me", response_model=UserOut)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Update name, avatar_url, or preferred_language."""
    if body.name is not None:
        current_user.name = body.name
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url
    if body.preferred_language is not None:
        current_user.preferred_language = body.preferred_language
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Change password — requires current password for verification."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password incorrect")
    current_user.password_hash = hash_password(body.new_password)
    await db.commit()


@router.put("/language", response_model=UserOut)
async def update_language(
    body: LanguageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Update the user's preferred language (ISO 639-1 code)."""
    supported = {"en", "bn", "ar", "es", "fr", "hi", "pt", "tr"}
    if body.language not in supported:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported language. Supported: {supported}")
    current_user.preferred_language = body.language
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.post("/ws-ticket")
async def ws_ticket(current_user: User = Depends(get_current_user)) -> dict:
    """Mint a short-lived, single-use ticket to authenticate a WebSocket
    connection — keeps the JWT out of the WS URL and proxy logs (Update 14.6)."""
    ticket = secrets.token_urlsafe(32)
    try:
        await get_redis().setex(
            f"ws_ticket:{ticket}", settings.WS_TICKET_TTL_SECONDS, str(current_user.id)
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ws-ticket mint failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ticket service unavailable",
        )
    return {"ticket": ticket, "expires_in": settings.WS_TICKET_TTL_SECONDS}
