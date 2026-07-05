"""`_resolve_ask_servers` — the "which server did you mean?" candidate mapper.

Pure (no DB): the AI returns candidate NAMES; this maps them to the user's real servers
as {id, name} chips the frontend can click. Only real, reachable matches survive.
"""
from __future__ import annotations

from types import SimpleNamespace as N

from app.websocket.terminal import _resolve_ask_servers


def _srv(id, name):
    return N(id=id, name=name)


SERVERS = [_srv("1", "TestServer1"), _srv("2", "TestServer2"), _srv("web", "web-prod")]


def test_maps_names_to_id_name_chips():
    out = _resolve_ask_servers(["TestServer1", "web-prod"], SERVERS)
    assert out == [{"id": "1", "name": "TestServer1"}, {"id": "web", "name": "web-prod"}]


def test_is_case_insensitive():
    assert _resolve_ask_servers(["testserver2"], SERVERS) == [{"id": "2", "name": "TestServer2"}]


def test_drops_names_that_are_not_real_servers():
    # A hallucinated name never becomes a clickable chip.
    assert _resolve_ask_servers(["ghost-server"], SERVERS) == []


def test_dedupes_repeats():
    out = _resolve_ask_servers(["TestServer1", "TestServer1"], SERVERS)
    assert out == [{"id": "1", "name": "TestServer1"}]


def test_caps_at_six():
    many = [_srv(str(i), f"S{i}") for i in range(10)]
    out = _resolve_ask_servers([f"S{i}" for i in range(10)], many)
    assert len(out) == 6


def test_empty_or_bad_input_yields_nothing():
    assert _resolve_ask_servers(None, SERVERS) == []
    assert _resolve_ask_servers([], SERVERS) == []
    assert _resolve_ask_servers("TestServer1", SERVERS) == []  # not a list
