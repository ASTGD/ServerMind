"""Who is calling — the question rate limiting and the audit log both depend on.

Two failures are being guarded against. Believing the header when we should not lets
anyone mint a fresh rate-limit bucket per request, or write a false address into their own
audit trail. Not believing it when we should puts every customer behind a proxy into one
shared bucket, so one person can lock out everybody.
"""
from __future__ import annotations

import pytest

from app.services import client_ip


class Req:
    """The two things the resolver looks at."""

    def __init__(self, peer: str | None, xff: str | None = None):
        self.client = type("C", (), {"host": peer})() if peer else None
        self.headers = {"x-forwarded-for": xff} if xff else {}


def r(peer, xff=None):
    return client_ip.resolve(Req(peer, xff))


# ── behind our own proxies ───────────────────────────────────────────────────
def test_the_real_client_is_found_through_our_production_chain():
    """The live shape: visitor → Caddy → nginx container → backend. Both proxies append,
    so the client sits second from the right."""
    assert r("172.18.0.7", "203.0.113.5, 172.18.0.1") == "203.0.113.5"


def test_a_single_proxy_hop_works_too():
    assert r("127.0.0.1", "203.0.113.5") == "203.0.113.5"


def test_however_many_of_our_hops_there_are():
    """Walking from the right means the number of proxies never has to be configured."""
    assert r("10.0.0.9", "198.51.100.4, 10.0.0.1, 172.18.0.1, 192.168.1.1") == "198.51.100.4"


def test_two_visitors_behind_the_same_proxy_get_different_keys():
    """The whole point. Keyed on the peer these were identical, which is how one person
    could exhaust the login limit for everyone."""
    a = client_ip.key_func(Req("172.18.0.7", "203.0.113.5, 172.18.0.1"))
    b = client_ip.key_func(Req("172.18.0.7", "198.51.100.9, 172.18.0.1"))
    assert a != b


# ── what a client writes themselves must never win ───────────────────────────
def test_a_forged_header_cannot_choose_its_own_address():
    """A client can put anything in the header, but our proxy appends the truth after it,
    so the forgery is always further left than the real address."""
    assert r("172.18.0.7", "9.9.9.9, 203.0.113.5, 172.18.0.1") == "203.0.113.5"


def test_a_forged_header_of_many_addresses_still_loses():
    forged = "1.1.1.1, 2.2.2.2, 3.3.3.3"
    assert r("172.18.0.7", f"{forged}, 203.0.113.5, 172.18.0.1") == "203.0.113.5"


def test_a_forged_private_address_does_not_hide_the_real_one():
    assert r("127.0.0.1", "10.0.0.99, 203.0.113.5") == "203.0.113.5"


def test_the_header_is_ignored_when_the_connection_is_not_from_a_proxy():
    """Reaching the backend directly. If the header were believed here, supplying one
    would be all it takes to get a fresh bucket on every request."""
    assert r("198.51.100.7", "203.0.113.5") == "198.51.100.7"


def test_a_direct_caller_cannot_get_unlimited_buckets():
    keys = {client_ip.key_func(Req("198.51.100.7", f"10.0.0.{i}")) for i in range(50)}
    assert keys == {"198.51.100.7"}, "one attacker, one bucket"


# ── shapes proxies really emit ───────────────────────────────────────────────
@pytest.mark.parametrize("xff,want", [
    ("203.0.113.5:44321, 172.18.0.1", "203.0.113.5"),      # address with a port
    ("  203.0.113.5 ,172.18.0.1 ", "203.0.113.5"),         # untidy spacing
    ("2001:db8::1, 172.18.0.1", "2001:db8::1"),            # IPv6 client
    ("[2001:db8::1]:443, 172.18.0.1", "2001:db8::1"),      # IPv6 with a port
])
def test_the_usual_header_shapes_are_understood(xff, want):
    assert r("172.18.0.7", xff) == want


def test_rubbish_in_the_header_is_skipped_not_returned():
    assert r("172.18.0.7", "not-an-ip, 203.0.113.5, 172.18.0.1") == "203.0.113.5"


def test_a_header_of_pure_rubbish_falls_back_to_the_peer():
    assert r("172.18.0.7", "banana, , ;;;") == "172.18.0.7"


def test_an_all_internal_chain_falls_back_to_the_peer():
    """An internal call — a health check or one container talking to another."""
    assert r("172.18.0.7", "172.18.0.3, 172.18.0.1") == "172.18.0.7"


def test_a_huge_forged_header_neither_wins_nor_costs_us_anything():
    """Only the rightmost entries are examined, which is safe by construction: our own
    proxies append at the END, so the truth is always within the window and everything a
    client stuffs in sits to the left of it."""
    import time
    forged = ", ".join(["9.9.9.9"] * 5000)
    started = time.perf_counter()
    got = r("172.18.0.7", f"{forged}, 203.0.113.5, 172.18.0.1")
    assert got == "203.0.113.5", "5000 forged entries must not displace the real one"
    assert time.perf_counter() - started < 0.05, "the walk has to stay bounded"


def test_no_peer_at_all_resolves_to_nothing():
    assert client_ip.resolve(Req(None)) is None


def test_the_key_is_never_empty_even_when_nothing_can_be_resolved():
    """A limiter key of None would raise inside slowapi and take the request with it. A
    shared bucket throttles more than intended, never less."""
    assert client_ip.key_func(Req(None)) == "unknown"


def test_a_broken_headers_object_does_not_break_the_request():
    class Hostile:
        client = type("C", (), {"host": "172.18.0.7"})()
        @property
        def headers(self):
            raise RuntimeError("malformed")
    assert client_ip.resolve(Hostile()) == "172.18.0.7"


# ── configuration ────────────────────────────────────────────────────────────
def test_the_trusted_list_can_be_narrowed(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "127.0.0.1", raising=False)
    client_ip._cache = None
    # 172.18.0.7 is no longer ours, so its header must not be believed.
    assert r("172.18.0.7", "203.0.113.5") == "172.18.0.7"
    assert r("127.0.0.1", "203.0.113.5") == "203.0.113.5"
    client_ip._cache = None


def test_a_nonsense_entry_in_the_setting_is_ignored_not_fatal(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "127.0.0.1,banana", raising=False)
    client_ip._cache = None
    assert r("127.0.0.1", "203.0.113.5") == "203.0.113.5"
    client_ip._cache = None


# ── both callers really use it ───────────────────────────────────────────────
def test_the_rate_limiter_is_wired_to_this_resolver():
    from app.services import rate_limit_service
    assert rate_limit_service.limiter._key_func is client_ip.key_func


def test_the_audit_log_records_the_unforgeable_address():
    """It used to take the FIRST header entry — the one the client writes — so anyone
    could choose the address recorded against their own actions."""
    from app.services import audit_service
    got = audit_service._client_ip(Req("172.18.0.7", "9.9.9.9, 203.0.113.5, 172.18.0.1"))
    assert got == "203.0.113.5"
    assert got != "9.9.9.9", "the forged entry must never be what gets logged"
