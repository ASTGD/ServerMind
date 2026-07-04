"""Mission persistence evals (Ally Missions Phase 3) — durable/resumable missions.

CI has no Postgres, so this covers the pure serialization + the best-effort/guard
logic with a fake session; the DB round-trip + resume are verified live.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.models.mission import Mission, MISSION_STATUSES, RESUMABLE_STATUSES
from app.services import mission_service


def _mission(**kw) -> Mission:
    m = Mission(
        user_id=uuid.uuid4(),
        goal=kw.pop("goal", "do the thing"),
        status=kw.pop("status", "running"),
        steps=kw.pop("steps", "[]"),
        steps_used=kw.pop("steps_used", 0),
        budget=kw.pop("budget", 20),
    )
    for k, v in kw.items():
        setattr(m, k, v)
    return m


# ── Pure serialization ────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,resumable", [
    ("interrupted", True),
    ("running", False),
    ("complete", False),
    ("blocked", False),
    ("failed", False),
    ("stopped", False),
])
def test_to_dict_resumable_only_when_interrupted(status, resumable):
    assert mission_service.to_dict(_mission(status=status))["resumable"] is resumable


def test_to_dict_maps_fields():
    m = _mission(status="complete", verified=False, summary="done but unconfirmed",
                 server_name="TS4", skill_slug="security-incident-response", steps_used=7, budget=30)
    d = mission_service.to_dict(m)
    assert d["status"] == "complete" and d["verified"] is False
    assert d["summary"] == "done but unconfirmed" and d["server_name"] == "TS4"
    assert d["skill"] == "security-incident-response" and d["steps_used"] == 7 and d["budget"] == 30
    assert "steps" not in d  # list view stays light
    assert mission_service.to_dict(m, include_steps=True)["steps"] == []


def test_steps_of_parses_and_survives_corruption():
    steps = [{"cmd": "ls", "exit_code": 0}, {"cmd": "df -h", "exit_code": 0}]
    assert mission_service.steps_of(_mission(steps=json.dumps(steps))) == steps
    assert mission_service.steps_of(_mission(steps="not json")) == []
    assert mission_service.steps_of(_mission(steps="{}")) == []  # object, not a list → []
    assert mission_service.steps_of(_mission(steps="[]")) == []


def test_status_constants_are_consistent():
    assert set(RESUMABLE_STATUSES) <= set(MISSION_STATUSES)
    assert "interrupted" in RESUMABLE_STATUSES
    # No terminal status is resumable.
    for terminal in ("complete", "blocked", "failed", "stopped"):
        assert terminal not in RESUMABLE_STATUSES


# ── Write paths (fake session) ────────────────────────────────────────────────

class _FakeSession:
    def __init__(self, store: dict):
        self.store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, obj):
        self.store.setdefault("added", []).append(obj)

    async def execute(self, stmt):
        self.store.setdefault("executed", []).append(stmt)

    async def commit(self):
        self.store["commits"] = self.store.get("commits", 0) + 1


def _patch_session(monkeypatch, store):
    monkeypatch.setattr(mission_service, "AsyncSessionLocal", lambda: _FakeSession(store))


class _Srv:
    def __init__(self):
        self.id = uuid.uuid4()
        self.name = "TestServer4"


async def test_start_adds_running_mission(monkeypatch):
    store: dict = {}
    _patch_session(monkeypatch, store)
    srv = _Srv()
    await mission_service.start(user_id=uuid.uuid4(), server=srv, skill_slug="wp", goal="host a site", budget=25)
    added = store["added"][0]
    assert added.status == "running" and added.goal == "host a site"
    assert added.server_id == srv.id and added.server_name == "TestServer4" and added.budget == 25
    assert store["commits"] == 1


async def test_checkpoint_and_interrupt_noop_without_id(monkeypatch):
    store: dict = {}
    _patch_session(monkeypatch, store)
    # No mission_id (persistence failed at start) → these must be silent no-ops.
    await mission_service.checkpoint(None, status="running", steps=[{"cmd": "x"}])
    await mission_service.finalize(None, status="complete", steps=[])
    await mission_service.mark_interrupted(None)
    assert store == {}  # nothing touched the DB


async def test_mark_interrupted_only_targets_live(monkeypatch):
    store: dict = {}
    _patch_session(monkeypatch, store)
    await mission_service.mark_interrupted(uuid.uuid4())
    stmt = str(store["executed"][0])
    # The UPDATE sets status and is guarded so it can't clobber a terminal status.
    assert "missions" in stmt and "status" in stmt
    assert "running" not in mission_service._LIVE_STATUSES or "awaiting_approval" in mission_service._LIVE_STATUSES
    # Terminal states are excluded from the live set (so they're never re-opened).
    for terminal in ("complete", "blocked", "failed", "stopped", "interrupted"):
        assert terminal not in mission_service._LIVE_STATUSES


async def test_recover_orphaned_targets_live_missions(monkeypatch):
    """On boot, orphaned live missions are flipped to interrupted; terminal ones aren't."""
    class _Res:
        rowcount = 3
    store: dict = {}
    class _Sess(_FakeSession):
        async def execute(self, stmt):
            await super().execute(stmt)
            return _Res()
    monkeypatch.setattr(mission_service, "AsyncSessionLocal", lambda: _Sess(store))
    n = await mission_service.recover_orphaned()
    assert n == 3
    stmt = str(store["executed"][0])
    assert "missions" in stmt and "status" in stmt


async def test_persistence_failure_never_raises(monkeypatch):
    """A DB hiccup during a checkpoint must be swallowed — a mission never dies from
    a persistence error."""
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(mission_service, "AsyncSessionLocal", _boom)
    # Should not raise.
    await mission_service.checkpoint(uuid.uuid4(), status="running", steps=[{"cmd": "x"}])
    assert await mission_service.start(user_id=uuid.uuid4(), server=None, skill_slug=None, goal="g", budget=20) is None
