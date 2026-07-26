"""Scheduled monthly delivery of the client report (docs/PRO-FEATURES-PLAN.md §4 #3).

An agency's *client* receives this email, so two properties matter more than the rest:

1. **It goes out once a month.** A restart, a re-run, or a second scheduler instance must
   not send the same report twice to a paying agency's customer.
2. **It carries the agency's brand, not ours** — and the branding strings land in HTML, so
   they must be escaped even though they were validated when saved.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.services import client_report_service
from app.workers.client_report_worker import is_due


class _Sub:
    def __init__(self, **kw):
        self.is_active = kw.get("is_active", True)
        self.send_day = kw.get("send_day", 1)
        self.last_sent = kw.get("last_sent")


def _day(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, 9, 0, tzinfo=timezone.utc)


# ── Sending exactly once a month ─────────────────────────────────────────────

def test_sends_on_its_day():
    assert is_due(_Sub(send_day=5), _day(2026, 8, 5))


def test_does_not_send_on_another_day():
    assert not is_due(_Sub(send_day=5), _day(2026, 8, 6))


def test_never_sends_twice_in_the_same_month():
    """The property that protects the agency's relationship with its client: a re-run,
    a restart or a duplicate scheduler must not re-send."""
    sub = _Sub(send_day=5, last_sent=_day(2026, 8, 5))
    assert not is_due(sub, _day(2026, 8, 5))


def test_sends_again_the_next_month():
    sub = _Sub(send_day=5, last_sent=_day(2026, 8, 5))
    assert is_due(sub, _day(2026, 9, 5))


def test_a_naive_last_sent_is_still_compared_correctly():
    """Older rows may carry a naive timestamp; comparing it must not raise."""
    sub = _Sub(send_day=5, last_sent=datetime(2026, 8, 5, 9, 0))
    assert not is_due(sub, _day(2026, 8, 5))


def test_paused_recipient_never_sends():
    assert not is_due(_Sub(send_day=5, is_active=False), _day(2026, 8, 5))


def test_a_day_the_month_does_not_have_still_fires():
    """Defensive: the API caps send_day at 28, but a day-31 row must not silently never
    send — it fires on the last day of a short month."""
    assert is_due(_Sub(send_day=31), _day(2026, 2, 28))
    assert not is_due(_Sub(send_day=31), _day(2026, 2, 27))


# ── The email itself ─────────────────────────────────────────────────────────

def _report(**kw) -> dict:
    base = {
        "server_name": "Acme Shop",
        "period_days": 30,
        "tone": "good",
        "headline": "Everything ran smoothly this period",
        "uptime": {"percentage": 100.0, "outages": 0, "monitors": [], "monitored": True},
        "security": {"grade": "A", "score": 96, "scanned_at": "2026-07-01", "threat_verdict": "clean"},
        "backups": {"configured": True, "runs": 30, "successful": 30, "healthy": True},
        "work": {"completed": ["Cleaned up a full disk"], "completed_count": 1, "commands_run": 40},
    }
    base.update(kw)
    return base


def _brand(**kw) -> dict:
    base = {
        "company_name": "Acme Web Studio", "logo_url": None, "primary_color": "#0f766e",
        "support_url": None, "support_email": None, "footer_text": None,
        "show_credit": True, "app_name": "ServerAlly",
    }
    base.update(kw)
    return base


def test_email_is_branded_as_the_agency():
    out = client_report_service.render_email(_report(), _brand(), "Acme Shop", "Jane Doe")
    assert "Acme Web Studio" in out["subject"]
    assert "Acme Web Studio" in out["html"]
    assert "#0f766e" in out["html"]
    assert out["text"].startswith("Hi Jane,")


def test_white_label_removes_every_trace_of_us():
    """`hide_serverally_branding` is the actual white-label switch — if our name survives
    it, an agency cannot resell the report."""
    out = client_report_service.render_email(
        _report(), _brand(show_credit=False), "Acme Shop"
    )
    assert "ServerAlly" not in out["html"]
    assert "ServerAlly" not in out["text"]
    assert "ServerAlly" not in out["subject"]


def _markup(html: str) -> tuple[set[str], set[str]]:
    """Parse the email the way a mail client would, and return (tag names, attribute
    names) that actually exist as MARKUP.

    Asserting on substrings is too weak here: correctly-escaped text legitimately still
    *contains* the characters "onerror=". What matters is whether the payload became an
    element or an attribute, which only a parse can answer.
    """
    from html.parser import HTMLParser

    tags: set[str] = set()
    attrs: set[str] = set()

    class _P(HTMLParser):
        def handle_starttag(self, tag, attributes):
            tags.add(tag)
            attrs.update(name.lower() for name, _v in attributes)

    p = _P()
    p.feed(html)
    return tags, attrs


def test_branding_cannot_inject_markup_into_a_client_email():
    """Validated at the write boundary, escaped again here — an HTML email is a second
    consumer and must not depend on another module still being correct."""
    out = client_report_service.render_email(
        _report(),
        _brand(company_name='<script>alert(1)</script>',
               footer_text='"><img src=x onerror=alert(1)>'),
        "Acme Shop",
    )
    tags, attrs = _markup(out["html"])
    assert "script" not in tags
    assert "img" not in tags            # no logo was set, so no <img> may exist at all
    assert not any(a.startswith("on") for a in attrs)
    assert "&lt;script&gt;" in out["html"]   # it survived as visible text, which is fine


def test_a_server_name_from_the_owner_is_escaped_too():
    out = client_report_service.render_email(_report(), _brand(), '<b>Shop</b>')
    tags, _ = _markup(out["html"])
    assert "b" not in tags


def test_a_logo_url_cannot_break_out_of_its_attribute():
    out = client_report_service.render_email(
        _report(), _brand(logo_url='https://a.com/x.png" onerror="alert(1)'), "Acme Shop",
    )
    tags, attrs = _markup(out["html"])
    assert "img" in tags                # the logo still renders
    assert not any(a.startswith("on") for a in attrs)


def test_plain_text_is_always_present_as_the_fallback():
    """Some clients refuse HTML; the report must still be readable."""
    out = client_report_service.render_email(_report(), _brand(), "Acme Shop")
    assert "online 100.0% of the time" in out["text"]
    assert "Cleaned up a full disk" in out["text"]


def test_bad_news_is_not_dressed_up_as_good():
    out = client_report_service.render_email(
        _report(tone="bad", headline="We found a security problem and acted on it"),
        _brand(), "Acme Shop",
    )
    assert "security problem" in out["html"]
    assert "#b91c1c" in out["html"]          # the bad-news colour, not the good one
    assert "#059669" not in out["html"]


def test_support_link_uses_email_when_there_is_no_url():
    out = client_report_service.render_email(
        _report(), _brand(support_email="help@acme.com"), "Acme Shop"
    )
    assert "mailto:help@acme.com" in out["html"]


def test_missing_branding_still_produces_a_sendable_email():
    """An agency that never opened the branding panel must still be able to send."""
    from app.services.branding_service import public_branding
    out = client_report_service.render_email(_report(), public_branding(None), "Acme Shop")
    assert out["subject"] and out["text"] and out["html"]
