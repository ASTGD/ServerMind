"""Rate limiting.

Two mechanisms:
  - ``limiter``: a slowapi Limiter for HTTP routes (login/register brute-force).
    In-memory storage by default (fine for a single web process; switch to Redis
    storage_uri for multi-worker production).
  - ``check_command_rate``: a Redis fixed-window counter for WebSocket command
    execution (CLAUDE.md rule 8 — 30/min/user/server). Fails OPEN if Redis is
    unavailable so a Redis outage never blocks legitimate work.
"""
from __future__ import annotations

import logging

from slowapi import Limiter

from app.config import settings
from app.services.client_ip import key_func
from app.services.redis_service import get_redis

logger = logging.getLogger(__name__)

# HTTP limiter. The key comes from `client_ip.key_func`, not from the raw peer address:
# in production the backend sits behind Caddy and the frontend nginx container, so keying
# on the peer put every visitor in ONE bucket — one person exhausting the login limit
# would have locked out the entire customer base. For prod multi-worker, pass
# storage_uri=settings.REDIS_URL for a shared window.
#
# key_style="endpoint" is load-bearing, not a preference. slowapi defaults to "url", which
# puts the *request URL* in the bucket key — so on a route with a path parameter, every
# distinct value gets its own bucket. That silently removes all protection from exactly the
# attack these limits exist to stop: guessing an acknowledge token or enumerating status-page
# slugs uses a DIFFERENT value on every request. Found live: 35 POSTs to
# /api/public/ack/{token} with 35 different tokens never hit the 30/minute limit, while 35
# with the same token did. Bucketing by endpoint function makes the limit per-route-per-IP,
# which is what every `@limiter.limit(...)` in this codebase means.
limiter = Limiter(
    key_func=key_func,
    enabled=settings.RATE_LIMIT_ENABLED,
    key_style="endpoint",
)


async def check_command_rate(user_id: str, server_id: str) -> bool:
    """Return True if a command may run, False if the per-minute cap is exceeded.

    Fixed 60s window per (user, server). Fail-open on any Redis error.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return True
    try:
        r = get_redis()
        key = f"rl:cmd:{user_id}:{server_id}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 60)
        return count <= settings.COMMAND_RATE_PER_MIN
    except Exception as exc:  # noqa: BLE001 — never let rate limiting break execution
        logger.warning("Command rate-limit check failed (allowing): %s", exc)
        return True


async def check_rate(bucket: str, limit: int, window_seconds: int = 60) -> bool:
    """Generic per-key fixed-window limiter. True if allowed, False if over the cap.

    Used for the MCP OAuth endpoints (brute-force + DCR-spam protection). Fail-OPEN on any
    Redis error — a rate limiter must never take the service down.
    """
    if not settings.RATE_LIMIT_ENABLED:
        return True
    try:
        r = get_redis()
        key = f"rl:{bucket}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, window_seconds)
        return count <= limit
    except Exception as exc:  # noqa: BLE001 — never let rate limiting break a request
        logger.warning("Rate-limit check failed (allowing) for %s: %s", bucket, exc)
        return True


# ── TOTP login brute-force lockout (per user) ─────────────────────────────────
# A 6-digit code is a small space, so the per-IP slowapi login limit isn't enough
# against rotating IPs. We add a per-user failed-attempt counter. Fail-OPEN on
# Redis errors (the per-IP slowapi limit remains the hard floor).

def _totp_key(user_id: str) -> str:
    return f"totp:fail:{user_id}"


async def totp_locked(user_id: str) -> bool:
    """True if the user has exceeded TOTP_MAX_FAILURES within the lockout window."""
    if not settings.RATE_LIMIT_ENABLED:
        return False
    try:
        n = await get_redis().get(_totp_key(user_id))
        return n is not None and int(n) >= settings.TOTP_MAX_FAILURES
    except Exception as exc:  # noqa: BLE001 — fail open
        logger.warning("TOTP lockout check failed (allowing): %s", exc)
        return False


async def totp_register_failure(user_id: str) -> None:
    """Record one failed TOTP attempt; starts the lockout window on the first."""
    try:
        r = get_redis()
        n = await r.incr(_totp_key(user_id))
        if n == 1:
            await r.expire(_totp_key(user_id), settings.TOTP_LOCKOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TOTP failure record failed: %s", exc)


async def totp_clear_failures(user_id: str) -> None:
    """Clear the failed-attempt counter after a successful TOTP."""
    try:
        await get_redis().delete(_totp_key(user_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("TOTP failure clear failed: %s", exc)
