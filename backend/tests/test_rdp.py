"""RDP as a first-class asset — connect by IP + user + password on port 3389.

RDP has no command channel, so "connected" means the Remote Desktop port is reachable
(a bounded TCP connect). These lock the availability rules, the category inference, the
reachability check, and that the connection manager routes 'rdp' to the reachability probe.
"""
from __future__ import annotations

import types

import pytest

from app.routers.servers import infer_category
from app.services import connection_manager, rdp_service


def _srv(**kw):
    s = types.SimpleNamespace(host="10.0.0.9", port=3389)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_ensure_available_allows_rdp_asset_without_the_winrm_optin():
    # A pure-RDP asset IS the desktop — no rdp_enabled gate.
    rdp_service.ensure_available(_srv(connection_type="rdp", rdp_enabled=False))
    # A WinRM box still must opt in.
    rdp_service.ensure_available(_srv(connection_type="winrm", rdp_enabled=True))


def test_ensure_available_rejects_non_windows_and_disabled_winrm():
    with pytest.raises(rdp_service.RdpError):
        rdp_service.ensure_available(_srv(connection_type="ssh", rdp_enabled=True))
    with pytest.raises(rdp_service.RdpError):
        rdp_service.ensure_available(_srv(connection_type="winrm", rdp_enabled=False))


def test_infer_category_maps_rdp_to_windows_rdp():
    assert infer_category("rdp", None) == "windows_rdp"
    assert infer_category("winrm", None) == "windows"


async def test_reachability_closed_port_is_a_clear_failure():
    r = await rdp_service.test_connection("127.0.0.1", 1)  # nothing listening → refused fast
    assert r["ok"] is False
    assert "Remote Desktop" in r["error"]
    assert "latency_ms" in r


async def test_connection_manager_routes_rdp_to_reachability(monkeypatch):
    called = {}

    async def fake_reach(host, port):
        called["args"] = (host, port)
        return {"ok": True, "latency_ms": 5}

    monkeypatch.setattr(rdp_service, "test_connection", fake_reach)
    result = await connection_manager.test_connection(
        _srv(connection_type="rdp", host="1.2.3.4", port=3389)
    )
    assert result.ok is True
    assert called["args"] == ("1.2.3.4", 3389)  # not a WinRM handshake
