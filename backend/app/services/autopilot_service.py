"""Autopilot — run a mission on a schedule, deciding approvals by policy.

Two pieces:

1. :func:`decide` — **pure**, and the safety-critical part. Given what the engine knows at
   an approval point (risk level, the safety verdict, whether the command only reads), it
   answers *"may Ally proceed without the owner?"*.
2. :class:`AutopilotRunner` — a duck-typed stand-in for the WebSocket the mission engine
   normally talks to. It answers ``wait_decision`` from the policy instead of from a human,
   and records what happened so the owner gets a report.

**What the policy cannot do.** It is consulted *after* ``safety_service.validate_command``
has already refused blocked commands (``terminal._run_mission`` step 2 refuses and moves on
*before* the approval check in step 3). So no policy setting can authorise a catastrophic
command — the policy only ever answers "ask the human, or don't".
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.models.autopilot import (
    POLICY_FULL,
    POLICY_REPORT_ONLY,
    POLICY_SAFE_FIXES,
)

logger = logging.getLogger(__name__)


@dataclass
class Decision:
    """Whether autopilot may proceed, and — when it may not — why, in the owner's words."""

    approve: bool
    reason: str = ""


def decide(
    *,
    policy: str,
    risk_level: str | None,
    safety_status: str,
    is_read_only: bool,
    flagged_by_ai: bool = False,
) -> Decision:
    """May autopilot approve this step on the owner's behalf? Pure — no I/O.

    ``safety_status`` is ``safety_service.validate_command(...).status`` — 'ok' or
    'confirm' by the time we are called ('blocked' never reaches here).
    """
    risk = (risk_level or "low").lower()

    # These three signals mean "a careful human would want to look at this".
    # They are NEVER auto-approved below `full`, in any policy.
    dangerous = safety_status == "confirm" or risk == "high" or flagged_by_ai

    if policy == POLICY_FULL:
        # The owner has explicitly said "proceed on anything the blocklist permits".
        return Decision(True)

    if policy == POLICY_SAFE_FIXES:
        if dangerous:
            return Decision(
                False,
                "This step needed your go-ahead — it is the kind of change that can break "
                "things, so autopilot stopped instead of guessing.",
            )
        return Decision(True)

    # POLICY_REPORT_ONLY (and anything unrecognised — fail closed).
    if is_read_only:
        return Decision(True)  # looking is always fine; that is how it investigates
    return Decision(
        False,
        "Autopilot is set to look and report only, so it stopped before changing anything.",
    )


def policy_label(policy: str) -> str:
    return {
        POLICY_REPORT_ONLY: "Look and report only",
        POLICY_SAFE_FIXES: "Fix ordinary problems, ask about risky ones",
        POLICY_FULL: "Fix anything the safety rules allow",
    }.get(policy, policy)


@dataclass
class AutopilotRunner:
    """Stands in for the WebSocket the mission engine talks to.

    The engine only needs ``send_text``, ``wait_decision``, a ``stop`` flag and
    ``pending_approval``. Here, ``wait_decision`` consults the policy instead of a human,
    so a scheduled mission never hangs waiting for someone who isn't there.
    """

    policy: str
    stop: bool = False
    pending_approval: dict | None = None
    # A pinned planning model (Ally's model picker). Autopilot never pins one — None means
    # "Auto", so the Smart Model Ladder chooses per step as it does everywhere else.
    model: str | None = None
    # What happened, for the run report.
    events: list[dict] = field(default_factory=list)
    approved_steps: int = 0
    stopped_reason: str | None = None
    _last_step: dict | None = None

    async def send_text(self, raw: str) -> None:
        """Receive one engine event. We keep the shape we need and drop the rest."""
        import json

        try:
            event = json.loads(raw)
        except Exception:  # noqa: BLE001 — an unparseable event must not break the run
            return
        etype = event.get("type")
        if etype == "mission_step":
            self._last_step = event
        if etype in {
            "mission_step", "mission_step_done", "mission_complete",
            "mission_blocked", "mission_stopped", "mission_failed",
        }:
            self.events.append(event)

    async def wait_decision(self, timeout: float = 0) -> dict | None:
        """Answer an approval from the policy rather than from a person.

        Returning ``None`` makes the engine finalise the mission as *blocked* with
        "I paused for your approval but didn't hear back" — which is exactly the right
        outcome: nothing was changed, and the owner is told why.
        """
        step = self._last_step or {}
        from app.services import safety_service

        cmd = step.get("cmd") or ""
        verdict = decide(
            policy=self.policy,
            risk_level=step.get("risk_level"),
            # The engine already refused 'blocked'; a step reaching approval is
            # 'confirm' or was flagged by the AI/careful-mode.
            safety_status="confirm" if step.get("needs_approval") and cmd else "ok",
            is_read_only=safety_service.is_read_only_command(cmd),
            flagged_by_ai=bool(step.get("needs_approval")) and (step.get("risk_level") == "high"),
        )
        if verdict.approve:
            self.approved_steps += 1
            return {"type": "approve"}
        self.stopped_reason = verdict.reason
        return None

    # The engine also treats the runner as its fan-out target; these are no-ops here.
    def provide_decision(self, msg: dict) -> bool:  # pragma: no cover — no clients attach
        return False

    @property
    def stop_requested(self) -> bool:
        """The engine checks this each iteration to abort early."""
        return self.stop

    def request_stop(self) -> None:
        self.stop = True

    def finish(self) -> None:
        """``_run_mission_detached`` always calls this in its ``finally`` to unblock any
        attached bridge. No clients attach to an autopilot run, so it is a no-op — but it
        MUST exist or every scheduled run raises AttributeError at the end."""
        return None


async def run_task_mission(task, user, server) -> dict:
    """Execute one autopilot run. Returns a small summary for the report/record.

    Imported lazily: the mission engine lives in the websocket layer and importing it at
    module load would create a cycle.
    """
    from app.websocket import terminal as ws_terminal

    runner = AutopilotRunner(policy=task.policy)
    try:
        await ws_terminal._run_mission_detached(
            runner,
            user,
            home_server=server,
            goal=task.goal,
            skill_slug=None,  # let the router match a runbook from the goal, as in chat
            user_language=getattr(user, "preferred_language", None) or "en",
        )
    except Exception as exc:  # noqa: BLE001 — one bad run must not stop the scheduler
        logger.warning("Autopilot task %s failed: %s", task.id, exc)
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300],
                "approved_steps": runner.approved_steps, "events": runner.events}

    status = "completed"
    for event in reversed(runner.events):
        etype = event.get("type")
        if etype == "mission_complete":
            status = "completed"
            break
        if etype in {"mission_blocked", "mission_stopped"}:
            status = "needs_you"
            break
        if etype == "mission_failed":
            status = "failed"
            break

    return {
        "status": status,
        "approved_steps": runner.approved_steps,
        "stopped_reason": runner.stopped_reason,
        "events": runner.events,
    }


def summarise(result: dict, task) -> tuple[str, str]:
    """(subject, body) for the owner's run report — plain language, no jargon."""
    status = result.get("status")
    name = task.name
    if status == "completed":
        subject = f"✅ {name} — done"
        body = f"Autopilot ran “{name}” and finished.\n\n"
        if result.get("approved_steps"):
            body += f"It made {result['approved_steps']} change(s) within the limits you set.\n"
        else:
            body += "Nothing needed changing.\n"
    elif status == "needs_you":
        subject = f"⏸ {name} — needs your OK"
        body = (
            f"Autopilot ran “{name}” and stopped because it reached something it is not "
            f"allowed to do on its own.\n\n{result.get('stopped_reason') or ''}\n\n"
            "Nothing was changed at that step. Open ServerAlly to review and continue."
        )
    else:
        subject = f"⚠️ {name} — could not finish"
        body = (
            f"Autopilot ran “{name}” but could not finish.\n\n"
            f"{result.get('error') or 'See the mission history in ServerAlly for details.'}"
        )
    body += f"\n\nSetting: {policy_label(task.policy)}."
    return subject, body


def should_notify(result: dict, task) -> bool:
    """Quiet by default: only speak up when something happened or someone is needed."""
    if not task.channel or not task.channel_target:
        return False
    if not task.notify_on_change_only:
        return True
    return result.get("status") != "completed" or bool(result.get("approved_steps"))
