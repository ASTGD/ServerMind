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


# ── the token that was refused while being perfectly good ────────────────────
class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
    def json(self):
        return self._payload


def test_a_token_is_verified_by_doing_what_we_actually_need():
    """Reported live: a token with Zone:Read, DNS:Read and DNS:Write for every zone —
    exactly what our own instructions ask for — was refused. We were calling
    /user/tokens/verify, which asks Cloudflare about the token itself and needs
    permissions this feature never uses. Listing zones is the capability the whole
    feature rests on, so it is the honest test."""
    import ast
    import inspect
    from app.services.dns_service import CloudflareAdapter
    # The docstring explains the old endpoint, so match the CODE rather than the prose.
    tree = ast.parse(inspect.getsource(CloudflareAdapter.verify).strip())
    calls = [n.value for n in ast.walk(tree)
             if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    body = [c for c in calls if c.startswith("/")]
    assert any("/zones" in c for c in body), f"verify calls {body}"
    assert not any("/user/tokens/verify" in c for c in body), \
        "do not test a permission this feature never uses"


def test_cloudflares_own_reason_reaches_the_customer():
    """Every 401 was reported as "wrong permissions", which is one of several causes —
    expired, revoked, IP-restricted — each needing a different fix."""
    from app.services.dns_service import CloudflareAdapter
    r = _Resp(403, {"errors": [{"code": 9109, "message": "Unauthorized to access requested resource"}]})
    msg = CloudflareAdapter._reason(r)
    assert "Unauthorized to access requested resource" in msg
    assert "Zone:Read and DNS:Edit" in msg, "the hint belongs on this code, not on all of them"


def test_the_specific_reason_is_pulled_out_of_the_nested_chain():
    """Cloudflare puts a generic message on top and the useful one inside error_chain."""
    from app.services.dns_service import CloudflareAdapter
    r = _Resp(400, {"errors": [{"code": 6003, "message": "Invalid request headers",
                                "error_chain": [{"code": 6111,
                                                 "message": "Invalid format for Authorization header"}]}]})
    msg = CloudflareAdapter._reason(r)
    assert "Invalid format for Authorization header" in msg
    assert "not the token itself" in msg


def test_a_permission_hint_is_not_attached_to_unrelated_failures():
    """Telling someone to fix their permissions when the token has expired sends them
    to remake a token that was fine."""
    from app.services.dns_service import CloudflareAdapter
    r = _Resp(403, {"errors": [{"code": 1001, "message": "Something else entirely"}]})
    msg = CloudflareAdapter._reason(r)
    assert "Something else entirely" in msg
    assert "Zone:Read" not in msg


def test_an_unreadable_body_still_says_something():
    from app.services.dns_service import CloudflareAdapter
    class Bad:
        status_code = 502
        def json(self): raise ValueError("not json")
    assert "502" in CloudflareAdapter._reason(Bad())


# ── what people actually paste ───────────────────────────────────────────────
@pytest.mark.parametrize("pasted", [
    "abc123DEF456ghi789JKL012mno345PQR678stu",
    "  abc123DEF456ghi789JKL012mno345PQR678stu  ",
    "abc123DEF456ghi789JKL012mno\n345PQR678stu",     # copied from a narrow window
    "abc123DEF456ghi789JKL012mno 345PQR678stu",
    "Bearer abc123DEF456ghi789JKL012mno345PQR678stu",
])
def test_a_token_survives_the_ways_people_copy_it(pasted):
    """A line break in the middle produces a header the provider rejects as malformed,
    which reads as "your token is wrong" when only the copy was. No API token contains
    whitespace, so removing it cannot damage a real one."""
    from app.services.dns_service import clean_token
    assert clean_token(pasted) == "abc123DEF456ghi789JKL012mno345PQR678stu"


def test_the_shape_check_only_advises_it_never_refuses_a_plausible_token():
    """A format that changes must not lock customers out, so this is a hint before the
    round trip — not a gate."""
    from app.services.dns_service import looks_like_token
    assert looks_like_token("abc123DEF456ghi789JKL012mno345PQR678stu")
    assert not looks_like_token("hello there")
    assert not looks_like_token("short")
    assert not looks_like_token("")
