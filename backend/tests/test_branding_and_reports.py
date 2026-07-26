"""White-label branding + client reports (docs/PRO-FEATURES-PLAN.md §4 #3).

Branding is rendered on a **public** status page, so its two string fields are injection
surfaces: ``primary_color`` is interpolated into styling and ``logo_url`` goes into an
``<img src>``. Validating at the write boundary is the only place it can be done once for
every consumer, so these tests pin it there.

The client report is deterministic by design — an agency may bill against it, so it must be
reproducible and unable to invent numbers.
"""
from __future__ import annotations

import json

from app.services import branding_service, client_report_service
from app.services.branding_service import normalise_color, public_branding, valid_color, valid_url


class _Branding:
    def __init__(self, **kw):
        self.company_name = kw.get("company_name")
        self.logo_url = kw.get("logo_url")
        self.primary_color = kw.get("primary_color")
        self.support_url = kw.get("support_url")
        self.support_email = kw.get("support_email")
        self.footer_text = kw.get("footer_text")
        self.hide_serverally_branding = kw.get("hide_serverally_branding", False)


# ── The colour is interpolated into client-facing styling ────────────────────

def test_valid_colours():
    for good in ("#fff", "#FFF", "#4F46E5", "#000000", None, ""):
        assert valid_color(good), good


def test_colour_cannot_carry_css_or_script():
    for bad in (
        "red",
        "#fff; background:url(javascript:alert(1))",
        "expression(alert(1))",
        "#12345",           # not 3 or 6 digits
        "#gggggg",
        "url(x)",
        "#fff\n}",          # break out of the rule
    ):
        assert not valid_color(bad), f"accepted dangerous colour: {bad!r}"


def test_colour_is_normalised_to_one_shape():
    assert normalise_color("#ABC") == "#aabbcc"
    assert normalise_color("#4F46E5") == "#4f46e5"
    assert normalise_color(None) is None
    assert normalise_color("") is None


# ── The logo goes into <img src>, the support link into <a href> ─────────────

def test_valid_urls():
    for good in ("https://cdn.example.com/logo.png", "http://example.com", None, ""):
        assert valid_url(good), good


def test_urls_cannot_carry_a_script_scheme():
    for bad in (
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "vbscript:msgbox(1)",
        "//evil.example.com/logo.png",   # scheme-relative
        "file:///etc/passwd",
        "https://a b.com",               # whitespace
        'https://x"onerror=alert(1)',    # attribute break-out
    ):
        assert not valid_url(bad), f"accepted dangerous URL: {bad!r}"


# ── What a stranger receives ─────────────────────────────────────────────────

def test_public_branding_is_an_allowlist():
    out = public_branding(_Branding(company_name="Acme Web"))
    assert set(out) == {
        "company_name", "logo_url", "primary_color", "support_url",
        "support_email", "footer_text", "show_credit", "app_name",
    }


def test_public_branding_never_publishes_the_raw_flag():
    """Publishing `hide_serverally_branding` invites a consumer to invert it by accident;
    we publish the already-resolved `show_credit` instead."""
    out = public_branding(_Branding(hide_serverally_branding=True))
    assert "hide_serverally_branding" not in out
    assert out["show_credit"] is False
    assert public_branding(_Branding())["show_credit"] is True


def test_no_branding_row_still_yields_a_usable_payload():
    """A user who never touched branding must not break their own status page."""
    out = public_branding(None)
    assert out["show_credit"] is True
    assert out["company_name"] is None
    assert out["app_name"] == "ServerAlly"


def test_blank_strings_become_null_not_empty_labels():
    out = public_branding(_Branding(company_name="   ", footer_text=""))
    assert out["company_name"] is None and out["footer_text"] is None


def test_public_branding_does_not_leak_an_account_email():
    """`support_email` is opt-in and separate from the account email precisely so that
    publishing a contact address is a deliberate act."""
    payload = json.dumps(public_branding(_Branding(company_name="Acme")))
    assert "user_id" not in payload and "@" not in payload


# ── The client report ────────────────────────────────────────────────────────

def test_verdict_puts_a_compromise_above_everything():
    """Ordered by what actually harms the client, not by which check ran last."""
    tone, headline = client_report_service._verdict(100.0, "A", "compromised", True)
    assert tone == "bad" and "security problem" in headline


def test_verdict_flags_downtime_before_posture():
    tone, headline = client_report_service._verdict(97.0, "A", "clean", True)
    assert tone == "warn" and "downtime" in headline


def test_verdict_mentions_backups_when_everything_else_is_fine():
    tone, headline = client_report_service._verdict(100.0, "A", "clean", False)
    assert tone == "warn" and "backups" in headline.lower()


def test_verdict_is_good_when_all_is_well():
    tone, headline = client_report_service._verdict(100.0, "A", "clean", True)
    assert tone == "good" and "smoothly" in headline


def test_verdict_survives_missing_data():
    """A brand-new server has no scans, no uptime and no backups — that is not a failure."""
    tone, _ = client_report_service._verdict(None, None, None, None)
    assert tone == "good"


def _report(**kw) -> dict:
    base = {
        "uptime": {"percentage": 100.0, "outages": 0, "monitors": [], "monitored": True},
        "security": {"grade": "A", "score": 96, "scanned_at": "2026-07-01", "threat_verdict": "clean"},
        "backups": {"configured": True, "runs": 30, "successful": 30, "healthy": True},
        "work": {"completed": [], "completed_count": 2, "commands_run": 40},
    }
    base.update(kw)
    return base


def test_summary_is_plain_language_for_a_non_technical_client():
    lines = " ".join(client_report_service.plain_summary(_report()))
    assert "online 100.0% of the time" in lines
    assert "no outages" in lines
    assert "out of 100" in lines          # the grade is explained, not just stated
    assert "nothing suspicious" in lines


def test_summary_is_honest_when_things_are_missing():
    lines = " ".join(client_report_service.plain_summary(_report(
        uptime={"percentage": None, "outages": 0, "monitors": [], "monitored": False},
        backups={"configured": False, "runs": 0, "successful": 0, "healthy": None},
    )))
    assert "not set up" in lines
    assert "No backups are configured" in lines


def test_summary_reports_partial_backup_failure_precisely():
    lines = " ".join(client_report_service.plain_summary(_report(
        backups={"configured": True, "runs": 10, "successful": 7, "healthy": False},
    )))
    assert "7 of 10" in lines


def test_period_bounds_span_the_requested_days():
    start, end = client_report_service.period_bounds(30)
    assert 29 <= (end - start).days <= 30
