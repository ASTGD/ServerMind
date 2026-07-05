"""Detached mission runner + hub (Ally Missions Phase 4 → Pass 2 concurrency).

Covers the concurrency that lets missions outlive their client AND run several at
once: the runner's event fan-out + approval/stop signalling, the mission_id tagging
that routes events to the right workspace card, and the per-connection _MissionHub
that pumps N missions' events over one socket and routes control frames by
mission_id — scoped to hub-attached runners only (never the global registry).
No API, no DB.
"""
from __future__ import annotations

import asyncio
import json

from app.websocket import mission_runner
from app.websocket.terminal import _MissionHub


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


async def test_send_text_shim_tags_events_with_mission_id():
    """Once registered, every event the mission loop sends carries the mission's id —
    this is what lets a client route events to the right one of several cards."""
    r = mission_runner.create()
    mission_runner.register(r, "m-tag")
    q = r.subscribe()
    await r.send_text(json.dumps({"type": "mission_step", "index": 1}))
    assert q.get_nowait() == {"type": "mission_step", "index": 1, "mission_id": "m-tag"}
    # An explicit mission_id (mission_started sets its own) is never overwritten.
    await r.send_text(json.dumps({"type": "mission_started", "mission_id": "explicit"}))
    assert q.get_nowait()["mission_id"] == "explicit"
    r.finish()


# ── Hub (Pass 2 — N missions over one socket) ─────────────────────────────────

class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


async def test_hub_pumps_two_missions_concurrently():
    ws = _FakeWS()
    hub = _MissionHub(ws)
    a, b = mission_runner.create(), mission_runner.create()
    mission_runner.register(a, "m-a")
    mission_runner.register(b, "m-b")
    hub.attach(a)
    hub.attach(b)
    await a.send_text(json.dumps({"type": "mission_step", "index": 1}))
    await b.send_text(json.dumps({"type": "mission_step", "index": 1}))
    await a.send_text(json.dumps({"type": "mission_step_done", "index": 1}))
    await asyncio.sleep(0.05)
    got = {(e["mission_id"], e["type"], e.get("index")) for e in ws.sent}
    assert ("m-a", "mission_step", 1) in got
    assert ("m-b", "mission_step", 1) in got
    assert ("m-a", "mission_step_done", 1) in got
    a.finish(); b.finish()
    hub.close()


async def test_hub_routes_approve_by_mission_id_to_the_right_runner():
    """With TWO missions waiting at an approval, an approve frame must reach exactly
    the mission it names — never the other one."""
    hub = _MissionHub(_FakeWS())
    a, b = mission_runner.create(), mission_runner.create()
    mission_runner.register(a, "m-a")
    mission_runner.register(b, "m-b")
    hub.attach(a); hub.attach(b)
    fa = asyncio.ensure_future(a.wait_decision(timeout=2))
    fb = asyncio.ensure_future(b.wait_decision(timeout=0.3))
    await asyncio.sleep(0.01)
    assert hub.route({"type": "approve", "mission_id": "m-b"}) is True
    assert (await asyncio.wait_for(fb, 1)) == {"type": "approve", "mission_id": "m-b"}
    assert a.awaiting_decision is True  # untouched
    a.request_stop()
    await asyncio.wait_for(fa, 1)
    a.finish(); b.finish(); hub.close()


async def test_hub_idless_frame_only_routes_when_unambiguous():
    """An approve/stop WITHOUT mission_id (older client) routes only when exactly one
    mission is live — with two, it's ambiguous and must be dropped."""
    hub = _MissionHub(_FakeWS())
    a, b = mission_runner.create(), mission_runner.create()
    mission_runner.register(a, "m-a")
    mission_runner.register(b, "m-b")
    hub.attach(a); hub.attach(b)
    assert hub.route({"type": "mission_stop"}) is False  # two live → ambiguous
    assert a.stop_requested is False and b.stop_requested is False
    b.finish()  # now only a is live
    assert hub.route({"type": "mission_stop"}) is True
    assert a.stop_requested is True
    a.finish(); hub.close()


async def test_hub_stop_by_id_stops_only_that_mission():
    hub = _MissionHub(_FakeWS())
    a, b = mission_runner.create(), mission_runner.create()
    mission_runner.register(a, "m-a")
    mission_runner.register(b, "m-b")
    hub.attach(a); hub.attach(b)
    assert hub.route({"type": "mission_stop", "mission_id": "m-a"}) is True
    assert a.stop_requested is True and b.stop_requested is False
    a.finish(); b.finish(); hub.close()


async def test_hub_never_routes_to_unattached_runners():
    """Access scoping: a runner in the GLOBAL registry that was never attached through
    this connection's checked paths is unreachable — a guessed mission_id from another
    user's session can't approve or stop someone else's mission."""
    hub = _MissionHub(_FakeWS())
    other = mission_runner.create()
    mission_runner.register(other, "m-other")  # global registry, NOT hub-attached
    fut = asyncio.ensure_future(other.wait_decision(timeout=0.3))
    await asyncio.sleep(0.01)
    assert hub.route({"type": "approve", "mission_id": "m-other"}) is False
    assert other.awaiting_decision is True  # decision never delivered
    other.request_stop()
    await asyncio.wait_for(fut, 1)
    other.finish(); hub.close()


async def test_hub_is_control_classification():
    """mission_stop is always mission control; approve/reject/cancel only WITH a
    mission_id (or the explicit ``mission: true`` marker for id-less missions) —
    a plain id-less approve/cancel stays a plan decision."""
    assert _MissionHub.is_control({"type": "mission_stop"}) is True
    assert _MissionHub.is_control({"type": "approve", "mission_id": "m"}) is True
    assert _MissionHub.is_control({"type": "reject", "mission_id": "m"}) is True
    assert _MissionHub.is_control({"type": "cancel", "mission_id": "m"}) is True
    assert _MissionHub.is_control({"type": "approve", "mission": True}) is True
    assert _MissionHub.is_control({"type": "approve"}) is False
    assert _MissionHub.is_control({"type": "cancel"}) is False
    assert _MissionHub.is_control({"type": "message", "content": "hi"}) is False


async def test_hub_close_stops_pumping_but_missions_keep_running():
    ws = _FakeWS()
    hub = _MissionHub(ws)
    r = mission_runner.create()
    mission_runner.register(r, "m-r")
    hub.attach(r)
    hub.close()
    await asyncio.sleep(0.02)  # let the pump cancellation land
    await r.send_text(json.dumps({"type": "mission_step", "index": 9}))
    await asyncio.sleep(0.02)
    assert all(e.get("index") != 9 for e in ws.sent)  # nothing pumped after close
    assert r.done is False  # dropping the client does NOT end the mission
    assert len(r.subscribers) == 0  # pump unsubscribed on the way out
    r.finish()
