"""Fleet-health digest — the pure email builder + cadence gate.

No DB, no SMTP: drives ``build_digest`` with real ServerHealth/Finding objects and
asserts the email content, and checks ``is_due`` across cadences/weekdays.
"""
from __future__ import annotations

import pytest

from app.services import digest_service as d
from app.services.fleet_service import Finding, ServerHealth


def _finding(fid="disk-critical", sev="high", title="Disk is almost full", detail="94% used"):
    return Finding(id=fid, severity=sev, title=title, detail=detail, penalty=25,
                   action={"kind": "page", "label": "x", "path": "/x"})


def _health(name="TS1", score=75, grade="C", findings=None):
    return ServerHealth(server_id="s1", name=name, score=score, grade=grade,
                        status="online", headline="", findings=findings or [])


# ── cadence gate ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("weekday", range(7))
def test_daily_is_due_every_day(weekday):
    assert d.is_due("daily", weekday) is True


def test_weekly_is_due_only_on_monday():
    assert d.is_due("weekly", 0) is True
    assert all(d.is_due("weekly", wd) is False for wd in range(1, 7))


@pytest.mark.parametrize("weekday", range(7))
def test_off_is_never_due(weekday):
    assert d.is_due("off", weekday) is False


# ── the builder ────────────────────────────────────────────────────────────────

def test_empty_fleet_returns_none():
    assert d.build_digest("Sam", [], "https://app.x") is None


def test_findings_appear_in_subject_text_and_html():
    fleet = [_health("TestServer3", 55, "D", [_finding()])]
    out = d.build_digest("Sam Jones", fleet, "https://app.x")
    assert out is not None
    # subject counts the servers needing attention
    assert "need" in out["subject"].lower()
    # greeting uses the first name
    assert "Hi Sam," in out["text"]
    for blob in (out["text"], out["html"]):
        assert "TestServer3" in blob
        assert "Disk is almost full" in blob
    # HTML carries the grade badge + a CTA link into the app
    assert "https://app.x/dashboard" in out["html"]
    assert ">D<" in out["html"] or "D</span>" in out["html"]


def test_healthy_fleet_still_sends_a_reassuring_note():
    fleet = [_health("TestServer1", 100, "A", []), _health("TestServer2", 95, "A", [])]
    out = d.build_digest(None, fleet, "https://app.x")
    assert out is not None
    assert "healthy" in out["subject"].lower()
    assert "healthy" in out["html"].lower()
    # No findings → no server rows, but the count is mentioned.
    assert "Disk" not in out["text"]


def test_html_escapes_server_names():
    fleet = [_health("<script>evil</script>", 40, "D", [_finding()])]
    out = d.build_digest("A", fleet, "https://app.x")
    assert "<script>evil</script>" not in out["html"]
    assert "&lt;script&gt;" in out["html"]


def test_mixed_fleet_lists_bad_then_notes_healthy():
    fleet = [_health("Bad", 40, "D", [_finding()]), _health("Good", 100, "A", [])]
    out = d.build_digest("A", fleet, "")
    assert "Bad" in out["text"]
    assert "1 other server looks healthy" in out["text"]


def test_non_urgent_findings_never_say_healthy():
    # A server with findings but not urgent (score >= 75, only medium/low) must NOT be
    # summarised as "healthy" while its findings are listed below.
    low = _finding(fid="backups-none", sev="medium", title="No backups configured", detail="set one up")
    out = d.build_digest("A", [_health("TS", 80, "B", [low])], "")
    assert "healthy" not in out["subject"].lower()
    assert "things to check" in out["subject"].lower()
