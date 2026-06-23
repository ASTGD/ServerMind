"""Async Redis client — lazy singleton from REDIS_URL.

Connection is established lazily on first use; callers should treat Redis as
best-effort (fail-open) so a Redis outage degrades gracefully rather than taking
down auth / rate limiting.
"""
from __future__ import annotations

import logging

from redis.asyncio import Redis, from_url

from app.config import settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


def get_redis() -> Redis:
    """Return the shared async Redis client (does not connect until first command)."""
    global _client
    if _client is None:
        _client = from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    return _client
