"""DNS — the validation that stops a screen from taking a domain offline.

Every case below is one a provider's API would happily accept. That is the point: the
provider is not the safety net, this is.
"""
from __future__ import annotations

import pytest

from app.services import dns_service as dns


# ── names: the mistake that silently creates www.example.com.example.com ──────
@pytest.mark.parametrize("given,expected", [
    ("www", "www.example.com"),
    ("www.example.com", "www.example.com"),
    ("@", "example.com"),
    ("", "example.com"),
    ("WWW", "www.example.com"),
    ("www.example.com.", "www.example.com"),
    ("mail.sub", "mail.sub.example.com"),
])
def test_name_is_normalised_so_the_domain_cannot_be_doubled(given, expected):
    assert dns.normalise_name(given, "example.com") == expected


def test_apex_is_recognised_however_it_is_typed():
    for form in ("@", "", "example.com", "EXAMPLE.COM."):
        assert dns.is_apex(form, "example.com"), form
    assert not dns.is_apex("www", "example.com")


# ── the records that break a domain, each accepted by the provider ────────────
def test_cname_on_the_domain_itself_is_refused():
    """Invalid per RFC 1034 and takes email down with the website. Cloudflare will
    accept it (it flattens); most providers will simply break."""
    with pytest.raises(dns.InvalidRecord) as e:
        dns.validate(type_="CNAME", name="@", content="target.example.net",
                     zone="example.com")
    assert "breaks email" in str(e.value)
    assert "A record" in str(e.value), "must say what to do instead"


def test_cname_pointing_at_an_ip_is_refused():
    with pytest.raises(dns.InvalidRecord) as e:
        dns.validate(type_="CNAME", name="www", content="203.0.113.10", zone="example.com")
    assert "points at another NAME" in str(e.value)


def test_mx_pointing_at_an_ip_is_refused():
    """Accepted by the API, then mail silently fails — receiving servers reject it."""
    with pytest.raises(dns.InvalidRecord) as e:
        dns.validate(type_="MX", name="@", content="203.0.113.10", zone="example.com",
                     priority=10)
    assert "not an IP address" in str(e.value)


def test_mx_without_a_priority_is_refused():
    with pytest.raises(dns.InvalidRecord):
        dns.validate(type_="MX", name="@", content="mail.example.com", zone="example.com")


@pytest.mark.parametrize("bad", ["not-an-ip", "203.0.113", "2001:db8::1", "hello world"])
def test_a_record_must_hold_an_ipv4(bad):
    with pytest.raises(dns.InvalidRecord):
        dns.validate(type_="A", name="www", content=bad, zone="example.com")


def test_aaaa_must_hold_an_ipv6_not_an_ipv4():
    with pytest.raises(dns.InvalidRecord):
        dns.validate(type_="AAAA", name="www", content="203.0.113.10", zone="example.com")
    ok = dns.validate(type_="AAAA", name="www", content="2001:db8::1", zone="example.com")
    assert ok["type"] == "AAAA"


# ── the records we refuse to touch at all ─────────────────────────────────────
@pytest.mark.parametrize("t", ["NS", "SOA", "DNSKEY", "DS", "RRSIG"])
def test_records_that_could_hand_away_the_domain_are_not_editable(t):
    """Editing NS is how a domain leaves your control. No owner-facing screen should
    offer it, so it is refused at the service, not hidden in the UI."""
    with pytest.raises(dns.InvalidRecord) as e:
        dns.validate(type_=t, name="@", content="ns1.attacker.net", zone="example.com")
    assert "your DNS provider" in str(e.value)


def test_an_unknown_type_is_refused():
    with pytest.raises(dns.InvalidRecord):
        dns.validate(type_="WAT", name="x", content="y", zone="example.com")


# ── things that should work ───────────────────────────────────────────────────
def test_ordinary_records_pass_and_come_back_normalised():
    r = dns.validate(type_="a", name="www", content=" 203.0.113.10 ", zone="example.com")
    assert r == {"type": "A", "name": "www.example.com", "content": "203.0.113.10",
                 "ttl": 300, "priority": None}


def test_txt_and_caa_and_srv_are_accepted():
    assert dns.validate(type_="TXT", name="@", content="v=spf1 -all",
                        zone="example.com")["type"] == "TXT"
    assert dns.validate(type_="CAA", name="@", content='0 issue "letsencrypt.org"',
                        zone="example.com")["type"] == "CAA"
    assert dns.validate(type_="SRV", name="_sip._tcp", content="10 5060 sip.example.com",
                        zone="example.com", priority=10)["type"] == "SRV"


def test_a_too_short_ttl_is_refused_but_automatic_is_allowed():
    with pytest.raises(dns.InvalidRecord):
        dns.validate(type_="A", name="www", content="203.0.113.10",
                     zone="example.com", ttl=5)
    # 1 is Cloudflare's "automatic"
    assert dns.validate(type_="A", name="www", content="203.0.113.10",
                        zone="example.com", ttl=1)["ttl"] == 1


def test_an_empty_value_is_refused():
    with pytest.raises(dns.InvalidRecord):
        dns.validate(type_="A", name="www", content="   ", zone="example.com")


# ── warnings: shown before a correct-looking but risky change ────────────────
def test_the_apex_a_record_warns_that_the_whole_site_is_at_stake():
    w = dns.warn_for(type_="A", name="@", zone="example.com")
    assert w and "offline everywhere" in w


def test_mx_changes_warn_about_email():
    assert "email" in (dns.warn_for(type_="MX", name="@", zone="example.com") or "")


def test_an_ordinary_subdomain_does_not_nag():
    assert dns.warn_for(type_="TXT", name="_acme-challenge", zone="example.com") is None


# ── credentials never leave the server ───────────────────────────────────────
def test_the_public_account_shape_cannot_leak_a_token():
    class FakeAccount:
        id = "abc"; provider = "cloudflare"; label = "My Cloudflare"
        encrypted_credential = "SUPER-SECRET-BLOB"
        created_at = None
    out = dns.public_account(FakeAccount())
    assert "SUPER-SECRET-BLOB" not in str(out)
    assert "encrypted_credential" not in out
    assert set(out) == {"id", "provider", "label", "created_at"}


def test_an_unknown_provider_is_a_sentence_not_a_crash():
    with pytest.raises(dns.DnsError) as e:
        dns.adapter_for("route53", {})
    assert "don’t support yet" in str(e.value) or "isn’t a DNS provider" in str(e.value)
