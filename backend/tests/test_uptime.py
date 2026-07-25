"""Uptime monitoring rules (docs/MARKET-RESEARCH-2026-07.md §8.2, Wave 1 #3).

Two product rules carry all the weight, and both are pure functions so they can be
tested exactly:

1. **A 200 is not proof.** The same lesson the mission verification gate learned — a
   broken or hacked site very often returns 200 with a blank body or an error page.
2. **One failed check is not an outage.** Alerts are only trustworthy if they don't cry
   wolf on a single network blip.
"""
from __future__ import annotations

from app.services.uptime_service import evaluate, next_state, uptime_percentage


# ── Rule 1: a 200 is not proof ───────────────────────────────────────────────

def test_healthy_page_is_up():
    r = evaluate(status_code=200, body="<html><body>Welcome to my shop</body></html>",
                 expected_status=200, expected_keyword=None)
    assert r.ok and r.http_status == 200 and r.error is None


def test_blank_200_is_down():
    """A blank 200 is the classic signature of a broken PHP site."""
    r = evaluate(status_code=200, body="", expected_status=200, expected_keyword=None)
    assert not r.ok
    assert "empty" in r.error.lower()


def test_whitespace_only_200_is_down():
    r = evaluate(status_code=200, body="\n   \n\t ", expected_status=200, expected_keyword=None)
    assert not r.ok


def test_keyword_missing_is_down_even_on_200():
    """The site answers, but it is not serving the real page — e.g. a parked/hacked page."""
    r = evaluate(status_code=200, body="<html>Account Suspended</html>",
                 expected_status=200, expected_keyword="Welcome to my shop")
    assert not r.ok
    assert "Welcome to my shop" in r.error


def test_keyword_present_is_up():
    r = evaluate(status_code=200, body="<html>Welcome to my shop — now open</html>",
                 expected_status=200, expected_keyword="Welcome to my shop")
    assert r.ok


def test_keyword_check_overrides_the_empty_body_rule():
    """With an explicit keyword the owner decides what 'working' means; a short body that
    contains it is fine."""
    r = evaluate(status_code=200, body="OK", expected_status=200, expected_keyword="OK")
    assert r.ok


def test_wrong_status_is_down_and_says_what_it_got():
    r = evaluate(status_code=502, body="Bad Gateway", expected_status=200, expected_keyword=None)
    assert not r.ok and r.http_status == 502
    assert "502" in r.error


def test_short_but_real_bodies_are_up():
    """Regression: an arbitrary "suspiciously short" threshold reported legitimately short
    pages as DOWN — a redirect stub, an API health endpoint and a plain OK are all valid.
    A false DOWN alert destroys trust in every other alert we send."""
    for body in ("<html>moved</html>", '{"ok":true}', "OK", "1"):
        r = evaluate(status_code=200, body=body, expected_status=200, expected_keyword=None)
        assert r.ok, f"{body!r} is a real response, not an outage"


def test_non_200_can_be_the_expected_status():
    """A monitor may legitimately expect a redirect or a 401."""
    r = evaluate(status_code=301, body="<html>moved</html>", expected_status=301, expected_keyword=None)
    assert r.ok


def test_transport_error_is_down():
    r = evaluate(status_code=None, body=None, expected_status=200,
                 expected_keyword=None, transport_error="The domain name could not be resolved (DNS problem).")
    assert not r.ok and "DNS" in r.error


# ── Rule 2: one failed check is not an outage ────────────────────────────────

def test_single_failure_does_not_declare_an_outage():
    status, failures, changed = next_state(
        current_status="up", consecutive_failures=0, ok=False, failure_threshold=2
    )
    assert status == "up", "a single blip must not page anyone"
    assert failures == 1 and changed is False


def test_second_consecutive_failure_declares_down():
    status, failures, changed = next_state(
        current_status="up", consecutive_failures=1, ok=False, failure_threshold=2
    )
    assert status == "down" and failures == 2 and changed is True


def test_recovery_is_immediate_and_announced_once():
    status, failures, changed = next_state(
        current_status="down", consecutive_failures=5, ok=True, failure_threshold=2
    )
    assert status == "up" and failures == 0 and changed is True


def test_staying_down_does_not_re_announce():
    """A site down for six hours must not send 72 emails."""
    status, failures, changed = next_state(
        current_status="down", consecutive_failures=9, ok=False, failure_threshold=2
    )
    assert status == "down" and changed is False


def test_staying_up_does_not_announce():
    status, failures, changed = next_state(
        current_status="up", consecutive_failures=0, ok=True, failure_threshold=2
    )
    assert status == "up" and changed is False


def test_threshold_of_one_declares_down_immediately():
    status, _f, changed = next_state(
        current_status="up", consecutive_failures=0, ok=False, failure_threshold=1
    )
    assert status == "down" and changed is True


def test_threshold_is_floored_at_one():
    """A zero/negative threshold must not make a monitor un-failable."""
    status, _f, changed = next_state(
        current_status="up", consecutive_failures=0, ok=False, failure_threshold=0
    )
    assert status == "down" and changed is True


def test_first_ever_check_transitions_out_of_unknown():
    up, _f, changed = next_state(
        current_status="unknown", consecutive_failures=0, ok=True, failure_threshold=2
    )
    assert up == "up" and changed is True


def test_new_monitor_failing_reaches_down_after_threshold():
    status, failures, changed = next_state(
        current_status="unknown", consecutive_failures=0, ok=False, failure_threshold=2
    )
    assert status == "unknown" and failures == 1 and changed is False
    status, failures, changed = next_state(
        current_status="unknown", consecutive_failures=failures, ok=False, failure_threshold=2
    )
    assert status == "down" and changed is True


# ── Uptime percentage ────────────────────────────────────────────────────────

def test_uptime_percentage():
    assert uptime_percentage(0, 0) == 100.0, "an unchecked monitor is not a failing one"
    assert uptime_percentage(100, 100) == 100.0
    assert uptime_percentage(99, 100) == 99.0
    assert uptime_percentage(0, 10) == 0.0
    assert uptime_percentage(2, 3) == 66.67


# ── Failure messages must point at the right fix ─────────────────────────────

def test_dns_failure_is_named_as_dns_not_a_connection_problem():
    """Live testing showed a non-existent domain reported as 'could not connect'. DNS and
    a refused connection need completely different fixes (point the domain vs fix the
    server), and the wording differs per platform — match all the common forms."""
    from app.services.uptime_service import _friendly_transport_error as f

    for text in (
        "[Errno 8] nodename nor servname provided, or not known",   # macOS
        "[Errno -2] Name or service not known",                     # Linux
        "Temporary failure in name resolution",
        "getaddrinfo failed",
    ):
        assert "dns" in f(Exception(text)).lower(), f"not detected as DNS: {text}"


def test_other_transport_failures_keep_their_own_message():
    from app.services.uptime_service import _friendly_transport_error as f

    assert "in time" in f(TimeoutError("read timeout")).lower()
    assert "certificate" in f(Exception("certificate verify failed")).lower()
    assert "connect" in f(ConnectionRefusedError("connection refused")).lower()
