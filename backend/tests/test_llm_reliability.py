"""Reliability of llm_service.complete — an empty/transient provider response must never
reach the caller (and then the user) as an error. complete() retries empties and transient
errors with backoff; client errors (4xx except 429) are NOT retried. (2026-07-11)"""
from app.services import llm_service


def test_is_retryable_transient_vs_client():
    class RateLimitError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    class InternalServerError(Exception):
        status_code = 500

    class Throttled(Exception):
        status_code = 429

    class BadRequestError(Exception):
        status_code = 400

    assert llm_service._is_retryable(RateLimitError())      # by name
    assert llm_service._is_retryable(APITimeoutError())     # by name
    assert llm_service._is_retryable(InternalServerError())  # by 5xx status
    assert llm_service._is_retryable(Throttled())            # by 429 status
    assert not llm_service._is_retryable(BadRequestError())  # 400 → not retried
    assert not llm_service._is_retryable(ValueError("nope"))


def _stub(monkeypatch, fake):
    monkeypatch.setattr(llm_service, "_BACKOFF", (0, 0))
    monkeypatch.setattr(llm_service, "_resolve", lambda: ("anthropic", "k", "m", None))
    monkeypatch.setattr(llm_service, "_tier_model", lambda *a, **k: None)
    monkeypatch.setattr(llm_service, "_anthropic_complete", fake)


async def test_complete_retries_empty_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def fake(*a, **k):
        calls["n"] += 1
        return "" if calls["n"] == 1 else '{"ok": true}'

    _stub(monkeypatch, fake)
    out = await llm_service.complete("sys", "user")
    assert out == '{"ok": true}'
    assert calls["n"] == 2  # retried once on the empty response


async def test_complete_all_empty_returns_empty_string(monkeypatch):
    calls = {"n": 0}

    async def fake(*a, **k):
        calls["n"] += 1
        return "   "  # always whitespace

    _stub(monkeypatch, fake)
    out = await llm_service.complete("sys", "user")
    assert out == ""              # exhausted — caller's JSON parse handles it
    assert calls["n"] == llm_service._MAX_ATTEMPTS  # tried the full budget


async def test_complete_retries_transient_exception_then_succeeds(monkeypatch):
    class InternalServerError(Exception):
        status_code = 503

    calls = {"n": 0}

    async def fake(*a, **k):
        calls["n"] += 1
        if calls["n"] < 2:
            raise InternalServerError("overloaded")
        return '{"ok": true}'

    _stub(monkeypatch, fake)
    out = await llm_service.complete("sys", "user")
    assert out == '{"ok": true}'
    assert calls["n"] == 2


async def test_complete_reraises_client_error_immediately(monkeypatch):
    class BadRequestError(Exception):
        status_code = 400

    calls = {"n": 0}

    async def fake(*a, **k):
        calls["n"] += 1
        raise BadRequestError("bad request")

    _stub(monkeypatch, fake)
    import pytest

    with pytest.raises(BadRequestError):
        await llm_service.complete("sys", "user")
    assert calls["n"] == 1  # a client error is NOT retried
