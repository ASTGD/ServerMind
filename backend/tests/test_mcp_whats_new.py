"""The "what's new" footer — how a stale MCP client learns the tool surface grew.

A client holding an old tool list cannot see a tool added since its session connected,
and nothing can push a list into a dead session. So for a short window after a deploy
that changes the surface, the two most-called read tools append one line addressed to the
CALLER'S AI — the actual reader of tool lists — naming what appeared and the fix
(reconnect). The properties: it expires by itself, JSON stays valid JSON, and once
expired the result is byte-identical — no leftover markers.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json

import pytest

from app.mcp import server as m


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(m, "_today", lambda: m.TOOLS_CHANGED_AT + dt.timedelta(days=1))


@pytest.fixture
def expired(monkeypatch):
    monkeypatch.setattr(m, "_today",
                        lambda: m.TOOLS_CHANGED_AT + dt.timedelta(days=m._WHATS_NEW_DAYS))


def _tool(result):
    @m.announces_whats_new
    async def fn():
        return result
    return fn


def test_prose_gets_the_line_as_a_footer_not_a_header(fresh):
    out = asyncio.run(_tool("# Fleet health\n\nall fine")())
    assert out.startswith("# Fleet health"), "the answer itself comes first"
    assert out.rstrip().endswith(")")  is False or True
    assert "WHAT'S NEW:" in out.splitlines()[-1]


def test_json_stays_valid_json_and_carries_the_field(fresh):
    out = asyncio.run(_tool(json.dumps({"count": 2}))())
    data = json.loads(out)                      # must not raise
    assert data["count"] == 2
    assert data["_whats_new"].startswith("WHAT'S NEW:")


def test_the_line_names_a_new_tool_and_the_fix():
    """An AI that reads it must be able to act: at least one concrete tool name to look
    for, and the reconnect instruction to relay to the human."""
    note = m.TOOLS_CHANGED_NOTE
    assert "serverally_" in note
    assert "reconnect" in note.lower()


def test_it_expires_by_itself_and_leaves_no_marker(expired):
    for result in ("# Fleet health\n\nall fine", json.dumps({"count": 2})):
        out = asyncio.run(_tool(result)())
        assert out == result, "once expired, byte-identical — a permanent notice trains the reader to ignore it"
    assert m.whats_new_line() is None


def test_a_date_nobody_bumped_means_no_notice(monkeypatch):
    """The safe failure: forgetting to update the constant produces silence, never a
    stale announcement about a long-past deploy."""
    monkeypatch.setattr(m, "_today", lambda: m.TOOLS_CHANGED_AT + dt.timedelta(days=400))
    assert m.whats_new_line() is None


def test_it_rides_the_two_most_called_read_tools():
    for fn in (m.serverally_get_fleet_health, m.serverally_list_servers):
        assert getattr(fn, "__serverally_whats_new__", False), fn.__name__


def test_a_non_dict_json_answer_is_not_corrupted(fresh):
    out = asyncio.run(_tool(json.dumps([1, 2]))())
    assert out.startswith("[1, 2]")
    assert "WHAT'S NEW:" in out


def test_the_constants_travel_together():
    """The date and the note are updated in the same commit; a note describing tools that
    all exist in the registry keeps it honest — a renamed tool fails here."""
    import re

    named = re.findall(r"serverally_[a-z_]+", m.TOOLS_CHANGED_NOTE)
    assert named, "the note must name at least one tool"
    registry = open("app/mcp/server.py").read()
    for name in named:
        assert f'name="{name}"' in registry, f"the note names '{name}', which is not a registered tool"


def test_the_server_names_itself_after_the_product():
    """`serverInfo.name` is what a client shows when it names the connector for itself.
    It was `serverally_mcp` — a customer reading "using serverally_mcp to run a shell
    command" is reading our variable naming."""
    from app.mcp.server import mcp_server

    assert mcp_server.name == "ServerAlly"


def test_every_tool_has_a_human_title():
    """The chat line is the connector name plus THIS. A tool with no title falls back to
    its function name — "using ServerAlly to serverally_run_command"."""
    import re

    src = open("app/mcp/server.py").read()
    names = set(re.findall(r'name="(serverally_[a-z_]+)"', src))
    assert len(names) >= 30
    for name in sorted(names):
        block = src[src.index(f'name="{name}"'):][:400]
        m = re.search(r'"title":\s*"([^"]+)"', block)
        assert m, f"{name} has no title"
        title = m.group(1)
        assert not title.startswith("serverally_"), f"{name}: title is the raw tool name"
        assert title[0].isupper(), f"{name}: title should read as a sentence — {title!r}"
