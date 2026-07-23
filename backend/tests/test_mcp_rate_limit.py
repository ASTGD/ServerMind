"""OAuth-endpoint rate limiting (app/mcp/rate_limit.py) — Phase 5 hardening.

The SDK's OAuth routes are CORS-wrapped and unreachable by SlowAPI's decorator, so a
path-based ASGI middleware throttles /oauth/consent, /token, /register per IP. These lock
the middleware's decision logic; the live 429 is validated end-to-end against the server.
"""
from __future__ import annotations

import asyncio

from app.mcp.rate_limit import OAuthRateLimitMiddleware, _LIMITS, _client_ip


class _Capture:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int:
        return self.messages[0]["status"]


async def _downstream(scope, receive, send) -> None:
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _scope(path: str, method: str = "POST", xff: str | None = "1.2.3.4") -> dict:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return {"type": "http", "method": method, "path": path, "headers": headers, "client": ("9.9.9.9", 1)}


def _run(mw, scope) -> _Capture:
    cap = _Capture()
    asyncio.run(mw(scope, None, cap))
    return cap


def test_the_oauth_paths_are_covered():
    assert set(_LIMITS) == {"/oauth/consent", "/token", "/register"}


def test_client_ip_prefers_forwarded_for_then_peer():
    assert _client_ip(_scope("/token")) == "1.2.3.4"
    assert _client_ip(_scope("/token", xff=None)) == "9.9.9.9"


def test_over_limit_returns_429(monkeypatch):
    async def _no(*a, **k):
        return False
    monkeypatch.setattr("app.mcp.rate_limit.check_rate", _no)
    cap = _run(OAuthRateLimitMiddleware(_downstream), _scope("/token"))
    assert cap.status == 429
    assert any(h == (b"retry-after", b"60") for h in cap.messages[0]["headers"])


def test_under_limit_passes_through(monkeypatch):
    async def _yes(*a, **k):
        return True
    monkeypatch.setattr("app.mcp.rate_limit.check_rate", _yes)
    cap = _run(OAuthRateLimitMiddleware(_downstream), _scope("/register"))
    assert cap.status == 200


def test_non_oauth_path_is_never_checked(monkeypatch):
    seen = {"n": 0}

    async def _count(*a, **k):
        seen["n"] += 1
        return False
    monkeypatch.setattr("app.mcp.rate_limit.check_rate", _count)
    cap = _run(OAuthRateLimitMiddleware(_downstream), _scope("/api/servers"))
    assert seen["n"] == 0 and cap.status == 200  # unrelated paths bypass the limiter entirely


def test_get_to_an_oauth_path_is_not_throttled(monkeypatch):
    seen = {"n": 0}

    async def _count(*a, **k):
        seen["n"] += 1
        return False
    monkeypatch.setattr("app.mcp.rate_limit.check_rate", _count)
    cap = _run(OAuthRateLimitMiddleware(_downstream), _scope("/token", method="GET"))
    assert seen["n"] == 0 and cap.status == 200  # only POST is throttled
