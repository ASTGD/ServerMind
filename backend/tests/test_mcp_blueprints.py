"""Blueprints over MCP — the front-desk contract, driven.

The properties that matter to a caller that is an AI: a missing input names what to ASK
THE USER for (never guessed); start returns immediately with an id (never blocks); a
read-only connection cannot start or stop; stop needs the same permission that started it;
and the run payload never carries anything but the run.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.mcp import server as m


class _Session:
    async def __aenter__(self): return self
    async def __aexit__(self, *e): return False


def _ok(value):
    async def _f(*a, **k): return value
    return _f


def test_the_catalogue_tells_the_ai_to_ask_the_user():
    """The tool description is the AI's instruction sheet — it must carry the rule."""
    body = (m.serverally_list_blueprints.__doc__ or "") + (m.serverally_start_blueprint.__doc__ or "")
    assert "ASK THE USER" in body or "ask the user" in body
    assert "never invent" in body.lower()


def test_a_missing_input_is_refused_naming_it(monkeypatch):
    srv = SimpleNamespace(id="s1", name="Box", connection_type="ssh", panel_type=None)
    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1")))
    monkeypatch.setattr(m, "_executor", _ok((SimpleNamespace(server=srv), None)))

    out = asyncio.run(m.serverally_start_blueprint(
        server="Box", blueprint="set-up-website", inputs={"site_type": "php"}))
    assert out.startswith("Not started:")
    assert "domain" in out


def test_a_read_only_connection_cannot_start(monkeypatch):
    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1")))
    monkeypatch.setattr(m, "_executor", _ok((None, "This connection is read-only.")))

    out = asyncio.run(m.serverally_start_blueprint(
        server="Box", blueprint="set-up-website",
        inputs={"domain": "a.com", "site_type": "php"}))
        # The what's-new footer rides every tool for a week after a deploy, so an
        # exact-equality assertion no longer holds. The property that matters is
        # unchanged and is what is asserted: the REFUSAL leads, intact — a customer
        # must not have to read past an announcement to learn they were refused.
    assert out.split("\n\n")[0] == "This connection is read-only."


def test_a_panel_server_is_refused_before_any_row_exists(monkeypatch):
    srv = SimpleNamespace(id="s1", name="Panel", connection_type="ssh", panel_type="cyberpanel")
    added = []

    class _S(_Session):
        def add(self, row): added.append(row)
        async def commit(self): pass

    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _S())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1")))
    monkeypatch.setattr(m, "_executor", _ok((SimpleNamespace(server=srv), None)))

    out = asyncio.run(m.serverally_start_blueprint(
        server="Panel", blueprint="set-up-website",
        inputs={"domain": "a.com", "site_type": "php"}))
    assert "cyberpanel" in out
    assert not added, "a refusal must not leave a run row behind"


def test_a_malformed_run_id_is_no_such_run_not_a_crash(monkeypatch):
    class _S(_Session):
        async def get(self, model, rid): raise ValueError("badly formed UUID")

    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _S())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1")))
    out = asyncio.run(m.serverally_get_blueprint_run(run_id="not-a-uuid"))
    assert "No blueprint run" in out


def test_another_users_run_is_invisible(monkeypatch):
    run = SimpleNamespace(id="r1", user_id="somebody-else", server_id="s1")

    class _S(_Session):
        async def get(self, model, rid): return run

    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _S())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1")))
    for fn in (m.serverally_get_blueprint_run, m.serverally_stop_blueprint):
        out = asyncio.run(fn(run_id="r1"))
        assert "No blueprint run" in out, fn.__name__


def test_stop_needs_the_permission_that_started_it(monkeypatch):
    run = SimpleNamespace(id="r1", user_id="u1", server_id="s1", status="running")

    class _S(_Session):
        async def get(self, model, rid): return run

    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _S())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1")))
    monkeypatch.setattr(m, "_executor", _ok((None, "This connection is read-only.")))
    out = asyncio.run(m.serverally_stop_blueprint(run_id="r1"))
        # The what's-new footer rides every tool for a week after a deploy, so an
        # exact-equality assertion no longer holds. The property that matters is
        # unchanged and is what is asserted: the REFUSAL leads, intact — a customer
        # must not have to read past an announcement to learn they were refused.
    assert out.split("\n\n")[0] == "This connection is read-only."
    assert run.status == "running", "a refused stop must change nothing"


def test_the_waiting_state_is_explained_to_the_ai():
    """An AI that reads 'waiting' as a failure will retry or apologise — the tool's own
    text must teach it."""
    doc = m.serverally_get_blueprint_run.__doc__ or ""
    assert "NOT a failure" in doc


def test_a_job_that_needs_nothing_says_so_rather_than_showing_a_blank():
    """Needing nothing is the selling point of the take-over job — access IS the input.
    An empty "Needs:" reads as a missing field, which says the opposite."""
    import asyncio as _a

    out = _a.run(m.serverally_list_blueprints())
    assert "**Needs**: \n" not in out and not out.rstrip().endswith("**Needs**:")
    assert "nothing — just a server ServerAlly can already reach" in out
