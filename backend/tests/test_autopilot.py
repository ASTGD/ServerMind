"""Autopilot policy guarantees (docs/PRO-FEATURES-PLAN.md §4 #1+#2).

Autopilot lets Ally act **without a human present**, so the policy is the most
safety-critical pure function in the product. The properties below are the promises we
make to an owner who turns it on.

The one that underpins all the others is structural, not a test of this module: the
absolute blocklist runs in ``terminal._run_mission`` step 2 and *refuses* a blocked
command before the approval check in step 3 — so no policy value can ever authorise a
catastrophic command. ``test_policy_is_never_asked_about_blocked_commands`` pins that
ordering so a refactor cannot quietly invert it.
"""
from __future__ import annotations

import inspect

from app.models.autopilot import POLICIES, POLICY_FULL, POLICY_REPORT_ONLY, POLICY_SAFE_FIXES
from app.services import autopilot_service
from app.services.autopilot_service import decide


# ── Look-and-report: the safe default ────────────────────────────────────────

def test_report_only_allows_looking():
    """It must be able to investigate — that is the whole point of a report."""
    d = decide(policy=POLICY_REPORT_ONLY, risk_level="low", safety_status="ok", is_read_only=True)
    assert d.approve


def test_report_only_refuses_any_change():
    d = decide(policy=POLICY_REPORT_ONLY, risk_level="low", safety_status="ok", is_read_only=False)
    assert not d.approve
    assert "look and report" in d.reason.lower()


def test_report_only_refuses_even_a_harmless_looking_change():
    """Low risk + safety-ok is still a CHANGE, and this policy promised not to make any."""
    d = decide(policy=POLICY_REPORT_ONLY, risk_level="low", safety_status="ok", is_read_only=False)
    assert not d.approve


# ── Safe fixes: ordinary repairs yes, risky ones no ──────────────────────────

def test_safe_fixes_approves_an_ordinary_repair():
    """e.g. restarting a service that has died."""
    d = decide(policy=POLICY_SAFE_FIXES, risk_level="medium", safety_status="ok", is_read_only=False)
    assert d.approve


def test_safe_fixes_stops_at_a_high_risk_step():
    d = decide(policy=POLICY_SAFE_FIXES, risk_level="high", safety_status="ok", is_read_only=False)
    assert not d.approve
    assert "go-ahead" in d.reason.lower()


def test_safe_fixes_stops_at_a_confirm_pattern():
    """The confirm list is things like `apt remove`, `systemctl disable`, `DROP TABLE` —
    a careful human would look, so autopilot must too."""
    d = decide(policy=POLICY_SAFE_FIXES, risk_level="low", safety_status="confirm", is_read_only=False)
    assert not d.approve


def test_safe_fixes_stops_when_the_ai_itself_flagged_the_step():
    d = decide(policy=POLICY_SAFE_FIXES, risk_level="low", safety_status="ok",
               is_read_only=False, flagged_by_ai=True)
    assert not d.approve


# ── Full: the owner has explicitly accepted the trade ────────────────────────

def test_full_proceeds_on_what_the_blocklist_permits():
    for risk in ("low", "medium", "high"):
        assert decide(policy=POLICY_FULL, risk_level=risk, safety_status="confirm",
                      is_read_only=False).approve


# ── Failing closed ───────────────────────────────────────────────────────────

def test_unknown_policy_falls_back_to_the_safest_behaviour():
    """A typo, a stale row, or a future value must never mean 'do anything'."""
    for bogus in ("", "yolo", "admin", None):
        d = decide(policy=bogus, risk_level="low", safety_status="ok", is_read_only=False)
        assert not d.approve, f"unknown policy {bogus!r} must not authorise a change"


def test_missing_risk_level_is_not_treated_as_safe_at_report_only():
    d = decide(policy=POLICY_REPORT_ONLY, risk_level=None, safety_status="ok", is_read_only=False)
    assert not d.approve


def test_every_declared_policy_is_handled():
    """No policy value may fall through to an unintended branch."""
    for policy in POLICIES:
        d = decide(policy=policy, risk_level="low", safety_status="ok", is_read_only=True)
        assert isinstance(d.approve, bool)


# ── The structural guarantee ─────────────────────────────────────────────────

def test_policy_is_never_asked_about_blocked_commands():
    """The blocklist must be refused BEFORE the approval gate, so no policy can authorise
    a catastrophic command. Pinned by reading the engine: the 'blocked' branch and its
    `continue` must appear before `needs_approval` is computed."""
    from app.websocket import terminal

    src = inspect.getsource(terminal._run_mission)
    blocked_at = src.find('safety.status == "blocked"')
    approval_at = src.find("needs_approval =")
    assert blocked_at != -1, "the blocklist check disappeared from the mission loop"
    assert approval_at != -1, "the approval gate disappeared from the mission loop"
    assert blocked_at < approval_at, (
        "SAFETY REGRESSION: the approval gate now runs before the blocklist check, so an "
        "autopilot policy could authorise a blocked command"
    )
    # And the blocked branch must skip the step entirely rather than fall through.
    assert "continue" in src[blocked_at:approval_at], "blocked steps must be skipped, not approved"


# ── Reporting ────────────────────────────────────────────────────────────────

def _task(**kw):
    class T:
        name = "Nightly check"
        policy = POLICY_SAFE_FIXES
        channel = "email"
        channel_target = "owner@example.com"
        notify_on_change_only = True
    t = T()
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def test_quiet_when_nothing_happened():
    """A nightly task that finds nothing must not email every single night."""
    assert not autopilot_service.should_notify(
        {"status": "completed", "approved_steps": 0}, _task()
    )


def test_speaks_up_when_it_changed_something():
    assert autopilot_service.should_notify(
        {"status": "completed", "approved_steps": 2}, _task()
    )


def test_speaks_up_when_it_needs_you():
    assert autopilot_service.should_notify(
        {"status": "needs_you", "approved_steps": 0}, _task()
    )


def test_never_notifies_without_a_destination():
    assert not autopilot_service.should_notify(
        {"status": "needs_you"}, _task(channel=None, channel_target=None)
    )


def test_summary_is_plain_language():
    subject, body = autopilot_service.summarise(
        {"status": "needs_you", "stopped_reason": "It needed your go-ahead."}, _task()
    )
    assert "needs your OK" in subject
    assert "Nothing was changed" in body
    assert "Fix ordinary problems" in body  # the policy is restated so the owner knows the setting


def test_runner_satisfies_the_mission_engine_contract():
    """AutopilotRunner stands in for the WebSocket the engine talks to. If the engine
    starts using another attribute, every scheduled run would crash at that point — with
    nobody watching, since autopilot runs unattended. Found live: `finish`, `model` and
    `stop_requested` were all missing on the first write."""
    import re

    from app.services.autopilot_service import AutopilotRunner
    from app.websocket import terminal

    src = inspect.getsource(terminal._run_mission) + inspect.getsource(terminal._run_mission_detached)
    used = set(re.findall(r"\bws\.([a-z_]+)", src)) | set(re.findall(r"\brunner\.([a-z_]+)", src))
    runner = AutopilotRunner(policy=POLICY_REPORT_ONLY)
    missing = sorted(a for a in used if not hasattr(runner, a))
    assert not missing, f"AutopilotRunner is missing {missing} — scheduled runs would crash"


def test_autopilot_call_matches_the_engine_signature():
    """The kwargs we pass must be the ones the engine declares (home_server, not server)."""
    from app.websocket import terminal

    params = inspect.signature(terminal._run_mission).parameters
    for required in ("home_server", "goal", "skill_slug", "user_language"):
        assert required in params, f"_run_mission no longer accepts {required}"


def test_autopilot_never_pins_a_model():
    """A pinned model would bypass the Smart Model Ladder for every scheduled run."""
    from app.services.autopilot_service import AutopilotRunner

    assert AutopilotRunner(policy=POLICY_REPORT_ONLY).model is None


# ── Bugs found by exercising the REAL path, not just decide() ────────────────

def test_autopilot_forces_the_strictest_approval_floor():
    """THE bug that mattered: `systemctl restart nginx` and even `rm -f /tmp/x` are
    safety-'ok' and NOT read-only, so the engine runs them WITHOUT asking. That means the
    approval gate alone cannot enforce "look and tell me" — a report-only task could still
    change the server, breaking the promise the UI makes.

    Autopilot therefore forces careful mode, which flags every mutating step for approval
    so the policy actually sees it."""
    import inspect as _i

    from app.services import autopilot_service as a

    src = _i.getsource(a.run_task_mission)
    assert 'ally_mode_override="careful"' in src, (
        "SAFETY REGRESSION: autopilot no longer forces careful mode, so ordinary changes "
        "would bypass the policy and a report-only task could modify the server"
    )
    # And the engine must still accept the override.
    from app.websocket import terminal
    assert "ally_mode_override" in _i.signature(terminal._run_mission).parameters


def test_ordinary_changes_really_do_bypass_approval_without_the_override():
    """Pins the premise of the test above, so nobody 'simplifies' the override away."""
    from app.services import safety_service

    for cmd in ("systemctl restart nginx", "rm -f /tmp/scratch"):
        assert safety_service.validate_command(cmd, "linux").status == "ok"
        assert not safety_service.is_read_only_command(cmd)


def test_policy_does_not_infer_danger_from_needs_approval():
    """Second bug: inferring safety_status from `needs_approval` made every step look
    dangerous, collapsing safe_fixes into report_only. The runner must compute the safety
    verdict itself and read the AI's flag from the explicit `ai_flagged` field."""
    import inspect as _i

    from app.services.autopilot_service import AutopilotRunner

    src = _i.getsource(AutopilotRunner.wait_decision)
    assert "validate_command" in src, "the runner must compute the safety verdict itself"
    assert 'step.get("ai_flagged")' in src, "the AI flag must be read explicitly"
    assert 'needs_approval' not in src.split("flagged =")[1].split("\n")[0], (
        "ai_flagged must not be inferred from needs_approval"
    )


def test_engine_reports_why_it_asked():
    """The step event must carry `ai_flagged`, or an unattended policy cannot tell an
    AI-flagged step from an ordinary one in careful mode."""
    import inspect as _i

    from app.websocket import terminal

    assert '"ai_flagged"' in _i.getsource(terminal._run_mission)
