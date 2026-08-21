"""The MCP write tools, driven rather than read.

Four of these tools assumed a control panel. `list_sites`, `create_site` and `issue_ssl`
each answered some form of "Unsupported or missing panel_type: (none)" on an ordinary
Linux server — the common case — and `create_database` was the fourth. A control panel is
one way to have a database on a server, not the only one.

These call the tools. Grepping the source for `database_service` would pass while the
call itself had the wrong arguments, which is exactly how the `create_site` fault shipped.
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


@pytest.fixture
def wired(monkeypatch):
    """A caller who owns one ordinary SSH server, with the gate satisfied."""
    srv = SimpleNamespace(id="s1", name="TestServerNew", connection_type="ssh",
                          panel_type=None, os_type="ubuntu")
    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1")))
    monkeypatch.setattr(m, "_executor", _ok((SimpleNamespace(server=srv, can_execute=True), None)))
    monkeypatch.setattr(m, "_audit", _ok(None))
    return srv


PASSWORD = "s3cr3t-never-echo-me"


def _stub_engine(monkeypatch, seen):
    from app.services import database_service as dbs

    async def create(server, *, engine, db_name, user, password, host="localhost"):
        seen.update(server=server.name, engine=engine, db=db_name, user=user,
                    password=password, host=host)
        return {"name": db_name, "user": user, "host": host}

    monkeypatch.setattr(dbs, "create_database", create)


def test_a_database_is_created_on_a_server_with_no_control_panel(wired, monkeypatch):
    seen: dict = {}
    _stub_engine(monkeypatch, seen)

    out = asyncio.run(m.serverally_create_database(
        server="TestServerNew", db_name="shop", db_user="shop_user", db_password=PASSWORD))

    assert "panel" not in out.lower(), out
    assert seen["db"] == "shop" and seen["user"] == "shop_user"
    assert seen["password"] == PASSWORD          # it reaches the engine…
    assert "shop" in out


@pytest.mark.parametrize("fmt", [m.ResponseFormat.MARKDOWN, m.ResponseFormat.JSON])
def test_the_password_never_comes_back(wired, monkeypatch, fmt):
    """…and it never comes back out. The caller supplied it and keeps their own copy;
    anything we return can end up in a transcript, a log, or somebody's chat history."""
    _stub_engine(monkeypatch, {})

    out = asyncio.run(m.serverally_create_database(
        server="TestServerNew", db_name="shop", db_user="shop_user",
        db_password=PASSWORD, response_format=fmt))

    assert PASSWORD not in out
    if fmt is m.ResponseFormat.JSON:
        assert PASSWORD not in json.dumps(json.loads(out))


def test_the_account_is_named_but_the_password_is_not_audited(wired, monkeypatch):
    """The audit trail records THAT a database was made, never how to get into it."""
    calls: list = []
    _stub_engine(monkeypatch, {})

    async def audit(db, user, action, target, *a, **k):
        calls.append((action, json.dumps(k, default=str)))

    monkeypatch.setattr(m, "_audit", audit)
    asyncio.run(m.serverally_create_database(
        server="TestServerNew", db_name="shop", db_user="shop_user", db_password=PASSWORD))

    assert calls and calls[0][0] == "create_database"
    assert PASSWORD not in calls[0][1]


def test_a_windows_server_is_refused_rather_than_attempted(monkeypatch):
    srv = SimpleNamespace(id="s2", name="WinBox", connection_type="winrm", panel_type=None)
    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1")))
    monkeypatch.setattr(m, "_executor", _ok((SimpleNamespace(server=srv, can_execute=True), None)))

    out = asyncio.run(m.serverally_create_database(
        server="WinBox", db_name="shop", db_user="u", db_password=PASSWORD))
    assert "winrm" in out and "SSH" in out


def test_creating_a_database_needs_execute_permission(monkeypatch):
    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1")))
    monkeypatch.setattr(m, "_executor", _ok((None, "This connection is read-only.")))

    out = asyncio.run(m.serverally_create_database(
        server="box", db_name="shop", db_user="u", db_password=PASSWORD))
        # The what's-new footer rides every tool for a week after a deploy, so an
        # exact-equality assertion no longer holds. The property that matters is
        # unchanged and is what is asserted: the REFUSAL leads, intact — a customer
        # must not have to read past an announcement to learn they were refused.
    assert out.split("\n\n")[0] == "This connection is read-only."
    assert PASSWORD not in out
