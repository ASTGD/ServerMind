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


# --- Deciding whether HTTPS can be turned on ---------------------------------------------
#
# The one requirement is outside our control: the domain must ALREADY point at the server,
# because the authority proves ownership by reaching it through that name. Let's Encrypt
# allows five certificates per domain per week and a FAILED attempt spends one, so an
# attempt that cannot succeed is worse than a refusal — three of those and the domain is
# locked out for days.

import pytest
from app.services import ssl_service


@pytest.mark.asyncio
async def test_ready_when_the_domain_resolves_to_the_server(monkeypatch):
    async def fake(name):
        return {"203.0.113.10"}
    monkeypatch.setattr(ssl_service, "resolve", fake)

    check = await ssl_service.check_dns("shop.example.com", "203.0.113.10")
    assert check["ready"] is True
    assert check["reason"] is None


@pytest.mark.asyncio
async def test_not_ready_when_the_domain_does_not_resolve(monkeypatch):
    """A domain bought an hour ago. Normal, not an error."""
    async def fake(name):
        return set()
    monkeypatch.setattr(ssl_service, "resolve", fake)

    check = await ssl_service.check_dns("brandnew.example.com", "203.0.113.10")
    assert check["ready"] is False
    assert check["reason"] == "does not resolve"
    message = ssl_service.dns_message("brandnew.example.com", check)
    assert "does not point anywhere yet" in message
    assert "203.0.113.10" in message, "the message must carry the address to point at"


@pytest.mark.asyncio
async def test_not_ready_when_it_points_somewhere_else(monkeypatch):
    """The common one: DNS still aimed at the old host during a migration."""
    async def fake(name):
        return {"198.51.100.7"} if name == "shop.example.com" else {"203.0.113.10"}
    monkeypatch.setattr(ssl_service, "resolve", fake)

    check = await ssl_service.check_dns("shop.example.com", "203.0.113.10")
    assert check["ready"] is False
    assert check["reason"] == "points somewhere else"
    assert "198.51.100.7" in ssl_service.dns_message("shop.example.com", check)


@pytest.mark.asyncio
async def test_a_server_added_by_hostname_still_matches(monkeypatch):
    """Not every server is stored as an IP. Comparing the names would say no when the
    domain points at exactly the right machine."""
    async def fake(name):
        return {"203.0.113.10"}          # both the domain and the server's hostname
    monkeypatch.setattr(ssl_service, "resolve", fake)

    check = await ssl_service.check_dns("shop.example.com", "box.hosting.example")
    assert check["ready"] is True


@pytest.mark.asyncio
async def test_one_matching_address_among_several_is_enough(monkeypatch):
    """A domain behind round-robin DNS answers with several addresses; the certificate can
    still be issued as long as one of them is this server."""
    async def fake(name):
        return {"198.51.100.7", "203.0.113.10"} if "shop" in name else {"203.0.113.10"}
    monkeypatch.setattr(ssl_service, "resolve", fake)

    assert (await ssl_service.check_dns("shop.example.com", "203.0.113.10"))["ready"] is True


@pytest.mark.asyncio
async def test_a_lookup_that_fails_is_not_treated_as_ready(monkeypatch):
    """Fails closed. A resolver hiccup must not green-light an attempt that would spend
    one of the week's five."""
    async def fake(name):
        return set()
    monkeypatch.setattr(ssl_service, "resolve", fake)

    check = await ssl_service.check_dns("shop.example.com", "unresolvable.invalid")
    assert check["ready"] is False


def test_the_installer_never_reissues_a_certificate_that_already_exists():
    """Re-issuing spends one of five a week for nothing, and exhausting them locks the
    domain out for days."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS, _script_for

    script = _script_for(next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == "site-ssl"))
    assert 'if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then' in script
    assert "--keep-until-expiring" in script


def test_the_installer_checks_the_config_before_the_web_server_keeps_it():
    """A configuration that does not parse takes every site on the server offline, not
    just this one."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS, _script_for

    script = _script_for(next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == "site-ssl"))
    assert "nginx -t" in script and "apachectl configtest" in script
    assert script.index("TEST_CMD") < script.index("systemctl reload")


def test_the_installer_refuses_a_domain_the_server_does_not_serve():
    """A certificate for a domain this machine does not answer for would be issued
    successfully and protect nothing."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS, _script_for

    script = _script_for(next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == "site-ssl"))
    assert "is not set up on this server yet" in script


def test_the_installer_names_the_three_things_that_actually_go_wrong():
    """certbot's own output is long and says none of this in words anyone can act on."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS, _script_for

    script = _script_for(next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == "site-ssl"))
    assert "too many certificates" in script            # rate limit
    assert "does not point at this server" in script    # dns
    assert "Open port 80, then try again" in script     # port 80 blocked
    # Each one has to be reachable — a branch that can never be taken says nothing.
    for marker in ("rate limit", "NXDOMAIN|DNS problem", "Timeout|connection refused"):
        assert marker in script
