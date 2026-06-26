"""Risk 2 graceful fallback: _worker_available() reports whether a Celery worker
is up, so the durable execution path can fall back to inline instead of hanging.
"""
from app.celery_app import celery
from app.websocket import terminal


def _reset_cache():
    terminal._worker_probe["ts"] = -999.0  # force a fresh probe


async def test_worker_available_true(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(celery.control, "ping", lambda timeout=0.5: [{"celery@h": {"ok": "pong"}}])
    assert await terminal._worker_available() is True


async def test_worker_available_false_when_no_replies(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(celery.control, "ping", lambda timeout=0.5: [])
    assert await terminal._worker_available() is False


async def test_worker_available_false_on_broker_error(monkeypatch):
    _reset_cache()

    def boom(timeout=0.5):
        raise RuntimeError("broker down")

    monkeypatch.setattr(celery.control, "ping", boom)
    assert await terminal._worker_available() is False


async def test_worker_probe_is_cached(monkeypatch):
    """A fresh probe is cached; a second call within the TTL doesn't re-ping."""
    _reset_cache()
    calls = {"n": 0}

    def ping(timeout=0.5):
        calls["n"] += 1
        return [{"celery@h": {"ok": "pong"}}]

    monkeypatch.setattr(celery.control, "ping", ping)
    assert await terminal._worker_available() is True
    assert await terminal._worker_available() is True  # cached — no second ping
    assert calls["n"] == 1
