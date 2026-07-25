"""Certificate expiry rules (docs/PRO-FEATURES-PLAN.md §4 #9).

An expired certificate is the most preventable outage there is — it announces itself weeks
ahead. The two rules that decide whether this feature is useful or ignored:

1. **Getting worse is news; staying bad is not.** A cert 10 days from expiry must not email
   for 10 days running, or people learn to ignore our alerts.
2. **Unknown is never "fine".** A check that could not complete must not read as healthy.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.ssl_service import (
    CRITICAL_DAYS,
    DEFAULT_WARN_DAYS,
    days_left,
    host_and_port,
    issuer_name,
    message,
    parse_not_after,
    severity,
    should_alert,
)

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


# ── What has a certificate at all ────────────────────────────────────────────

def test_https_urls_are_checkable():
    assert host_and_port("https://example.com") == ("example.com", 443)
    assert host_and_port("https://example.com:8443/path?q=1") == ("example.com", 8443)


def test_plain_http_has_nothing_to_check():
    """Not a failure — there is simply no certificate. It must not become an alert."""
    assert host_and_port("http://example.com") is None


def test_junk_urls_do_not_raise():
    for bad in ("", "not a url", "ftp://example.com", "https://", None):
        assert host_and_port(bad) is None


# ── Days remaining ───────────────────────────────────────────────────────────

def test_days_left():
    assert days_left(NOW + timedelta(days=30), NOW) == 30
    assert days_left(NOW + timedelta(days=1), NOW) == 1
    assert days_left(NOW - timedelta(days=2), NOW) == -2
    assert days_left(None, NOW) is None


def test_partial_day_rounds_down():
    """23 hours left is 'today', not 'tomorrow' — never round expiry in our favour."""
    assert days_left(NOW + timedelta(hours=23), NOW) == 0


def test_naive_datetimes_are_treated_as_utc():
    assert days_left(datetime(2026, 8, 24, 12, 0), NOW) == 30


# ── Severity ─────────────────────────────────────────────────────────────────

def test_severity_bands():
    assert severity(90) == "ok"
    assert severity(DEFAULT_WARN_DAYS + 1) == "ok"
    assert severity(DEFAULT_WARN_DAYS) == "warning"
    assert severity(CRITICAL_DAYS + 1) == "warning"
    assert severity(CRITICAL_DAYS) == "critical"
    assert severity(0) == "critical"
    assert severity(-1) == "expired"


def test_unknown_is_not_ok():
    """A failed check must never read as healthy."""
    assert severity(None) == "unknown"


def test_custom_warn_window_is_respected():
    assert severity(20, warn_days=30) == "warning"
    assert severity(20, warn_days=7) == "ok"


def test_warn_window_cannot_undercut_critical():
    """A warn window below the critical threshold must not hide a critical cert."""
    assert severity(2, warn_days=1) == "critical"


# ── Alerting: worse is news, same is not ─────────────────────────────────────

def test_alerts_when_crossing_into_warning():
    assert should_alert("ok", "warning")


def test_does_not_repeat_the_same_warning():
    """THE rule that decides whether these alerts get read or filtered."""
    assert not should_alert("warning", "warning")
    assert not should_alert("critical", "critical")
    assert not should_alert("expired", "expired")


def test_alerts_again_when_it_gets_worse():
    assert should_alert("warning", "critical")
    assert should_alert("critical", "expired")
    assert should_alert("warning", "expired")


def test_recovery_is_silent_but_rearms():
    """A renewal needs no email; and because state returns to 'ok', the next slide into
    warning alerts again."""
    assert not should_alert("expired", "ok")
    assert not should_alert("critical", "ok")
    assert should_alert("ok", "warning")


def test_first_ever_check_alerts_if_already_bad():
    assert should_alert(None, "warning")
    assert should_alert(None, "expired")


def test_never_alerts_on_ok_or_unknown():
    """'unknown' means our check failed — that is our problem, not an owner's emergency."""
    assert not should_alert("ok", "ok")
    assert not should_alert(None, "ok")
    assert not should_alert("ok", "unknown")
    assert not should_alert("warning", "unknown")


# ── Parsing what OpenSSL gives us ────────────────────────────────────────────

def test_parse_openssl_not_after():
    parsed = parse_not_after("Jul 25 12:00:00 2026 GMT")
    assert parsed == datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def test_parse_bad_not_after_is_none_not_a_crash():
    for bad in (None, "", "tomorrow", "2026-07-25"):
        assert parse_not_after(bad) is None


def test_issuer_prefers_the_recognisable_organisation():
    cert = {"issuer": ((("countryName", "US"),), (("organizationName", "Let's Encrypt"),),
                       (("commonName", "R11"),))}
    assert issuer_name(cert) == "Let's Encrypt"


def test_issuer_falls_back_to_common_name():
    assert issuer_name({"issuer": ((("commonName", "Internal CA"),),)}) == "Internal CA"
    assert issuer_name({}) is None


# ── The owner-facing message ─────────────────────────────────────────────────

def test_messages_say_what_to_do_and_avoid_jargon():
    subject, body = message("shop.example.com", -2, "expired")
    assert "EXPIRED" in subject
    assert "security warning" in body      # what the visitor actually sees
    assert "Ally" in body                  # and the way out

    subject, body = message("shop.example.com", 2, "critical")
    assert "2 day" in subject and "Ally" in body

    subject, body = message("shop.example.com", 12, "warning")
    assert "12 days" in subject
    assert "probably nothing to do" in body  # do not alarm people over routine renewal
