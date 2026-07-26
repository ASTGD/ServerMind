"""The escalation state machine — when to reach whom, and when to stop.

This module is **pure**: no database, no clock of its own, no sending. Everything it
decides is a function of the state it is handed. That matters because the thing most worth
proving about an escalation engine is a property about *all* possible states —
``escalation always terminates`` — and you can only prove that about a function you can
drive forward yourself, thousands of times, without a database or a real minute passing.

The ladder a person means when they describe on-call:

    right away    → email me
    after 5 min   → text me
    after 15 min  → text my colleague
    then          → keep nudging every 15 min, at most 3 more times

``after_minutes`` counts from when the incident **started**, not from the previous step,
because that is what "text me 5 minutes in" means to the person writing it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# Worst first. A policy's `min_severity` admits everything at or above its own rank.
_SEVERITY_RANK = {"critical": 0, "high": 1, "warning": 2, "info": 3}

# Hard ceilings. These are not configuration — they are the outer bound on how much noise
# any policy can ever produce, whatever a user types into the form.
MAX_STEPS = 10
MAX_REPEATS_CEILING = 10
MIN_REPEAT_MINUTES = 1


@dataclass(frozen=True)
class Step:
    """One rung. Mirrors the EscalationStep row but stays independent of the ORM so the
    state machine can be exercised without touching a database."""

    after_minutes: int
    channel: str
    target: str
    label: str | None = None


@dataclass(frozen=True)
class Decision:
    """What the worker should do with one incident, right now.

    ``next_at is None`` means escalation is finished for this incident — the worker will
    never look at it again. That is the terminal state the guarantee is about.
    """

    fire: Step | None
    next_at: datetime | None
    step_index: int
    repeats_done: int

    @property
    def finished(self) -> bool:
        return self.next_at is None


def severity_allows(min_severity: str, severity: str) -> bool:
    """Does a policy with ``min_severity`` escalate something of ``severity``?

    Unknown values are treated as the *lowest* severity, so a typo can never cause paging
    that the user did not ask for — the safe direction for a feature that wakes people up.
    """
    want = _SEVERITY_RANK.get((min_severity or "").lower(), _SEVERITY_RANK["high"])
    got = _SEVERITY_RANK.get((severity or "").lower(), len(_SEVERITY_RANK))
    return got <= want


def ordered_steps(steps: list[Step]) -> list[Step]:
    """Steps in the order they actually fire, capped at ``MAX_STEPS``.

    Sorting by ``after_minutes`` rather than trusting the stored order means a policy edited
    into a nonsensical sequence (10 min, then 2 min) still escalates monotonically instead
    of firing the whole ladder at once.
    """
    return sorted(steps, key=lambda s: s.after_minutes)[:MAX_STEPS]


def first_action_at(steps: list[Step], created_at: datetime) -> datetime | None:
    """When the very first notification is due. None when the policy has no steps."""
    ladder = ordered_steps(steps)
    if not ladder:
        return None
    return created_at + timedelta(minutes=max(0, ladder[0].after_minutes))


def decide(
    steps: list[Step],
    created_at: datetime,
    now: datetime,
    step_index: int = 0,
    repeats_done: int = 0,
    repeat_minutes: int = 15,
    max_repeats: int = 3,
    last_notified_at: datetime | None = None,
) -> Decision:
    """Decide what to do with an unacknowledged incident at ``now``.

    Called only for incidents that are still open — acknowledging or resolving removes an
    incident from the worker's query entirely, which is *why* those two actions stop paging
    immediately rather than at the next tick.
    """
    ladder = ordered_steps(steps)
    if not ladder:
        return Decision(fire=None, next_at=None, step_index=step_index, repeats_done=repeats_done)

    # The nudge budget is clamped ONCE, here. Everything downstream takes the clamped value,
    # so there is exactly one place that decides how much noise a policy may make. (An
    # earlier version clamped again inside the scheduling helper; mutation testing showed
    # that second clamp could never bind, which made it read as a safety net it wasn't.)
    allowed = min(max(0, max_repeats), MAX_REPEATS_CEILING)
    gap = timedelta(minutes=max(MIN_REPEAT_MINUTES, repeat_minutes))

    def nudge_at(done: int) -> datetime | None:
        """When the next nudge is due, or None once the budget is spent."""
        return now + gap if done < allowed else None

    # Still climbing the ladder.
    if step_index < len(ladder):
        due = created_at + timedelta(minutes=max(0, ladder[step_index].after_minutes))
        if now < due:
            return Decision(fire=None, next_at=due, step_index=step_index, repeats_done=repeats_done)

        fired = ladder[step_index]
        nxt = step_index + 1
        if nxt < len(ladder):
            following = created_at + timedelta(minutes=max(0, ladder[nxt].after_minutes))
            # A step whose time has already passed is due immediately, not skipped — a
            # worker that was down for an hour must still climb, not jump to the top.
            return Decision(fire=fired, next_at=max(following, now), step_index=nxt,
                            repeats_done=repeats_done)
        return Decision(fire=fired, next_at=nudge_at(repeats_done),
                        step_index=nxt, repeats_done=repeats_done)

    # Ladder exhausted — the bounded nudge phase.
    if repeats_done >= allowed:
        # Terminal. Nobody answered; we stop rather than page forever.
        return Decision(fire=None, next_at=None, step_index=step_index, repeats_done=repeats_done)

    due = (last_notified_at or created_at) + gap
    if now < due:
        return Decision(fire=None, next_at=due, step_index=step_index, repeats_done=repeats_done)

    done = repeats_done + 1
    return Decision(
        fire=ladder[-1],                       # keep nudging the last person told
        next_at=nudge_at(done),
        step_index=step_index, repeats_done=done,
    )


def total_notifications(steps: list[Step], max_repeats: int) -> int:
    """The most notifications one incident can ever produce.

    Exposed so the UI can tell the user the truth up front ("at most 6 messages") and so a
    test can assert the simulated run matches the promise.
    """
    ladder = ordered_steps(steps)
    if not ladder:
        return 0
    return len(ladder) + min(max(0, max_repeats), MAX_REPEATS_CEILING)


def describe(steps: list[Step], repeat_minutes: int, max_repeats: int) -> list[str]:
    """The policy in plain sentences, for the UI and for the incident email.

    A person needs to be able to read their own on-call ladder back and believe it — an
    escalation policy you cannot picture is one you will not trust at 3am.
    """
    ladder = ordered_steps(steps)
    if not ladder:
        return ["This policy has no steps yet, so nothing will be sent."]

    lines: list[str] = []
    for step in ladder:
        who = step.label or step.target
        when = "Right away" if step.after_minutes <= 0 else f"After {_minutes(step.after_minutes)}"
        lines.append(f"{when} — {_channel_verb(step.channel)} {who}")

    allowed = min(max(0, max_repeats), MAX_REPEATS_CEILING)
    if allowed:
        last = ladder[-1].label or ladder[-1].target
        lines.append(
            f"Then every {_minutes(repeat_minutes)}, up to {allowed} more time"
            f"{'s' if allowed != 1 else ''} — {_channel_verb(ladder[-1].channel)} {last}"
        )
    lines.append("Acknowledging stops all of it.")
    return lines


def _minutes(n: int) -> str:
    n = max(0, int(n))
    if n < 60:
        return f"{n} minute{'s' if n != 1 else ''}"
    hours, rest = divmod(n, 60)
    if not rest:
        return f"{hours} hour{'s' if hours != 1 else ''}"
    return f"{hours}h {rest}m"


def _channel_verb(channel: str) -> str:
    return {
        "email": "email", "sms": "text", "telegram": "message on Telegram",
        "slack": "post to Slack", "webhook": "call the webhook for",
    }.get(channel, f"notify via {channel}:")


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)
