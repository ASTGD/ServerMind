"""rate_limit_service — WebSocket command cap + per-user TOTP lockout.

Uses fakeredis so the tests need no live Redis."""
import pytest
from fakeredis import aioredis as fake_aioredis

from app.config import settings
from app.services import rate_limit_service as rl


@pytest.fixture
def fake_redis(monkeypatch):
    client = fake_aioredis.FakeRedis(decode_responses=True)
    # rate_limit_service binds get_redis at import — patch it there.
    monkeypatch.setattr(rl, "get_redis", lambda: client)
    return client


async def test_command_rate_allows_then_blocks(fake_redis):
    for _ in range(settings.COMMAND_RATE_PER_MIN):
        assert await rl.check_command_rate("u1", "s1") is True
    # one past the per-minute cap
    assert await rl.check_command_rate("u1", "s1") is False
    # a different (user, server) has its own budget
    assert await rl.check_command_rate("u1", "s2") is True


async def test_totp_lockout_after_threshold(fake_redis):
    uid = "u2"
    assert await rl.totp_locked(uid) is False
    for _ in range(settings.TOTP_MAX_FAILURES):
        await rl.totp_register_failure(uid)
    assert await rl.totp_locked(uid) is True
    await rl.totp_clear_failures(uid)
    assert await rl.totp_locked(uid) is False


async def test_fails_open_when_redis_unavailable(monkeypatch):
    class Broken:
        async def incr(self, *a, **k):
            raise RuntimeError("redis down")

        async def get(self, *a, **k):
            raise RuntimeError("redis down")

    monkeypatch.setattr(rl, "get_redis", lambda: Broken())
    # Fail OPEN: a Redis outage must not block legitimate work / lock everyone out.
    assert await rl.check_command_rate("u", "s") is True
    assert await rl.totp_locked("u") is False
