from __future__ import annotations
"""TOTP (time-based one-time password) two-factor auth.

Secrets are stored AES-256-GCM encrypted (via crypto_service); the plaintext
base32 secret only exists in memory during setup (to render the QR / otpauth
URI) and during verification (decrypted just-in-time). The secret is never
returned by the API once 2FA is enabled.
"""

import hashlib
import logging
import secrets

import pyotp

from app.services import crypto_service

logger = logging.getLogger(__name__)

ISSUER = "ServerMind"
RECOVERY_CODE_COUNT = 10


def generate_secret() -> str:
    """Return a fresh random base32 TOTP secret (plaintext, 32 chars)."""
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    """Encrypt a plaintext base32 secret for DB storage (~80 chars)."""
    return crypto_service.encrypt(secret)


def provisioning_uri(secret: str, email: str, issuer: str = ISSUER) -> str:
    """Build the otpauth:// URI for a *plaintext* secret (for QR rendering)."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify(encrypted_secret: str | None, code: str | None, valid_window: int = 1) -> bool:
    """Verify a 6-digit code against an ENCRYPTED stored secret.

    Decrypts just-in-time. ``valid_window=1`` accepts the previous/current/next
    30-second step to tolerate clock skew. Returns ``False`` (never raises) on a
    missing/bad code or an undecryptable secret, so callers can treat any failure
    as a clean auth rejection rather than a 500.
    """
    if not encrypted_secret or not code:
        return False
    code = code.strip().replace(" ", "")
    try:
        secret = crypto_service.decrypt(encrypted_secret)
    except Exception:  # noqa: BLE001 — InvalidTag / malformed base64 / value errors
        logger.warning("TOTP secret decrypt failed during verify")
        return False
    # pyotp.verify uses hmac.compare_digest internally (constant-time).
    return pyotp.TOTP(secret).verify(code, valid_window=valid_window)


# ── Recovery / backup codes ───────────────────────────────────────────────────

def normalize_code(code: str) -> str:
    """Canonicalise a recovery code so formatting (case/dashes/spaces) doesn't matter."""
    return code.strip().lower().replace("-", "").replace(" ", "")


def hash_code(code: str) -> str:
    """Hash a recovery code for storage. SHA-256 is appropriate (the codes are
    high-entropy random tokens, not user-chosen passwords)."""
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


def generate_recovery_codes(n: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Return n fresh plaintext recovery codes, formatted like 'abcd-ef01'."""
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(n)]

