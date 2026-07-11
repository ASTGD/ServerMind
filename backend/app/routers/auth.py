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
    create_verify_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.services import ai_service, audit_service, notification_service, totp_service
from app.services.rate_limit_service import (
    limiter,
    totp_clear_failures,
    totp_locked,
    totp_register_failure,
)
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
    totp_code: str | None = None


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


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class TotpCodeRequest(BaseModel):
    code: str


class TotpVerifyResponse(BaseModel):
    user: UserOut
    recovery_codes: list[str]


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class VerifyEmailRequest(BaseModel):
    token: str


# ── Endpoints ─────────────────────────────────────────────────────────────────


async def _consume_recovery_code(db: AsyncSession, user: User, code: str) -> bool:
    """If ``code`` matches one of the user's stored recovery-code hashes, consume
    it (one-time use), persist the remaining codes, and return True."""
    codes = user.totp_recovery_codes or []
    if not codes or not code:
        return False
    h = totp_service.hash_code(code)
    if h in codes:
        user.totp_recovery_codes = [c for c in codes if c != h]
        await db.commit()
        return True
    return False


async def _send_verification_email(user: User, request: Request) -> None:
    """Email the user a signed link to verify their address. Best-effort."""
    token = create_verify_token(str(user.id))
    base = settings.APP_BASE_URL or str(request.base_url).rstrip("/")
    link = f"{base}/verify-email?token={token}"
    await notification_service.send_email(
        user.email,
        "Verify your ServerAlly email",
        (
            "Welcome to ServerAlly! Confirm your email to activate your account:\n\n"
            f"{link}\n\n"
            f"This link expires in {settings.EMAIL_VERIFICATION_TOKEN_HOURS} hours. "
            "If you didn't sign up, you can ignore this email."
        ),
    )


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
        is_verified=not settings.REQUIRE_EMAIL_VERIFICATION,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if settings.REQUIRE_EMAIL_VERIFICATION:
        await _send_verification_email(user, request)

    logger.info("New user registered: %s", user.email)
    await audit_service.audit(db, user, "auth.register", request=request)
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

    # Second factor (TOTP), when enabled. A single generic 401 covers both a
    # missing and an invalid code so we don't reveal which it was.
    if user.totp_enabled:
        if await totp_locked(str(user.id)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many 2FA attempts — try again later.",
            )
        code = body.totp_code
        ok = bool(code) and (
            totp_service.verify(user.totp_secret, code)
            or await _consume_recovery_code(db, user, code)
        )
        if not ok:
            await totp_register_failure(str(user.id))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="TOTP code required"
            )
        await totp_clear_failures(str(user.id))

    await audit_service.audit(db, user, "auth.login", request=request)
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
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Logout — invalidate every token issued to this user by bumping token_version."""
    current_user.token_version += 1
    await db.commit()
    await audit_service.audit(db, current_user, "auth.logout", request=request)
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
    """Update name, avatar_url, preferred_language, or ally_mode."""
    if body.name is not None:
        current_user.name = body.name
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url
    if body.preferred_language is not None:
        current_user.preferred_language = body.preferred_language
    if body.ally_mode is not None:
        # Coerce to a known mode so a bad value can't reach the prompt layer (Track D).
        current_user.ally_mode = ai_service.normalize_mode(body.ally_mode)
    await db.commit()
    await db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: Request,
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Change password — requires current password for verification."""
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password incorrect")
    current_user.password_hash = hash_password(body.new_password)
    await db.commit()
    await audit_service.audit(db, current_user, "auth.password_change", request=request)


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


@router.post("/2fa/setup", response_model=TotpSetupResponse)
async def totp_setup(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TotpSetupResponse:
    """Begin TOTP enrollment: store a fresh (still-disabled) secret and return it
    plus the otpauth URI for QR display. 2FA is only activated by /2fa/verify."""
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled",
        )
    secret = totp_service.generate_secret()
    current_user.totp_secret = totp_service.encrypt_secret(secret)
    await db.commit()
    return TotpSetupResponse(
        secret=secret,
        otpauth_uri=totp_service.provisioning_uri(secret, current_user.email),
    )


@router.post("/2fa/verify", response_model=TotpVerifyResponse)
async def totp_verify(
    request: Request,
    body: TotpCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TotpVerifyResponse:
    """Confirm a TOTP code from the authenticator app to activate 2FA."""
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled",
        )
    if not current_user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run 2FA setup first")
    if await totp_locked(str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many 2FA attempts — try again later.",
        )
    if not totp_service.verify(current_user.totp_secret, body.code):
        await totp_register_failure(str(current_user.id))
        # 400, not 401 — a 401 trips the global client interceptor and logs the
        # (authenticated) user out for a mistyped code.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code")
    await totp_clear_failures(str(current_user.id))
    recovery = totp_service.generate_recovery_codes()
    current_user.totp_recovery_codes = [totp_service.hash_code(c) for c in recovery]
    current_user.totp_enabled = True
    await db.commit()
    await db.refresh(current_user)
    await audit_service.audit(db, current_user, "auth.2fa_enabled", request=request)
    return TotpVerifyResponse(
        user=UserOut.model_validate(current_user),
        recovery_codes=recovery,
    )


@router.delete("/2fa", response_model=UserOut)
async def totp_disable(
    request: Request,
    body: TotpCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    """Disable 2FA — requires a current TOTP code (guards against session takeover)."""
    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled",
        )
    if await totp_locked(str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many 2FA attempts — try again later.",
        )
    if not (
        totp_service.verify(current_user.totp_secret, body.code)
        or await _consume_recovery_code(db, current_user, body.code)
    ):
        await totp_register_failure(str(current_user.id))
        # 400, not 401 — avoids the global interceptor logging the user out, and
        # the per-user lockout makes brute-forcing the disable endpoint impractical.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code")
    await totp_clear_failures(str(current_user.id))
    current_user.totp_enabled = False
    current_user.totp_secret = None
    current_user.totp_recovery_codes = None
    await db.commit()
    await db.refresh(current_user)
    await audit_service.audit(db, current_user, "auth.2fa_disabled", request=request)
    return UserOut.model_validate(current_user)


@router.post("/2fa/recovery-codes", response_model=RecoveryCodesResponse)
async def regenerate_recovery_codes(
    request: Request,
    body: TotpCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RecoveryCodesResponse:
    """Replace the user's recovery codes with a fresh set. Requires a current TOTP
    code (the authenticator app), not a recovery code."""
    if not current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled",
        )
    if await totp_locked(str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many 2FA attempts — try again later.",
        )
    if not totp_service.verify(current_user.totp_secret, body.code):
        await totp_register_failure(str(current_user.id))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid TOTP code")
    await totp_clear_failures(str(current_user.id))
    recovery = totp_service.generate_recovery_codes()
    current_user.totp_recovery_codes = [totp_service.hash_code(c) for c in recovery]
    await db.commit()
    await audit_service.audit(db, current_user, "auth.2fa_recovery_regenerated", request=request)
    return RecoveryCodesResponse(recovery_codes=recovery)


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Confirm an email address from a signed verification token (no auth needed)."""
    payload = decode_token(body.token)
    if not payload or payload.get("type") != "verify":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link",
        )
    try:
        uid = uuid.UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification link")
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if not user.is_verified:
        user.is_verified = True
        await db.commit()
    return {"verified": True}


class ClaimRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


@router.post("/claim", response_model=TokenResponse)
async def claim_account(
    request: Request, body: ClaimRequest, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    """Claim a billing-provisioned account (docs/WHMCS-INTEGRATION.md): a one-time
    signed link lets the customer set their first password and signs them in. The
    token carries the account's token_version and claiming bumps it, so a claim link
    dies on first use."""
    payload = decode_token(body.token)
    if not payload or payload.get("type") != "claim":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired claim link",
        )
    try:
        uid = uuid.UUID(payload.get("sub", ""))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid claim link")
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if payload.get("tv", 0) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This claim link was already used — sign in instead, or reset your password.",
        )

    user.password_hash = hash_password(body.password)
    user.is_verified = True
    user.token_version += 1  # kills the claim token (and any stray older tokens)
    await db.commit()
    await db.refresh(user)

    await audit_service.audit(db, user, "auth.claim", request=request)
    logger.info("Account claimed: %s", user.email)
    return TokenResponse(
        access_token=create_access_token(str(user.id), user.token_version),
        refresh_token=create_refresh_token(str(user.id), user.token_version),
        user=UserOut.model_validate(user),
    )


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> None:
    """Re-send the verification email to the current user (no-op if verified)."""
    if not current_user.is_verified:
        await _send_verification_email(current_user, request)
    return None
