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
    # How ServerAlly reaches the server this run works on — so the self-lockout guard
    # can run here too. The engine already refuses a blocked command before the
    # approval gate, so this is belt to that brace rather than the only strap.
    access: object | None = None
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
        risk = (step.get("risk_level") or "low").lower()
        # Compute the safety verdict OURSELVES rather than inferring it from
        # ``needs_approval``. The engine sets that flag for several different reasons, so
        # treating it as "confirm" made every step look dangerous and collapsed
        # safe_fixes into report_only. CONFIRM_PATTERNS is OS-agnostic, and 'blocked'
        # never reaches this point, so checking against linux is complete here.
        safety_status = safety_service.validate_command(cmd, "linux", self.access).status
        # The engine tells us explicitly whether the AI itself flagged the step. We must
        # NOT infer this from ``needs_approval``: autopilot forces careful mode, so that
        # flag is true for every change and would stop even an ordinary repair.
        flagged = bool(step.get("ai_flagged"))
        verdict = decide(
            policy=self.policy,
            risk_level=risk,
            safety_status=safety_status,
            is_read_only=safety_service.is_read_only_command(cmd),
            flagged_by_ai=flagged,
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

    from app.services import safety_service as _safety
    runner = AutopilotRunner(policy=task.policy, access=_safety.access_for(server))
    try:
        await ws_terminal._run_mission_detached(
            runner,
            user,
            home_server=server,
            goal=task.goal,
            skill_slug=None,  # let the router match a runbook from the goal, as in chat
            user_language=getattr(user, "preferred_language", None) or "en",
            # Force the strictest approval floor so EVERY mutating step reaches the
            # policy. Without this, steps the engine considers ordinary (`systemctl
            # restart nginx`, even `rm -f /tmp/x`) would run without consulting it, and a
            # "look and tell me" task could still change the server.
            ally_mode_override="careful",
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


# ── Scheduling (APScheduler, shared with scheduler_service) ──────────────────
# Mirrors backup_service: one cron job per task, namespaced job ids, reloaded on startup.

def _job_id(task_id) -> str:
    return f"autopilot:{task_id}"


def schedule_task(task) -> None:
    """Register (or replace) the cron job for an active task."""
    from app.services import scheduler_service

    if not (task.is_active and task.cron_expression):
        unschedule_task(task.id)
        return
    try:
        from apscheduler.triggers.cron import CronTrigger

        scheduler_service.get_scheduler().add_job(
            _execute_task,
            trigger=CronTrigger.from_crontab(task.cron_expression, timezone="UTC"),
            args=[str(task.id)],
            id=_job_id(task.id),
            replace_existing=True,
            max_instances=1,  # a long mission must never overlap its own next run
        )
        logger.debug("Scheduled autopilot %s (%s)", task.name, task.cron_expression)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not schedule autopilot %s: %s", task.id, exc)


def unschedule_task(task_id) -> None:
    from app.services import scheduler_service

    try:
        scheduler_service.get_scheduler().remove_job(_job_id(task_id))
    except Exception:  # noqa: BLE001 — not scheduled is fine
        pass


async def load_all_tasks() -> None:
    """Re-register every active task on startup."""
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.autopilot import AutopilotTask

    try:
        async with AsyncSessionLocal() as db:
            tasks = (await db.execute(
                select(AutopilotTask).where(AutopilotTask.is_active.is_(True))
            )).scalars().all()
        for task in tasks:
            schedule_task(task)
        if tasks:
            logger.info("Autopilot: %d scheduled task(s) loaded", len(tasks))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load autopilot tasks: %s", exc)


async def _execute_task(task_id: str) -> None:
    """The scheduled job: load the task, run the mission, record and report."""
    from datetime import datetime, timezone as _tz

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.autopilot import AutopilotTask
    from app.models.server import Server
    from app.models.user import User
    from app.services import notification_service, scheduler_service

    async with AsyncSessionLocal() as db:
        task = (await db.execute(
            select(AutopilotTask).where(AutopilotTask.id == task_id)
        )).scalar_one_or_none()
        if task is None or not task.is_active:
            return
        user = (await db.execute(select(User).where(User.id == task.user_id))).scalar_one_or_none()
        server = None
        if task.server_id:
            server = (await db.execute(
                select(Server).where(Server.id == task.server_id)
            )).scalar_one_or_none()
        if user is None:
            logger.warning("Autopilot task %s has no user; skipping", task_id)
            return
        # Snapshot what we need — the session closes while the mission runs.
        name, policy, channel, target = task.name, task.policy, task.channel, task.channel_target
        notify_changes_only, cron = task.notify_on_change_only, task.cron_expression

    logger.info("Autopilot: running '%s'", name)
    result = await run_task_mission(task, user, server)

    async with AsyncSessionLocal() as db:
        task = (await db.execute(
            select(AutopilotTask).where(AutopilotTask.id == task_id)
        )).scalar_one_or_none()
        if task is not None:
            task.last_run = datetime.now(tz=_tz.utc)
            task.last_status = result.get("status")
            try:
                task.next_run = scheduler_service.compute_next_run(cron)
            except Exception:  # noqa: BLE001
                task.next_run = None
            await db.commit()

    if should_notify(result, _Notifiable(name, policy, channel, target, notify_changes_only)):
        subject, body = summarise(result, _Notifiable(name, policy, channel, target, notify_changes_only))
        try:
            if channel == "email":
                await notification_service.send_email(target, subject, body)
            else:
                await notification_service.send_webhook(
                    target, {"text": f"{subject}\n{body}", "task": name, "status": result.get("status")}
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Autopilot report for %s could not be sent: %s", task_id, exc)


@dataclass
class _Notifiable:
    """The few task fields the report helpers need, detached from the DB session."""

    name: str
    policy: str
    channel: str | None
    channel_target: str | None
    notify_on_change_only: bool
