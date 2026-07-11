"""Dev Door (docs/EVAL-DRIVEN-DEV.md) Phase 0 — the admin gate, the shared context
assembly, trace capture, and the dry-run's read-only guarantee.

The load-bearing properties:
  * require_admin 403s a non-admin (a customer must never reach the Dev Door).
  * dev_service.dry_run returns a full trace (prompt + raw + parsed + meta) and NEVER
    executes a command (it plans only).
  * plan_commands fills a passed-in trace with the exact prompt + raw output.
  * build_chat_context assembles the same fields the live chat uses, and degrades to a
    partial context (never crashes) when its DB work fails.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.database as database
from app.dependencies.auth import require_admin
from app.services import (
    ai_context_service,
    ai_service,
    connection_manager,
    dev_service,
    llm_service,
    memory_service,
    team_service,
)

_PLAN_JSON = (
    '{"intent_understood":"check disk","plan_summary":"Check disk usage",'
    '"commands":[{"cmd":"df -h","description":"Show disk usage","risk_level":"low",'
    '"requires_confirmation":false}],"post_execution_message":"done"}'
)


def _server(**kw):
    d = dict(
        id=uuid.uuid4(), name="TestServer", os_type="ubuntu", os_version="22.04",
        connection_type="ssh", shell="bash", arch="amd64", user_id=uuid.uuid4(),
        panel_type=None, status="online",
    )
    d.update(kw)
    return SimpleNamespace(**d)


def _user(**kw):
    d = dict(id=uuid.uuid4(), preferred_language="en", ally_mode="normal", is_admin=True)
    d.update(kw)
    return SimpleNamespace(**d)


# ── The admin gate ────────────────────────────────────────────────────────────

async def test_require_admin_forbids_non_admin():
    with pytest.raises(HTTPException) as ei:
        await require_admin(current_user=_user(is_admin=False))
    assert ei.value.status_code == 403


async def test_require_admin_allows_admin():
    admin = _user(is_admin=True)
    assert await require_admin(current_user=admin) is admin


# ── The dry-run: full trace, zero execution ───────────────────────────────────

async def test_dry_run_returns_full_trace_and_never_executes(monkeypatch):
    server, admin = _server(), _user()

    async def fake_ctx(*a, **k):
        return ai_context_service.ChatContext(
            server_profile="PROFILE-XYZ", memories="MEM-XYZ", ally_mode="normal",
            other_servers=None, scout=None, live_snapshot=None, skill_menu="MENU",
        )

    async def fake_complete(system, user, **k):
        return _PLAN_JSON

    def boom(*a, **k):
        raise AssertionError("dry_run must NEVER execute a command on a server")

    monkeypatch.setattr(ai_context_service, "build_chat_context", fake_ctx)
    monkeypatch.setattr(llm_service, "complete", fake_complete)
    monkeypatch.setattr(connection_manager, "execute", boom)
    monkeypatch.setattr(connection_manager, "execute_stream", boom)

    result = await dev_service.dry_run(server, "how much disk is free?", acting_user=admin)

    # Output — the parsed plan and the exact raw model text.
    assert result["output"]["parsed"]["plan_summary"] == "Check disk usage"
    assert result["output"]["raw"] == _PLAN_JSON
    # Prompt — the exact prompt Ally received was captured; the mocked context reached it.
    assert result["prompt"]["system"]
    assert "PROFILE-XYZ" in result["prompt"]["volatile"]
    assert "MEM-XYZ" in result["prompt"]["volatile"]
    # Input + context + meta shape.
    assert result["input"]["server"]["name"] == "TestServer"
    assert result["context"]["skill_menu_offered"] is True
    assert "cost_usd" in result["meta"] and "input_tokens" in result["meta"]
    # (boom would have raised if any execution path were reached.)


# ── Trace capture inside plan_commands ────────────────────────────────────────

async def test_plan_commands_populates_trace(monkeypatch):
    async def fake_complete(system, user, **k):
        return _PLAN_JSON

    monkeypatch.setattr(llm_service, "complete", fake_complete)
    trace: dict = {}
    plan = await ai_service.plan_commands(
        "check disk", _server(), "en", server_profile="PROF-123", trace=trace
    )
    assert plan["plan_summary"] == "Check disk usage"
    assert trace["user_input"] == "check disk"
    assert trace["system"]                 # stable prompt captured
    assert "PROF-123" in trace["volatile"]  # the profile rode the volatile tail
    assert trace["raw"] == _PLAN_JSON


async def test_plan_commands_no_trace_is_noop(monkeypatch):
    """Passing no trace must not change behavior (prod path)."""
    async def fake_complete(system, user, **k):
        return _PLAN_JSON

    monkeypatch.setattr(llm_service, "complete", fake_complete)
    plan = await ai_service.plan_commands("check disk", _server(), "en")
    assert plan["plan_summary"] == "Check disk usage"


# ── build_chat_context: assembly + best-effort ────────────────────────────────

async def test_build_chat_context_assembles_fields(monkeypatch):
    server = _server()
    other = _server(name="OtherBox", os_type="debian")
    actor = SimpleNamespace(id=uuid.uuid4(), ally_mode="proactive")

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, model, key):
            return actor

    async def prof(db, s):
        return "PROFILE"

    async def health(db, servers):
        return {}

    async def mem(db, sid, owner):
        return "MEM"

    async def roster(db, user, home=None, cap=15):
        return [other]

    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(ai_context_service, "build_server_profile", prof)
    monkeypatch.setattr(ai_context_service, "build_fleet_health", health)
    monkeypatch.setattr(memory_service, "block_for_server", mem)
    monkeypatch.setattr(team_service, "mission_roster", roster)

    ctx = await ai_context_service.build_chat_context(
        server, "hello", acting_user_id=str(uuid.uuid4()), skill=None,
        want_scout=False, want_live=False,
    )

    assert ctx.server_profile == "PROFILE"
    assert ctx.memories == "MEM"
    assert ctx.ally_mode == "proactive"
    assert "OtherBox" in (ctx.other_servers or "")
    assert ctx.skill_menu is not None          # skill=None → the menu is offered
    assert ctx.scout is None and ctx.live_snapshot is None  # probes skipped


async def test_build_chat_context_best_effort_on_db_failure(monkeypatch):
    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(database, "AsyncSessionLocal", boom)
    ctx = await ai_context_service.build_chat_context(
        _server(), "hi", acting_user_id=str(uuid.uuid4()), skill=None,
        want_scout=False, want_live=False,
    )
    assert ctx.skill_menu is not None   # still assembled
    assert ctx.server_profile is None   # DB failed → degraded, never crashed
