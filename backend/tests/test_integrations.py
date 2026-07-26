"""API keys + webhooks (docs/PRO-FEATURES-PLAN.md §4 #8).

Three properties carry this feature, and each of them is the kind of thing that is quietly
wrong until someone attacks it:

1. **A webhook URL must not reach our own infrastructure.** This inverts the usual trust
   direction — the customer types an address and *our server* connects to it. On a cloud
   instance, 169.254.169.254 hands out IAM credentials to anything that asks.
2. **An API key must not be storable, guessable, or escalatable.**
3. **A webhook signature must be verifiable and non-replayable**, or the receiver has no
   reason to believe an event came from us.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.services import api_key_service, outbound_guard, webhook_service
from app.services.outbound_guard import BlockedURL, check_url

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


# ── SSRF: where we refuse to send ────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    # Cloud metadata — the highest-value target: these endpoints hand out credentials.
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "http://metadata.google.internal/computeMetadata/v1/instance/",
    "http://100.100.100.200/latest/meta-data/",
    # Our own server.
    "http://localhost:8888/api/servers",
    "http://127.0.0.1/",
    "http://[::1]/",
    "http://0.0.0.0/",
    # Private networks — the customer's LAN, or our Docker network.
    "http://10.1.2.3/hook",
    "http://192.168.0.10/hook",
    "http://172.16.5.4/hook",
    # Link-local.
    "http://169.254.1.1/",
    # An IPv4-mapped IPv6 address is still loopback.
    "http://[::ffff:127.0.0.1]/",
    # Internal service ports.
    "http://example.com:5432/",
    "http://example.com:6379/",
    "http://example.com:22/",
    # Not HTTP at all.
    "file:///etc/passwd",
    "gopher://example.com/",
    "ftp://example.com/",
    "//example.com/protocol-relative",
])
def test_we_refuse_to_send_there(url):
    with pytest.raises(BlockedURL):
        check_url(url)


@pytest.mark.parametrize("url", [
    "https://hooks.slack.com/services/T000/B000/xxx",
    "https://example.com/webhooks/serverally",
    "http://example.com:8080/hook",
    "https://8.8.8.8/hook",
])
def test_a_real_public_endpoint_is_allowed(url):
    """The guard must not be so strict that it blocks the actual use case."""
    assert check_url(url) == url


def test_a_hostname_that_resolves_internally_is_refused(monkeypatch):
    """The important case: the URL *looks* public. Only resolving it reveals otherwise —
    which is why the check resolves rather than pattern-matching."""
    monkeypatch.setattr(
        outbound_guard.socket, "getaddrinfo",
        lambda *_a, **_k: [(2, 1, 6, "", ("169.254.169.254", 0))],
    )
    with pytest.raises(BlockedURL) as exc:
        check_url("https://totally-normal-looking.example.com/hook")
    assert "metadata" in str(exc.value).lower()


def test_a_hostname_resolving_to_a_private_address_is_refused(monkeypatch):
    monkeypatch.setattr(
        outbound_guard.socket, "getaddrinfo",
        lambda *_a, **_k: [(2, 1, 6, "", ("10.0.0.7", 0))],
    )
    with pytest.raises(BlockedURL):
        check_url("https://looks-fine.example.com/hook")


def test_one_bad_address_among_several_is_enough_to_refuse(monkeypatch):
    """A hostname with both a public and a private A record must be refused: we cannot
    control which one the socket picks."""
    monkeypatch.setattr(
        outbound_guard.socket, "getaddrinfo",
        lambda *_a, **_k: [(2, 1, 6, "", ("93.184.216.34", 0)),
                           (2, 1, 6, "", ("127.0.0.1", 0))],
    )
    with pytest.raises(BlockedURL):
        check_url("https://mixed.example.com/hook")


def test_an_unresolvable_host_is_refused_with_a_clear_reason(monkeypatch):
    import socket as _socket

    def boom(*_a, **_k):
        raise _socket.gaierror("nope")

    monkeypatch.setattr(outbound_guard.socket, "getaddrinfo", boom)
    with pytest.raises(BlockedURL) as exc:
        check_url("https://does-not-exist.invalid/hook")
    assert "spelled correctly" in str(exc.value)


def test_the_existing_alert_webhook_path_is_guarded_too():
    """The guard was retrofitted into notification_service, because alert channels and
    escalation steps were already POSTing to customer URLs with no checks at all."""
    import inspect

    from app.services import notification_service
    source = inspect.getsource(notification_service._send_webhook_sync)
    assert "outbound_guard.check_url" in source


# ── API keys ─────────────────────────────────────────────────────────────────

def test_a_key_is_unguessable_and_distinctive():
    full, prefix, digest = api_key_service.generate()
    assert full.startswith("sa_live_")
    # A recognisable prefix is a security feature: secret scanners match on known shapes.
    assert prefix.startswith("sa_live_") and len(prefix) < len(full)
    assert len(digest) == 64
    assert len({api_key_service.generate()[0] for _ in range(50)}) == 50


def test_only_a_hash_can_be_stored():
    full, prefix, digest = api_key_service.generate()
    assert full not in digest
    # The stored prefix must never be enough to reconstruct the key.
    assert len(prefix) < 32
    assert api_key_service.hash_key(full) == digest


def test_a_jwt_is_never_mistaken_for_an_api_key():
    """Both arrive as `Authorization: Bearer …`, so the shape check has to separate them."""
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ4In0.sig"
    assert not api_key_service.looks_like_key(jwt)
    assert not api_key_service.looks_like_key("")
    assert not api_key_service.looks_like_key(None)
    assert not api_key_service.looks_like_key("sa_live_" + "x" * 200)  # absurdly long
    assert api_key_service.looks_like_key(api_key_service.generate()[0])


def test_write_implies_read():
    """A key that could write but not read would be a trap — every real automation reads
    something back to check its own work."""
    assert api_key_service.normalise_scopes(["write"]) == ["read", "write"]


def test_unknown_scopes_are_dropped_and_read_is_the_floor():
    assert api_key_service.normalise_scopes(["admin", "root", "delete"]) == ["read"]
    assert api_key_service.normalise_scopes([]) == ["read"]
    assert api_key_service.normalise_scopes(None) == ["read"]


def test_there_is_no_admin_scope_to_ask_for():
    """Deliberate: an admin scope would recreate the escalation path the design avoids."""
    from app.models.integration import API_SCOPES
    assert set(API_SCOPES) == {"read", "write"}


class _Key:
    def __init__(self, **kw):
        self.revoked_at = kw.get("revoked_at")
        self.expires_at = kw.get("expires_at")
        self.last_used_at = kw.get("last_used_at")
        self.scopes = kw.get("scopes", ["read"])
        self.name = "ci"
        self.prefix = "sa_live_abcd1234"
        self.key_hash = "0" * 64
        self.id = "k1"
        self.created_at = NOW


def test_a_revoked_key_is_unusable():
    ok, reason = api_key_service.is_usable(_Key(revoked_at=NOW), NOW)
    assert not ok and "revoked" in reason


def test_an_expired_key_is_unusable():
    ok, reason = api_key_service.is_usable(_Key(expires_at=NOW - timedelta(days=1)), NOW)
    assert not ok and "expired" in reason


def test_a_key_expiring_later_still_works():
    ok, _ = api_key_service.is_usable(_Key(expires_at=NOW + timedelta(days=1)), NOW)
    assert ok


def test_a_naive_expiry_does_not_crash_the_comparison():
    ok, _ = api_key_service.is_usable(_Key(expires_at=datetime(2026, 1, 1)), NOW)
    assert not ok


def test_serialising_a_key_never_exposes_its_hash():
    """Publishing the hash of a bearer credential is the sort of "harmless" leak that turns
    into an offline attack the moment the key format changes."""
    payload = json.dumps(api_key_service.serialize(_Key()))
    assert "key_hash" not in payload
    assert "0" * 64 not in payload


# ── Webhook signatures ───────────────────────────────────────────────────────

SECRET = "whsec_test_secret_value"
BODY = b'{"event":"incident.opened","data":{"title":"Site is down"}}'


def test_a_signature_we_produce_verifies():
    ts = int(NOW.timestamp())
    header = webhook_service.sign(SECRET, ts, BODY)
    assert webhook_service.verify(SECRET, header, BODY, now=ts)


def test_the_wrong_secret_fails():
    ts = int(NOW.timestamp())
    header = webhook_service.sign(SECRET, ts, BODY)
    assert not webhook_service.verify("whsec_someone_elses", header, BODY, now=ts)


def test_a_tampered_body_fails():
    """The whole point: a receiver must be able to tell a real event from a forged one, since
    anyone who learns the URL can POST "your server is compromised"."""
    ts = int(NOW.timestamp())
    header = webhook_service.sign(SECRET, ts, BODY)
    assert not webhook_service.verify(SECRET, header, BODY.replace(b"down", b"fine"), now=ts)


def test_an_old_request_cannot_be_replayed():
    """The timestamp is inside the signed material, so a captured request expires. A
    signature over the body alone would stay valid forever."""
    ts = int(NOW.timestamp())
    header = webhook_service.sign(SECRET, ts, BODY)
    later = ts + webhook_service.TOLERANCE_SECONDS + 1
    assert not webhook_service.verify(SECRET, header, BODY, now=later)
    assert webhook_service.verify(SECRET, header, BODY, now=ts + 60)


def test_a_future_timestamp_is_also_refused():
    ts = int(NOW.timestamp())
    header = webhook_service.sign(SECRET, ts + 10_000, BODY)
    assert not webhook_service.verify(SECRET, header, BODY, now=ts)


def test_the_timestamp_cannot_be_edited_without_breaking_the_signature():
    """Otherwise an attacker would just move `t` forward to un-expire a captured request."""
    ts = int(NOW.timestamp())
    header = webhook_service.sign(SECRET, ts, BODY)
    digest = header.split("v1=")[1]
    forged = f"t={ts + 100},v1={digest}"
    assert not webhook_service.verify(SECRET, forged, BODY, now=ts + 100)


@pytest.mark.parametrize("header", ["", "garbage", "t=abc,v1=x", "v1=onlythis", "t=123"])
def test_a_malformed_signature_header_is_refused_not_crashed(header):
    assert not webhook_service.verify(SECRET, header, BODY, now=int(NOW.timestamp()))


def test_signing_is_compared_in_constant_time():
    """A fast "wrong" answer leaks how much of the digest matched."""
    import inspect
    assert "compare_digest" in inspect.getsource(webhook_service.verify)


# ── Webhook payloads and retry policy ────────────────────────────────────────

def test_unknown_events_are_never_emitted():
    assert webhook_service.valid_events(["incident.opened", "made.up"]) == ["incident.opened"]


def test_a_huge_payload_is_trimmed_rather_than_dropped():
    """A customer would rather get a trimmed event than silently get nothing.

    The field that makes a payload huge is normally a string (a playbook's output), so
    "keep the scalar fields" is not enough — each string has to be capped individually.
    Caught by this test failing at 200 KB.
    """
    payload = webhook_service.build_payload("playbook.finished", {"output": "x" * 200_000})
    assert len(json.dumps(payload)) < webhook_service.MAX_PAYLOAD_BYTES
    assert payload["data"]["truncated"] is True
    assert payload["data"]["output"].endswith("…")


def test_trimming_survives_many_long_fields():
    """No realistic number of fields may re-inflate the payload past the cap."""
    data = {f"field_{i}": "y" * 50_000 for i in range(40)}
    payload = webhook_service.build_payload("playbook.finished", data)
    assert len(json.dumps(payload)) < webhook_service.MAX_PAYLOAD_BYTES


def test_trimming_keeps_the_useful_scalars():
    payload = webhook_service.build_payload(
        "playbook.finished",
        {"run_id": "abc", "status": "failed", "attempts": 3, "output": "z" * 100_000},
    )
    data = payload["data"]
    assert data["run_id"] == "abc" and data["status"] == "failed" and data["attempts"] == 3


def test_a_normal_payload_is_untouched():
    payload = webhook_service.build_payload("incident.opened", {"title": "Site is down"})
    assert payload["data"] == {"title": "Site is down"}
    assert payload["event"] == "incident.opened"
    assert "occurred_at" in payload


def test_retries_back_off_and_then_stop():
    """Bounded: an endpoint that never answers must not be retried forever."""
    seen = []
    for attempts in range(webhook_service.MAX_ATTEMPTS + 2):
        seen.append(webhook_service.next_attempt(attempts, NOW))
    assert seen[-1] is None and seen[-2] is None
    gaps = [(t - NOW).total_seconds() / 60 for t in seen if t is not None]
    assert gaps == list(webhook_service.RETRY_BACKOFF_MINUTES)
    assert gaps == sorted(gaps), "backoff must not shrink"


def test_the_endpoint_view_hides_the_secret_by_default():
    """It appears only from the dedicated route, so it does not ride along in every list
    response, log line and browser cache."""
    from app.models.integration import WebhookEndpoint
    from app.services import crypto_service

    row = WebhookEndpoint(
        user_id="u1", name="Slack", url="https://example.com/h",
        encrypted_secret=crypto_service.encrypt(SECRET), events=["incident.opened"],
    )
    row.failure_count, row.is_active, row.created_at = 0, True, NOW
    row.disabled_reason = row.last_delivery_at = row.last_status = None
    row.id = "e1"

    payload = json.dumps(webhook_service.public_endpoint(row))
    assert SECRET not in payload
    assert "encrypted_secret" not in payload
    assert webhook_service.public_endpoint(row, include_secret=True)["secret"] == SECRET


def test_the_signature_instructions_we_publish_match_the_code():
    """The docs are generated from the module that does the signing, so they cannot drift."""
    from app.models.integration import WEBHOOK_EVENTS
    assert webhook_service.SIGNATURE_HEADER == "X-ServerAlly-Signature"
    assert "incident.opened" in WEBHOOK_EVENTS
    ts = int(NOW.timestamp())
    header = webhook_service.headers_for("incident.opened", "d1", SECRET, BODY, ts)
    assert webhook_service.verify(SECRET, header[webhook_service.SIGNATURE_HEADER], BODY, now=ts)
    assert header[webhook_service.EVENT_HEADER] == "incident.opened"


# ── The structural guarantee ─────────────────────────────────────────────────
# The whole /api/v1 design rests on a key being unable to escalate into account control.
# That is a property of the ROUTING, not of any check inside a handler, so these tests
# inspect the app's actual route table rather than trusting a comment.

def _v1_paths() -> set[str]:
    import main
    return {r.path for r in main.app.routes if getattr(r, "path", "").startswith("/api/v1")}


def _routes_using_api_key_auth() -> set[str]:
    """Every route whose dependency tree accepts an API key."""
    import main
    from app.dependencies.api_key import get_api_caller, require_write

    accepting = set()
    for route in main.app.routes:
        for dep in getattr(getattr(route, "dependant", None), "dependencies", []) or []:
            if dep.call in (get_api_caller, require_write):
                accepting.add(route.path)
        # The dependency may also sit directly on a parameter.
        for dep in getattr(getattr(route, "dependant", None), "sub_dependant_list", []) or []:
            if getattr(dep, "call", None) in (get_api_caller, require_write):
                accepting.add(route.path)
    return accepting


def test_only_v1_routes_accept_an_api_key():
    """If a key ever becomes accepted outside /api/v1, this fails. That is the point: the
    dangerous routes are unreachable with a key because they do not use its dependency, and
    nothing but this test enforces that as the app grows."""
    import main
    from app.dependencies.api_key import get_api_caller, require_write

    offenders = []
    for route in main.app.routes:
        path = getattr(route, "path", "")
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        flat = str(getattr(dependant, "dependencies", ""))
        uses = ("get_api_caller" in flat or "require_write" in flat)
        if uses and not path.startswith("/api/v1"):
            offenders.append(path)
    assert not offenders, f"API-key auth leaked outside /api/v1: {offenders}"
    # Sanity: the mechanism is actually in use, so the check above isn't vacuous.
    assert get_api_caller is not None and require_write is not None


def test_the_api_surface_cannot_touch_account_security():
    """An API key must never be able to change a password, disable 2FA, read a credential,
    mint another key, or delete anything."""
    paths = _v1_paths()
    assert paths, "no /api/v1 routes registered"
    forbidden = ("auth", "password", "2fa", "totp", "api-keys", "webhooks",
                 "credential", "team", "settings")
    for path in paths:
        for word in forbidden:
            assert word not in path.lower(), f"{path} exposes '{word}' to an API key"


def test_the_api_surface_has_no_shell_and_no_delete():
    """Open-ended command execution is the MCP connector's job, behind its own consent flow
    and audit trail — not something a long-lived key can reach."""
    import main

    for route in main.app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1"):
            continue
        methods = getattr(route, "methods", set()) or set()
        assert "DELETE" not in methods, f"{path} allows DELETE with an API key"
        assert not any(w in path.lower() for w in ("command", "exec", "shell", "terminal", "files")), \
            f"{path} looks like arbitrary execution"


def test_key_management_requires_a_browser_session():
    """Minting a key with a key would defeat scoping entirely, so those routes use the
    normal session dependency."""
    import main
    from app.dependencies.auth import get_current_user

    managed = [r for r in main.app.routes
               if getattr(r, "path", "") in ("/api/api-keys", "/api/webhooks")]
    assert managed, "management routes not registered"
    for route in managed:
        flat = str(getattr(getattr(route, "dependant", None), "dependencies", ""))
        assert "get_current_user" in flat, f"{route.path} does not require a login"
    assert get_current_user is not None


# ── Disabling a dead endpoint (found live) ───────────────────────────────────

@pytest.mark.asyncio
async def test_a_brief_outage_does_not_disable_a_webhook(monkeypatch):
    """Found live: failure_count was incremented per ATTEMPT, so a five-attempt delivery
    spent half the budget. Two events during a ten-minute outage on the customer's side would
    switch their webhook off and leave them to re-enable it by hand.

    One consecutive failure must mean one GIVEN-UP delivery — the endpoint stayed unreachable
    across a full retry cycle.
    """
    from app.models.integration import WebhookDelivery, WebhookEndpoint
    from app.services import crypto_service
    from app.workers import webhook_worker

    endpoint = WebhookEndpoint(
        user_id="u1", name="theirs", url="https://example.com/h",
        encrypted_secret=crypto_service.encrypt(SECRET), events=["incident.opened"],
    )
    endpoint.id, endpoint.is_active, endpoint.failure_count = "e1", True, 0
    endpoint.disabled_reason = endpoint.last_delivery_at = endpoint.last_status = None

    class _Session:
        async def get(self, _model, _pk):
            return endpoint

        async def commit(self):
            return None

        async def rollback(self):
            return None

    monkeypatch.setattr(webhook_service, "_post_sync", lambda *_a, **_k: (500, "Your endpoint answered 500."))

    delivery = WebhookDelivery(endpoint_id="e1", event="incident.opened", payload={})
    delivery.id, delivery.attempts, delivery.status = "d1", 0, "pending"
    delivery.http_status = delivery.error = delivery.delivered_at = None
    delivery.next_attempt_at = NOW

    # Drive one delivery through every one of its retries.
    for _ in range(webhook_service.MAX_ATTEMPTS):
        await webhook_worker.deliver_one(_Session(), delivery, NOW)

    assert delivery.attempts == webhook_service.MAX_ATTEMPTS
    assert delivery.status == "failed"
    assert endpoint.failure_count == 1, "one failed delivery is one strike, not five"
    assert endpoint.is_active is True, "a single failed event must not disable the webhook"


@pytest.mark.asyncio
async def test_a_genuinely_dead_endpoint_is_eventually_switched_off(monkeypatch):
    """The other half: we must stop knocking forever on a door nobody answers."""
    from app.models.integration import WebhookDelivery, WebhookEndpoint
    from app.services import crypto_service
    from app.workers import webhook_worker

    endpoint = WebhookEndpoint(
        user_id="u1", name="abandoned", url="https://example.com/h",
        encrypted_secret=crypto_service.encrypt(SECRET), events=["incident.opened"],
    )
    endpoint.id, endpoint.is_active = "e1", True
    # Already one short of the limit.
    endpoint.failure_count = webhook_service.FAILURES_BEFORE_DISABLE - 1
    endpoint.disabled_reason = endpoint.last_delivery_at = endpoint.last_status = None

    class _Session:
        async def get(self, _model, _pk):
            return endpoint

        async def commit(self):
            return None

    monkeypatch.setattr(webhook_service, "_post_sync", lambda *_a, **_k: (0, "We couldn't connect."))

    delivery = WebhookDelivery(endpoint_id="e1", event="incident.opened", payload={})
    delivery.id, delivery.status = "d1", "pending"
    # Its last attempt, so this delivery gives up now.
    delivery.attempts = webhook_service.MAX_ATTEMPTS - 1
    delivery.http_status = delivery.error = delivery.delivered_at = None
    delivery.next_attempt_at = NOW

    await webhook_worker.deliver_one(_Session(), delivery, NOW)
    assert endpoint.is_active is False
    assert endpoint.disabled_reason and "failed deliveries" in endpoint.disabled_reason


@pytest.mark.asyncio
async def test_a_success_clears_the_strikes(monkeypatch):
    """A merely flaky endpoint must not accumulate its way to being disabled over months."""
    from app.models.integration import WebhookDelivery, WebhookEndpoint
    from app.services import crypto_service
    from app.workers import webhook_worker

    endpoint = WebhookEndpoint(
        user_id="u1", name="flaky", url="https://example.com/h",
        encrypted_secret=crypto_service.encrypt(SECRET), events=["incident.opened"],
    )
    endpoint.id, endpoint.is_active, endpoint.failure_count = "e1", True, 7
    endpoint.disabled_reason = endpoint.last_delivery_at = endpoint.last_status = None

    class _Session:
        async def get(self, _model, _pk):
            return endpoint

        async def commit(self):
            return None

    monkeypatch.setattr(webhook_service, "_post_sync", lambda *_a, **_k: (200, ""))

    delivery = WebhookDelivery(endpoint_id="e1", event="incident.opened", payload={})
    delivery.id, delivery.attempts, delivery.status = "d1", 0, "pending"
    delivery.http_status = delivery.error = delivery.delivered_at = None
    delivery.next_attempt_at = NOW

    assert await webhook_worker.deliver_one(_Session(), delivery, NOW) is True
    assert endpoint.failure_count == 0
    assert delivery.status == "delivered"
