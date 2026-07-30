"""The frequent malware sweep — what it records, and when it pages someone.

The sweep runs every 5 minutes, so the two things that could go wrong are both about
volume rather than detection: burying real history under 288 identical rows a day, and
paging the owner every 5 minutes about a compromise they already know about.

Deterministic — no SSH, no Postgres. The DB layer is faked, because what is under test is
the worker's decision logic, not SQLAlchemy.
"""
from __future__ import annotations

import pytest

from app.models.server import Server
from app.workers import threat_worker


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value


class _FakeSession:
    """Just enough session to record what the worker tried to persist."""

    def __init__(self, prev_verdict, added):
        self._prev = prev_verdict
        self._added = added

    async def execute(self, _stmt):
        return _FakeResult(self._prev)

    def add(self, obj):
        self._added.append(obj)

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def harness(monkeypatch):
    """Wire the worker to a fake DB and a scriptable scan; capture rows and alerts."""
    state = {"prev": None, "verdict": "clean", "added": [], "alerts": [], "resolved": [],
             "fast_flags": []}

    monkeypatch.setattr(threat_worker, "AsyncSessionLocal",
                        lambda: _FakeSession(state["prev"], state["added"]))

    async def fake_run_scan(server, *, fast_only=False):
        state["fast_flags"].append(fast_only)
        return {
            "verdict": state["verdict"], "status": "completed", "error": None,
            "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "pass": 6},
            "findings": [], "scope": "fast" if fast_only else "full", "duration_ms": 120,
        }

    monkeypatch.setattr(threat_worker.threat_service, "run_scan", fake_run_scan)

    async def fake_notify(server, result):
        state["alerts"].append(result["verdict"])

    monkeypatch.setattr(threat_worker, "_notify", fake_notify)

    async def fake_resolve(db, user_id, key):
        state["resolved"].append(key)

    monkeypatch.setattr(threat_worker.incident_service, "resolve_key", fake_resolve)
    return state


def _server() -> Server:
    return Server(name="web1", host="h", username="u", connection_type="ssh",
                  shell="bash", os_type="ubuntu")


@pytest.mark.asyncio
async def test_unchanged_verdict_records_nothing(harness):
    """288 rows a day of "still clean" would bury the scans a customer cares about."""
    harness["prev"] = "clean"
    harness["verdict"] = "clean"
    await threat_worker._scan_and_alert(_server(), fast_only=True)
    assert harness["added"] == [], "an unchanged fast sweep should not store a row"
    assert harness["alerts"] == []


@pytest.mark.asyncio
async def test_newly_compromised_records_and_pages_immediately(harness):
    """The reason the feature exists: a webshell appears, the owner hears within minutes."""
    harness["prev"] = "clean"
    harness["verdict"] = "compromised"
    await threat_worker._scan_and_alert(_server(), fast_only=True)
    assert len(harness["added"]) == 1, "a new compromise must be recorded"
    assert harness["alerts"] == ["compromised"], "a new compromise must alert"


@pytest.mark.asyncio
async def test_still_compromised_does_not_page_again(harness):
    """One heads-up per incident. Paging every 5 minutes trains people to ignore us."""
    harness["prev"] = "compromised"
    harness["verdict"] = "compromised"
    await threat_worker._scan_and_alert(_server(), fast_only=True)
    assert harness["alerts"] == [], "an already-known compromise must not re-page"
    assert harness["added"] == [], "nor add a duplicate row"


@pytest.mark.asyncio
async def test_recovery_closes_the_incident(harness):
    harness["prev"] = "compromised"
    harness["verdict"] = "clean"
    await threat_worker._scan_and_alert(_server(), fast_only=True)
    assert harness["resolved"], "coming back clean should close the open incident"
    assert len(harness["added"]) == 1, "the recovery itself is a state change worth recording"


@pytest.mark.asyncio
async def test_full_scan_always_records_even_when_unchanged(harness):
    """The 12-hour scan is the heartbeat — it proves we looked, so it always stores."""
    harness["prev"] = "clean"
    harness["verdict"] = "clean"
    await threat_worker._scan_and_alert(_server(), fast_only=False)
    assert len(harness["added"]) == 1
    assert harness["fast_flags"] == [False]


@pytest.mark.asyncio
async def test_sweep_requests_the_fast_scan(harness, monkeypatch):
    """A sweep that quietly ran the full scan would make the 5-minute cadence expensive."""
    monkeypatch.setattr(threat_worker, "AsyncSessionLocal",
                        lambda: _FakeSession([_server()], harness["added"]))
    await threat_worker.sweep_fast()
    assert harness["fast_flags"] == [True], "sweep_fast must ask for fast_only=True"


@pytest.mark.asyncio
async def test_one_bad_server_does_not_stop_the_sweep(harness, monkeypatch):
    servers = [_server(), _server(), _server()]
    servers[0].name = "boom"
    monkeypatch.setattr(threat_worker, "AsyncSessionLocal",
                        lambda: _FakeSession(servers, harness["added"]))

    calls = []

    async def flaky(server, *, fast_only=False):
        calls.append(server.name)
        if server.name == "boom":
            raise RuntimeError("ssh exploded")
        return {"verdict": "clean", "status": "completed", "error": None,
                "counts": {}, "findings": [], "scope": "fast", "duration_ms": 1}

    monkeypatch.setattr(threat_worker.threat_service, "run_scan", flaky)
    await threat_worker.sweep_fast()
    assert len(calls) == 3, "an unreachable server must not abort the rest of the fleet"


@pytest.mark.asyncio
async def test_full_scan_does_not_re_page_a_known_compromise(harness):
    """The 12-hour scan always stores a row, so only the "was it already bad?" check
    stops it paging the owner again about the same incident.

    The fast sweep is protected by its own no-change rule, which meant this path had no
    test — mutation testing found that: deleting `prev not in _ALERTING` broke nothing.
    """
    harness["prev"] = "compromised"
    harness["verdict"] = "compromised"
    await threat_worker._scan_and_alert(_server(), fast_only=False)
    assert len(harness["added"]) == 1, "the full scan is a heartbeat — it still records"
    assert harness["alerts"] == [], (
        "a compromise already known 12 hours ago must not page the owner again"
    )
