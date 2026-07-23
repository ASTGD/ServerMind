"""Per-IP rate limiting for the MCP OAuth endpoints (docs/MCP-SERVER-PLAN.md Phase 5).

SlowAPI's ``@limiter.limit`` decorator can't be applied to the SDK's OAuth routes (they're
CORS-wrapped raw Starlette routes, not our functions), so a small path-based ASGI middleware
throttles them instead:

- ``/oauth/consent`` — a password surface (a valid signed txn + email/password) → tight.
- ``/token`` — code exchange + refresh → generous (legit clients refresh periodically).
- ``/register`` — Dynamic Client Registration → tight (a client registers rarely; the plan
  flags DCR client-table bloat, §12).

Fail-OPEN: a Redis hiccup never blocks a legitimate OAuth flow.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.rate_limit_service import check_rate

# path → (limit, window_seconds), POST only.
_LIMITS: dict[str, tuple[int, int]] = {
    "/oauth/consent": (10, 60),
    "/token": (30, 60),
    "/register": (10, 60),
}

_BODY = (
    b'{"error":"rate_limited",'
    b'"error_description":"Too many requests. Please slow down and try again shortly."}'
)


def _client_ip(scope: Scope) -> str:
    """The caller's IP — honour the first X-Forwarded-For hop (behind a reverse proxy),
    else the direct peer."""
    for name, value in scope.get("headers") or []:
        if name == b"x-forwarded-for":
            return value.decode("latin-1").split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


class OAuthRateLimitMiddleware:
    """Throttle the OAuth mutation endpoints per IP; 429 when over the cap."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http" and scope.get("method") == "POST":
            limit = _LIMITS.get(scope.get("path", ""))
            if limit is not None:
                ip = _client_ip(scope)
                allowed = await check_rate(f"oauth:{scope['path']}:{ip}", limit[0], limit[1])
                if not allowed:
                    await self._reject(send)
                    return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Send) -> None:
        start: Message = {
            "type": "http.response.start",
            "status": 429,
            "headers": [(b"content-type", b"application/json"), (b"retry-after", b"60")],
        }
        await send(start)
        await send({"type": "http.response.body", "body": _BODY})
