"""Detached mission runner + bridge (Ally Missions Phase 4).

Covers the concurrency that lets a mission outlive its client: the runner's event
fan-out + approval/stop signalling, and the bridge that forwards events to a socket
and routes approve/stop back — plus the three ways a bridge ends (mission finished /
client sent something else / socket dropped) with the mission always kept running.
No API, no DB.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import WebSocketDisconnect

from app.websocket import mission_runner
from app.websocket.terminal import _bridge_mission


# ── Runner ────────────────────────────────────────────────────────────────────

async def test_emit_fans_out_to_all_subscribers():
    r = mission_runner.create()
    a, b = r.subscribe(), r.subscribe()
    r.emit({"n": 1})
    assert (await a.get()) == {"n": 1}
    assert (await b.get()) == {"n": 1}
    r.unsubscribe(a)
    r.emit({"n": 2})
    assert b.get_nowait() == {"n": 2}
    assert a.empty()  # unsubscribed → no more events


async def test_wait_decision_times_out_to_none():
    r = mission_runner.create()
    assert await r.wait_decision(timeout=0.05) is None


async def test_provide_decision_wakes_the_waiter():
    r = mission_runner.create()
    fut = asyncio.ensure_future(r.wait_decision(timeout=2))
    await asyncio.sleep(0.01)
    assert r.awaiting_decision is True
    assert r.provide_decision({"type": "approve"}) is True
    assert await asyncio.wait_for(fut, 1) == {"type": "approve"}
    # No waiter now → provide returns False.
    assert r.provide_decision({"type": "approve"}) is False


async def test_request_stop_sets_flag_and_wakes_approval():
    r = mission_runner.create()
    fut = asyncio.ensure_future(r.wait_decision(timeout=2))
    await asyncio.sleep(0.01)
    r.request_stop()
    assert r.stop_requested is True
    assert (await asyncio.wait_for(fut, 1)).get("type") == "mission_stop"


async def test_pending_approval_is_remembered_for_reattach():
    """A mission paused at an approval remembers the prompt so a client that ATTACHES
    mid-approval can be re-shown it and actually approve."""
    r = mission_runner.create()
    assert r.pending_approval is None
    fut = asyncio.ensure_future(r.wait_decision(timeout=2))
    await asyncio.sleep(0.01)
    r.pending_approval = {"type": "mission_step", "needs_approval": True, "index": 5}
    # An attaching client would re-emit this because we're awaiting a decision.
    assert r.awaiting_decision and r.pending_approval["needs_approval"] is True
    r.provide_decision({"type": "approve"})
    await asyncio.wait_for(fut, 1)


async def test_registry_and_finish_deregisters():
    r = mission_runner.create()
    mission_runner.register(r, "m-1")
    assert mission_runner.get("m-1") is r
    assert mission_runner.is_running("m-1") is True
    assert "m-1" in mission_runner.running_ids()
    r.finish()
    assert r.done is True
    assert mission_runner.get("m-1") is None  # dropped from the registry


async def test_send_text_shim_emits_parsed_event():
    r = mission_runner.create()
    q = r.subscribe()
    await r.send_text(json.dumps({"type": "mission_step", "i": 3}))
    assert q.get_nowait() == {"type": "mission_step", "i": 3}


# ── Bridge ────────────────────────────────────────────────────────────────────

class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self._incoming: asyncio.Queue = asyncio.Queue()

    async def send_text(self, raw: str) -> None:
        self.sent.append(json.loads(raw))

    async def receive_text(self) -> str:
        item = await self._incoming.get()
        if isinstance(item, Exception):
            raise item
        return item

    def feed(self, msg: dict) -> None:
        self._incoming.put_nowait(json.dumps(msg))

    def disconnect(self) -> None:
        self._incoming.put_nowait(WebSocketDisconnect())


async def test_bridge_forwards_events_then_ends_when_mission_finishes():
    r = mission_runner.create()
    ws = _FakeWS()
    bridge = asyncio.create_task(_bridge_mission(ws, r))
    await asyncio.sleep(0.02)  # let it subscribe + start pump/reader
    r.emit({"type": "mission_step", "index": 1})
    await asyncio.sleep(0.02)
    assert {"type": "mission_step", "index": 1} in ws.sent
    r.finish()  # mission ended → pump stops → bridge returns
    assert await asyncio.wait_for(bridge, 1) is None


async def test_bridge_routes_approve_and_stop_to_runner():
    r = mission_runner.create()
    ws = _FakeWS()
    bridge = asyncio.create_task(_bridge_mission(ws, r))
    await asyncio.sleep(0.02)
    # approve reaches a waiting mission
    fut = asyncio.ensure_future(r.wait_decision(timeout=2))
    await asyncio.sleep(0.01)
    ws.feed({"type": "approve"})
    assert (await asyncio.wait_for(fut, 1)) == {"type": "approve"}
    # stop sets the flag
    ws.feed({"type": "mission_stop"})
    await asyncio.sleep(0.02)
    assert r.stop_requested is True
    r.finish()
    await asyncio.wait_for(bridge, 1)


async def test_bridge_returns_other_message_as_leftover_mission_keeps_running():
    r = mission_runner.create()
    ws = _FakeWS()
    bridge = asyncio.create_task(_bridge_mission(ws, r))
    await asyncio.sleep(0.02)
    ws.feed({"type": "message", "content": "hi"})
    leftover = await asyncio.wait_for(bridge, 1)
    assert leftover == {"type": "message", "content": "hi"}
    assert r.done is False  # the mission was NOT stopped — it runs on detached


async def test_bridge_reraises_disconnect_mission_keeps_running():
    r = mission_runner.create()
    ws = _FakeWS()
    bridge = asyncio.create_task(_bridge_mission(ws, r))
    await asyncio.sleep(0.02)
    ws.disconnect()
    with pytest.raises(WebSocketDisconnect):
        await asyncio.wait_for(bridge, 1)
    assert r.done is False  # dropping the client does NOT end the mission
