"""API keys — authenticating a customer's own code.

A browser session lasts 15 minutes and is refreshed by a cookie flow; neither works for a
cron job. An API key is the machine equivalent, with three properties that matter:

- **Shown once.** Only a SHA-256 is stored, so we cannot show a key again and neither can
  anyone who reads the database. A prefix is kept in clear purely so a customer can tell
  their keys apart in a list.
- **Bounded by construction.** A key authenticates only the ``/api/v1`` surface. It cannot
  change a password, disable 2FA, read a server credential, or mint another key — not
  because a check forbids it, but because those routes do not accept keys at all.
- **Scoped.** ``read`` or ``read``+``write``. There is deliberately no admin scope; a key
  that could grant itself more would defeat the point of the first two properties.

SHA-256 rather than bcrypt is deliberate. Password hashing is slow on purpose because
humans choose guessable passwords; a key here is 256 bits from ``secrets``, so there is
nothing to brute-force, and a slow hash on every API request would just be a rate limit we
did not ask for.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.integration import API_SCOPES, SCOPE_READ, SCOPE_WRITE, ApiKey

logger = logging.getLogger(__name__)

# "sa" for ServerAlly, "live" leaving room for a future test-mode key. The visible prefix is
# also what makes a leaked key findable: secret scanners match on a known shape, so a
# distinctive prefix is a security feature, not decoration.
KEY_PREFIX = "sa_live_"
PREFIX_VISIBLE = 8  # characters of the random part kept in clear for display


def generate() -> tuple[str, str, str]:
    """Return ``(full_key, display_prefix, sha256_hex)``.

    The full key is returned to the caller once and never stored.
    """
    body = secrets.token_urlsafe(32)
    full = f"{KEY_PREFIX}{body}"
    return full, f"{KEY_PREFIX}{body[:PREFIX_VISIBLE]}", hash_key(full)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def looks_like_key(value: str | None) -> bool:
    """Cheap shape check, so an obviously-wrong credential never costs a database round trip
    and a JWT is never mistaken for a key."""
    return bool(value) and value.startswith(KEY_PREFIX) and 16 < len(value) <= 128


def normalise_scopes(scopes: list[str] | None) -> list[str]:
    """Keep only scopes we recognise, and make ``write`` imply ``read``.

    A key that could write but not read would be a trap: every useful automation reads
    something back to check its own work.
    """
    picked = {s for s in (scopes or []) if s in API_SCOPES}
    if SCOPE_WRITE in picked:
        picked.add(SCOPE_READ)
    return sorted(picked) or [SCOPE_READ]


def is_usable(key: ApiKey, now: datetime | None = None) -> tuple[bool, str]:
    """Whether this key may be used, and why not if it may not."""
    now = now or datetime.now(tz=timezone.utc)
    if key.revoked_at is not None:
        return False, "This API key has been revoked."
    if key.expires_at is not None:
        expires = key.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= now:
            return False, "This API key has expired."
    return True, ""


async def create(
    db: AsyncSession, user_id: uuid.UUID, name: str,
    scopes: list[str] | None = None, expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    """Mint a key. Returns ``(row, full_key)`` — the full key is the caller's only chance."""
    full, prefix, digest = generate()
    row = ApiKey(
        user_id=user_id, name=name.strip()[:120] or "API key",
        prefix=prefix, key_hash=digest,
        scopes=normalise_scopes(scopes), expires_at=expires_at,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    logger.info("API key created for user %s (%s)", user_id, prefix)
    return row, full


async def resolve(db: AsyncSession, presented: str) -> tuple[ApiKey | None, str]:
    """Look up a presented key. Returns ``(row, error)``; row is None when unusable.

    Lookup is by hash, so the presented secret is never compared against anything stored in
    clear, and a unique index means one hash resolves to exactly one owner.
    """
    if not looks_like_key(presented):
        return None, "Not a valid API key."
    row = (await db.execute(
        select(ApiKey).where(ApiKey.key_hash == hash_key(presented)).limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None, "Unknown API key."
    ok, reason = is_usable(row)
    if not ok:
        return None, reason
    return row, ""


async def touch(db: AsyncSession, key: ApiKey) -> None:
    """Record that the key was used — at most once an hour.

    Writing on every request would turn a read-only API call into a database write, which is
    a real cost on a busy integration for information nobody needs to the second.
    """
    now = datetime.now(tz=timezone.utc)
    last = key.last_used_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is not None and (now - last).total_seconds() < 3600:
        return
    try:
        key.last_used_at = now
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — bookkeeping must never fail a request
        logger.warning("Could not record API key use: %s", exc)
        await db.rollback()


async def revoke(db: AsyncSession, key: ApiKey) -> ApiKey:
    """Revoke rather than delete, so the audit trail of what happened survives."""
    if key.revoked_at is None:
        key.revoked_at = datetime.now(tz=timezone.utc)
        await db.commit()
        await db.refresh(key)
    return key


def serialize(key: ApiKey) -> dict:
    """What the API may say about a key.

    An explicit allowlist because ``key_hash`` must never appear: it is not the secret, but
    publishing the hash of a bearer credential is exactly the kind of "harmless" leak that
    turns into an offline attack the moment the key format changes.
    """
    return {
        "id": str(key.id),
        "name": key.name,
        "prefix": key.prefix,
        "scopes": list(key.scopes or []),
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
        "created_at": key.created_at.isoformat() if key.created_at else None,
    }
