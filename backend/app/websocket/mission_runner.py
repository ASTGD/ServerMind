"""Detached mission runner (Ally Missions Phase 4) — a mission that outlives the socket.

Phase 3 made a mission durable (persisted + resumable). Phase 4 makes it **detached**:
the mission loop runs as a background ``asyncio.Task`` in the process, NOT tied to the
WebSocket that started it. A client connects to it through a *bridge* — it subscribes
to the runner's event stream and forwards approvals/stops. If the client goes away, the
bridge ends but the task **keeps running**; the client can re-attach later and catch up.

In-process by design (single-process deployments — the common case). Horizontal
scaling would put the fan-out on Redis pub/sub; a backend restart is covered by
Phase 3's ``recover_orphaned`` (any 'running' mission → resumable). Kept deliberately
small and testable: the mission loop talks to a ``MissionRunner``, never to a socket.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Sentinel a finished mission puts on every subscriber queue so a bridge's event pump
# knows to stop (distinct from any real event).
ENDED = {"_ended": True}

# How long a mission waits at an approval step for a decision before giving up. A
# detached mission that nobody returns to approve shouldn't hold resources forever.
APPROVAL_TIMEOUT_S = 1800  # 30 min


class MissionRunner:
    """One in-flight mission, decoupled from any client. The mission loop calls
    ``emit`` to stream events and ``wait_decision`` at an approval pause; a bridge
    (per attached client) reads the events and feeds decisions back."""

    def __init__(self) -> None:
        self.mission_id: str | None = None
        self.task: asyncio.Task | None = None
        self.subscribers: set[asyncio.Queue] = set()
        self._decision: asyncio.Future | None = None
        self._stop = False
        self.done = False
        # The approval-request event a mission is currently paused on (so a client that
        # ATTACHES mid-approval can be re-shown the prompt and actually approve).
        self.pending_approval: dict | None = None

    # ── event fan-out (mission → attached clients) ────────────────────────────
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def emit(self, event: dict) -> None:
        """Fan an event out to every attached client. Non-blocking: a slow/absent
        client just misses the live event and catches up from the DB transcript on
        re-attach — the mission never blocks on a client."""
        for q in list(self.subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover — client too slow; DB has truth
                pass

    async def send_text(self, raw: str) -> None:
        """WebSocket-compatible shim so the mission loop can stay written against a
        ``.send_text(json)`` sink — here it just fans the event out to clients. This is
        what lets ``_run_mission`` be handed a runner in place of a socket unchanged.

        Every event is tagged with this runner's ``mission_id`` (one place, covers every
        emit site in the loop) so a client showing SEVERAL concurrent missions can route
        each event to the right card."""
        import json
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):  # pragma: no cover — we always send valid json
            return
        if self.mission_id and isinstance(event, dict):
            event.setdefault("mission_id", self.mission_id)
        self.emit(event)

    def _broadcast_ended(self) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(ENDED)
            except asyncio.QueueFull:  # pragma: no cover
                pass

    # ── approvals (client → mission) ──────────────────────────────────────────
    async def wait_decision(self, timeout: float = APPROVAL_TIMEOUT_S) -> dict | None:
        """Block the mission at an approval step until a client provides a decision
        (approve / stop / other), or ``timeout`` elapses (→ None)."""
        self._decision = asyncio.get_event_loop().create_future()
        try:
            if self._stop:  # a stop that arrived before we started waiting
                return {"type": "mission_stop"}
            return await asyncio.wait_for(self._decision, timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self._decision = None

    def provide_decision(self, msg: dict) -> bool:
        """A bridge feeds a client's decision to a mission waiting at an approval step.
        Returns False if the mission isn't currently waiting."""
        if self._decision is not None and not self._decision.done():
            self._decision.set_result(msg)
            return True
        return False

    @property
    def awaiting_decision(self) -> bool:
        return self._decision is not None and not self._decision.done()

    # ── stop ──────────────────────────────────────────────────────────────────
    def request_stop(self) -> None:
        self._stop = True
        if self._decision is not None and not self._decision.done():
            self._decision.set_result({"type": "mission_stop"})

    @property
    def stop_requested(self) -> bool:
        return self._stop

    def finish(self) -> None:
        """Called when the mission task ends — wake any pump and drop from the registry."""
        self.done = True
        self._broadcast_ended()
        if self.mission_id:
            _RUNNERS.pop(self.mission_id, None)


# ── process-wide registry ─────────────────────────────────────────────────────
_RUNNERS: dict[str, MissionRunner] = {}


def create() -> MissionRunner:
    """A runner with no id yet (the mission row is created inside the task); it
    registers itself once the id is known via ``register``."""
    return MissionRunner()


def register(runner: MissionRunner, mission_id: str) -> None:
    runner.mission_id = str(mission_id)
    _RUNNERS[str(mission_id)] = runner


def get(mission_id: str) -> MissionRunner | None:
    return _RUNNERS.get(str(mission_id))


def is_running(mission_id: str) -> bool:
    r = _RUNNERS.get(str(mission_id))
    return r is not None and not r.done


def running_ids() -> list[str]:
    return [mid for mid, r in _RUNNERS.items() if not r.done]
