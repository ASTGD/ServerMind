"""The escalation state machine (docs/PRO-FEATURES-PLAN.md §4 #5).

An escalation engine has one failure mode that destroys trust in *every* alert the product
ever sends: paging that will not stop. So the headline test here is not an example — it is
a **simulation over many policy shapes**, driving the real ``decide`` forward until it
either terminates or exceeds its promised budget.

``decide`` is pure precisely so this is possible without a database or a real minute
passing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import escalation_service as esc
from app.services.escalation_service import Decision, Step, decide

T0 = datetime(2026, 7, 26, 3, 0, tzinfo=timezone.utc)  # 3am, the hour this feature is for


def ladder(*mins: int) -> list[Step]:
    return [Step(after_minutes=m, channel="sms", target=f"+8801{i}") for i, m in enumerate(mins)]


def run_to_completion(
    steps: list[Step], repeat_minutes: int = 15, max_repeats: int = 3, tick_limit: int = 5000,
) -> tuple[int, int]:
    """Drive `decide` forward as the worker would, jumping the clock to each `next_at`.

    Nobody ever acknowledges. Returns (notifications sent, ticks taken).
    Raises if it does not terminate — which is the whole point.
    """
    now, step_index, repeats, last_notified = T0, 0, 0, None
    sent = ticks = 0
    while ticks < tick_limit:
        ticks += 1
        d: Decision = decide(
            steps, T0, now, step_index=step_index, repeats_done=repeats,
            repeat_minutes=repeat_minutes, max_repeats=max_repeats,
            last_notified_at=last_notified,
        )
        if d.fire is not None:
            sent += 1
            last_notified = now
        step_index, repeats = d.step_index, d.repeats_done
        if d.finished:
            return sent, ticks
        assert d.next_at is not None
        # The worker only ever moves forward in time.
        now = max(d.next_at, now + timedelta(seconds=1))
    raise AssertionError(f"escalation did NOT terminate after {tick_limit} ticks ({sent} sent)")


# ── The guarantee ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("steps", [
    ladder(0),
    ladder(0, 5),
    ladder(0, 5, 15),
    ladder(0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    ladder(5),                       # nothing fires immediately
    ladder(0, 0, 0),                 # everything at once
    ladder(15, 5, 0),                # written out of order
    ladder(0, 60 * 24),              # a step a day later
])
@pytest.mark.parametrize("repeat_minutes,max_repeats", [
    (15, 3), (1, 0), (1, 10), (60, 1), (0, 5), (-5, -5), (15, 99),
])
def test_escalation_always_terminates(steps, repeat_minutes, max_repeats):
    """Across every policy shape — including nonsense a user could type — escalation
    reaches a terminal state and never exceeds its promised message budget."""
    sent, _ticks = run_to_completion(steps, repeat_minutes, max_repeats)
    promised = esc.total_notifications(steps, max_repeats)
    assert sent == promised, f"sent {sent}, promised {promised}"


def test_an_empty_policy_sends_nothing_rather_than_looping():
    """A policy with no steps must be inert, not a worker that wakes forever finding
    nothing to do."""
    d = decide([], T0, T0)
    assert d.fire is None and d.finished
    assert esc.total_notifications([], 3) == 0


def test_the_promise_shown_to_the_user_matches_reality():
    """The UI tells the user "at most N messages"; that number has to be true."""
    steps = ladder(0, 5, 15)
    sent, _ = run_to_completion(steps, repeat_minutes=15, max_repeats=3)
    assert sent == 6 == esc.total_notifications(steps, 3)


def test_repeats_are_capped_even_if_a_user_asks_for_a_thousand():
    assert esc.total_notifications(ladder(0), 100_000) == 1 + esc.MAX_REPEATS_CEILING


def test_a_giant_ladder_is_capped():
    assert len(esc.ordered_steps(ladder(*range(50)))) == esc.MAX_STEPS


# ── Climbing in the right order, at the right time ───────────────────────────

def test_nothing_fires_before_its_time():
    d = decide(ladder(5), T0, T0)
    assert d.fire is None
    assert d.next_at == T0 + timedelta(minutes=5)
    assert not d.finished          # still waiting, not done


def test_the_first_step_fires_when_due():
    d = decide(ladder(0, 5), T0, T0)
    assert d.fire is not None and d.step_index == 1
    assert d.next_at == T0 + timedelta(minutes=5)


def test_steps_climb_one_at_a_time_after_an_outage_of_our_own():
    """If our worker was down for an hour, a 3-step ladder must still deliver all three
    notifications rather than silently skipping to the top — the user is owed the messages
    they configured, and step 1 may be the only channel that reaches them."""
    steps = ladder(0, 5, 15)
    late = T0 + timedelta(hours=1)
    idx, fired = 0, 0
    for _ in range(3):
        d = decide(steps, T0, late, step_index=idx)
        assert d.fire is not None, "a due step was skipped"
        fired += 1
        idx = d.step_index
    assert fired == 3


def test_steps_written_out_of_order_still_escalate_gradually():
    """A policy edited into 15/5/0 must not fire everything at once."""
    steps = ladder(15, 5, 0)
    d = decide(steps, T0, T0)
    assert d.fire is not None and d.fire.after_minutes == 0
    assert d.next_at == T0 + timedelta(minutes=5)


def test_the_nudge_phase_reuses_the_last_contact():
    """Once the ladder is exhausted we keep nudging whoever was last told — escalating
    past the top of the ladder would mean paging someone the user never listed."""
    steps = ladder(0, 5)
    d = decide(steps, T0, T0 + timedelta(minutes=30), step_index=2, repeats_done=0,
               last_notified_at=T0 + timedelta(minutes=5))
    assert d.fire == esc.ordered_steps(steps)[-1]
    assert d.repeats_done == 1


def test_the_last_nudge_leaves_no_next_action():
    """The final message must close the incident's schedule, not leave the worker
    re-checking it forever."""
    d = decide(ladder(0), T0, T0 + timedelta(hours=5), step_index=1, repeats_done=2,
               repeat_minutes=15, max_repeats=3, last_notified_at=T0)
    assert d.fire is not None and d.repeats_done == 3
    assert d.finished


def test_a_spent_budget_is_terminal_and_silent():
    d = decide(ladder(0), T0, T0 + timedelta(days=1), step_index=1, repeats_done=3, max_repeats=3)
    assert d.fire is None and d.finished


# ── Severity gating: never page for something the user didn't ask about ──────

@pytest.mark.parametrize("min_sev,sev,expected", [
    ("high", "critical", True),
    ("high", "high", True),
    ("high", "warning", False),
    ("high", "info", False),
    ("critical", "high", False),
    ("critical", "critical", True),
    ("info", "info", True),
    ("info", "critical", True),
])
def test_severity_gate(min_sev, sev, expected):
    assert esc.severity_allows(min_sev, sev) is expected


def test_an_unknown_severity_never_pages():
    """A typo must fail toward silence. Waking someone up for something they did not
    configure is worse than not waking them for something misspelled."""
    assert esc.severity_allows("high", "urgent!!") is False
    assert esc.severity_allows("high", "") is False
    assert esc.severity_allows("high", None) is False  # type: ignore[arg-type]


def test_an_unknown_min_severity_falls_back_to_the_default():
    assert esc.severity_allows("nonsense", "critical") is True
    assert esc.severity_allows("nonsense", "warning") is False


# ── Reading your own ladder back ─────────────────────────────────────────────

def test_describe_reads_like_a_person_wrote_it():
    lines = esc.describe(
        [Step(0, "email", "me@co.com", "my inbox"),
         Step(5, "sms", "+8801", "my phone"),
         Step(15, "sms", "+8802", "Rafi")],
        repeat_minutes=15, max_repeats=3,
    )
    assert lines[0] == "Right away — email my inbox"
    assert lines[1] == "After 5 minutes — text my phone"
    assert lines[2] == "After 15 minutes — text Rafi"
    assert "up to 3 more times" in lines[3]
    assert lines[-1] == "Acknowledging stops all of it."


def test_describe_is_honest_about_an_empty_policy():
    assert "no steps" in esc.describe([], 15, 3)[0]


def test_describe_says_so_when_there_is_no_nudge_phase():
    lines = esc.describe([Step(0, "email", "me@co.com")], 15, max_repeats=0)
    assert not any("up to" in line for line in lines)


def test_long_delays_read_as_hours():
    lines = esc.describe([Step(90, "sms", "+880")], 15, 0)
    assert "After 1h 30m" in lines[0]
    assert "After 2 hours" in esc.describe([Step(120, "sms", "+880")], 15, 0)[0]


def test_first_action_at_is_relative_to_the_incident_start():
    assert esc.first_action_at(ladder(0, 5), T0) == T0
    assert esc.first_action_at(ladder(7), T0) == T0 + timedelta(minutes=7)
    assert esc.first_action_at([], T0) is None
