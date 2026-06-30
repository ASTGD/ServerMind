"""Offline detection tolerates a transient blip — a server only flips to offline after
two consecutive failed checks, not the first one."""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.workers import metrics_worker


class _FakeDB:
    """Minimal async-session stand-in that records the calls made against it."""
    def __init__(self, calls: list[str]):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    def add(self, _obj):
        self.calls.append("add")

    async def execute(self, _stmt):
        self.calls.append("execute")

    async def commit(self):
        self.calls.append("commit")


def test_single_blip_does_not_flip_offline_two_does():
    async def run():
        srv = SimpleNamespace(id=uuid.uuid4(), name="t", connection_type="ssh")
        sid = str(srv.id)
        metrics_worker._offline_strikes.pop(sid, None)

        calls: list[str] = []
        with patch.object(metrics_worker, "AsyncSessionLocal", lambda: _FakeDB(calls)), patch(
            "app.services.metrics_service.get_metrics",
            new=AsyncMock(side_effect=Exception("network blip")),
        ):
            # First miss: strike 1, status untouched (no DB write at all).
            await metrics_worker._collect_server(srv)
            assert metrics_worker._offline_strikes[sid] == 1
            assert calls == []
            # Second consecutive miss: now it flips to offline (DB write happens).
            await metrics_worker._collect_server(srv)
            assert metrics_worker._offline_strikes[sid] == 2
            assert "commit" in calls

        # A successful check clears the strike count.
        with patch.object(metrics_worker, "AsyncSessionLocal", lambda: _FakeDB([])), patch(
            "app.services.metrics_service.get_metrics",
            new=AsyncMock(return_value={"cpu_percent": 1.0, "ram_percent": 2.0}),
        ):
            await metrics_worker._collect_server(srv)
            assert sid not in metrics_worker._offline_strikes

    asyncio.run(run())
