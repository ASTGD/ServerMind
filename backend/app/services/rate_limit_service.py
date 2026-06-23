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
from slowapi.util import get_remote_address

from app.config import settings
from app.services.redis_service import get_redis

logger = logging.getLogger(__name__)

# HTTP limiter. NOTE: behind a reverse proxy, configure trusted X-Forwarded-For
# so the client IP (not the proxy IP) is the key; for prod multi-worker, pass
# storage_uri=settings.REDIS_URL for a shared window.
limiter = Limiter(key_func=get_remote_address, enabled=settings.RATE_LIMIT_ENABLED)


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
