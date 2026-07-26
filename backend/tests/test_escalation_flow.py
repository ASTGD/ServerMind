"""Escalation end-to-end behaviour: raising, paging, acknowledging, resolving.

These use a fake session rather than Postgres (CI has no database), so what they pin is the
*logic* — which incidents the worker picks up, what it sends, and what stops it. The two
guarantees that need a real database (the partial unique index, and the encrypted-token
round trip) are verified live against Postgres instead.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.escalation import (
    STATUS_ACKNOWLEDGED, STATUS_OPEN, STATUS_RESOLVED, EscalationPolicy, Incident,
)
from app.services import escalation_service as esc
from app.services import incident_service
from app.workers import escalation_worker

T0 = datetime(2026, 7, 26, 3, 0, tzinfo=timezone.utc)


class FakeSession:
    """Just enough AsyncSession for these paths."""

    def __init__(self, objects: dict | None = None):
        self.objects = objects or {}
        self.added: list = []
        self.commits = 0

    async def get(self, _model, pk):
        return self.objects.get(pk)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None

    async def rollback(self):
        return None


def make_incident(**kw) -> Incident:
    inc = Incident(
        user_id=kw.get("user_id", "u1"), server_id=kw.get("server_id"),
        source=kw.get("source", "uptime"), dedup_key=kw.get("dedup_key", "uptime:m1"),
        title=kw.get("title", "Shop is down"), message=kw.get("message", ""),
        severity=kw.get("severity", "critical"), status=kw.get("status", STATUS_OPEN),
        policy_id=kw.get("policy_id", "p1"),
    )
    inc.step_index = kw.get("step_index", 0)
    inc.repeats_done = kw.get("repeats_done", 0)
    inc.notifications_sent = kw.get("notifications_sent", 0)
    inc.next_action_at = kw.get("next_action_at", T0)
    inc.last_notified_at = kw.get("last_notified_at")
    inc.created_at = kw.get("created_at", T0)
    inc.acknowledged_at = None
    inc.acknowledged_by = None
    inc.resolved_at = None
    inc.auto_resolved = False
    inc.ack_token_hash = None
    inc.ack_token_enc = None
    return inc


def make_policy(**kw) -> EscalationPolicy:
    p = EscalationPolicy(
        user_id="u1", name=kw.get("name", "On-call"),
        min_severity=kw.get("min_severity", "high"),
        repeat_minutes=kw.get("repeat_minutes", 15),
        max_repeats=kw.get("max_repeats", 3),
        is_default=True, is_active=kw.get("is_active", True),
    )
    p.id = "p1"
    return p


# ── Acknowledging stops the paging ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_acknowledging_stops_escalation_immediately():
    """The promise the whole feature rests on. Both the status and the schedule change, and
    the worker's query needs both, so there is no tick in which it can page again."""
    db, inc = FakeSession(), make_incident()
    await incident_service.acknowledge(db, inc, by="Sharwat")
    assert inc.status == STATUS_ACKNOWLEDGED
    assert inc.next_action_at is None
    assert inc.acknowledged_by == "Sharwat"


@pytest.mark.asyncio
async def test_acknowledging_does_not_resolve():
    """"I'm on it" is not "it's fixed" — the incident stays open in the list."""
    inc = make_incident()
    await incident_service.acknowledge(FakeSession(), inc, by="Sharwat")
    assert inc.status != STATUS_RESOLVED and inc.resolved_at is None


@pytest.mark.asyncio
async def test_acknowledging_twice_keeps_the_first_answer():
    """Two people following the same link must not rewrite who responded first."""
    inc = make_incident()
    await incident_service.acknowledge(FakeSession(), inc, by="Sharwat")
    await incident_service.acknowledge(FakeSession(), inc, by="Someone else")
    assert inc.acknowledged_by == "Sharwat"


@pytest.mark.asyncio
async def test_resolving_stops_escalation_even_without_an_acknowledgement():
    """The detector clearing is the most common way an incident ends — a site that came
    back up on its own must stop paging without anyone touching their phone."""
    inc = make_incident()
    await incident_service.resolve(FakeSession(), inc, auto=True)
    assert inc.status == STATUS_RESOLVED
    assert inc.next_action_at is None
    assert inc.auto_resolved is True


@pytest.mark.asyncio
async def test_a_manual_resolve_records_who_did_it():
    inc = make_incident()
    await incident_service.resolve(FakeSession(), inc, auto=False, by="Sharwat")
    assert inc.auto_resolved is False and inc.acknowledged_by == "Sharwat"


# ── The acknowledge token ────────────────────────────────────────────────────

def test_the_ack_token_is_unguessable_and_stored_only_as_a_hash():
    token, digest = incident_service.mint_ack_token()
    assert len(token) >= 32
    assert digest == incident_service.hash_ack_token(token)
    assert token not in digest
    # Distinct every time — a predictable token would let anyone silence any alert.
    assert len({incident_service.mint_ack_token()[0] for _ in range(50)}) == 50


def test_the_encrypted_token_round_trips_but_is_not_readable_at_rest():
    """Later rungs reach a different person who also needs the link, so the worker must be
    able to re-read the token — without it sitting in the database in the clear."""
    from app.services import crypto_service
    token, _ = incident_service.mint_ack_token()
    inc = make_incident()
    inc.ack_token_enc = crypto_service.encrypt(token)
    assert token not in inc.ack_token_enc
    assert incident_service.read_ack_token(inc) == token


def test_an_unreadable_token_does_not_stop_the_page():
    """A page with no shortcut link beats no page at all."""
    inc = make_incident()
    inc.ack_token_enc = "not-valid-ciphertext"
    assert incident_service.read_ack_token(inc) is None


@pytest.mark.asyncio
async def test_a_junk_token_is_rejected_without_a_database_lookup():
    """Cheap rejection, and no oracle: an over-long or empty token never reaches a query."""
    class Boom(FakeSession):
        async def execute(self, *_a, **_k):
            raise AssertionError("must not query for an obviously invalid token")

    assert await incident_service.acknowledge_by_token(Boom(), "") is None
    assert await incident_service.acknowledge_by_token(Boom(), "x" * 500) is None


# ── What the API may reveal ──────────────────────────────────────────────────

def test_serialising_an_incident_never_exposes_the_ack_token():
    """A field that gates silencing alerts has no business in a response body — not even
    as a hash. This is why serialize() is an allowlist rather than a model dump."""
    import json
    from app.services import crypto_service

    token, digest = incident_service.mint_ack_token()
    inc = make_incident()
    inc.id, inc.ack_token_hash, inc.ack_token_enc = "i1", digest, crypto_service.encrypt(token)

    payload = json.dumps(incident_service.serialize(inc))
    assert token not in payload
    assert digest not in payload
    assert inc.ack_token_enc not in payload
    assert "ack_token" not in payload


# ── The worker ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_worker_pages_and_advances(monkeypatch):
    inc, policy = make_incident(), make_policy()
    db = FakeSession({"p1": policy})

    monkeypatch.setattr(incident_service, "steps_for",
                        lambda *_a, **_k: _async([esc.Step(0, "sms", "+8801"), esc.Step(5, "sms", "+8802")]))
    sent: list[tuple] = []

    async def fake_deliver(_db, _uid, channel, target, subject, body):
        sent.append((channel, target, subject, body))
        return True, "sent"

    monkeypatch.setattr(escalation_worker.paging_service, "deliver", fake_deliver)

    assert await escalation_worker.process_incident(db, inc, T0) is True
    assert len(sent) == 1 and sent[0][:2] == ("sms", "+8801")
    assert inc.step_index == 1 and inc.notifications_sent == 1
    assert inc.next_action_at == T0 + timedelta(minutes=5)


@pytest.mark.asyncio
async def test_a_failed_channel_still_advances_the_ladder(monkeypatch):
    """The reason to have a second rung is that the first one can fail. Parking on a dead
    channel would mean the escalation never reaches anyone."""
    inc, policy = make_incident(), make_policy()
    db = FakeSession({"p1": policy})
    monkeypatch.setattr(incident_service, "steps_for",
                        lambda *_a, **_k: _async([esc.Step(0, "sms", "+8801"), esc.Step(5, "email", "me@co")]))
    monkeypatch.setattr(escalation_worker.paging_service, "deliver",
                        lambda *_a, **_k: _async((False, "Monthly SMS limit reached")))

    assert await escalation_worker.process_incident(db, inc, T0) is False
    assert inc.step_index == 1, "a failed step must not park the ladder"
    assert inc.notifications_sent == 0, "a failure must not count as a delivery"
    assert inc.next_action_at == T0 + timedelta(minutes=5)


@pytest.mark.asyncio
async def test_switching_a_policy_off_stops_an_in_flight_incident(monkeypatch):
    """Turning off on-call has to mean the paging stops now, not that incidents already
    escalating keep running on the old rules."""
    inc = make_incident()
    db = FakeSession({"p1": make_policy(is_active=False)})
    monkeypatch.setattr(escalation_worker.paging_service, "deliver",
                        lambda *_a, **_k: _async((True, "sent")))

    assert await escalation_worker.process_incident(db, inc, T0) is False
    assert inc.next_action_at is None


@pytest.mark.asyncio
async def test_a_deleted_policy_stops_escalation_rather_than_crashing(monkeypatch):
    inc = make_incident()
    inc.policy_id = None
    assert await escalation_worker.process_incident(FakeSession(), inc, T0) is False
    assert inc.next_action_at is None


# ── The message someone reads at 3am ─────────────────────────────────────────

def test_the_page_says_what_broke_where_and_how_to_stop_it():
    inc = make_incident(title="Shop is down", message="https://shop.com\nProblem: HTTP 502")
    subject, body = escalation_worker.build_page(inc, "web-01", "tok123", attempt=2, total=6)
    assert "CRITICAL" in subject and "Shop is down" in subject and "web-01" in subject
    assert "HTTP 502" in body
    assert "/ack/tok123" in body            # the one action that stops it
    assert "2 of at most 6" in body         # how much more paging is coming


def test_the_page_still_sends_without_an_ack_link():
    _subject, body = escalation_worker.build_page(
        make_incident(), None, None, attempt=1, total=1)
    assert "/ack/" not in body
    assert "Open in ServerAlly" in body


def test_the_page_does_not_invent_a_server_name():
    subject, _ = escalation_worker.build_page(make_incident(), None, "t", 1, 1)
    assert " on " not in subject


def test_the_server_name_is_never_repeated():
    """Found live: a monitor is usually named after the server it watches, so appending the
    server name unconditionally produced "FireVPS RDP is down on FireVPS RDP". Wasted words
    in an email, and wasted money in an SMS."""
    inc = make_incident(title="FireVPS RDP is down")
    subject, body = escalation_worker.build_page(inc, "FireVPS RDP", None, 1, 1)
    assert subject == "[CRITICAL] FireVPS RDP is down"
    assert body.splitlines()[0] == "FireVPS RDP is down"


def test_the_server_name_is_added_when_the_title_lacks_it():
    inc = make_incident(title="Certificate expires tomorrow")
    subject, _ = escalation_worker.build_page(inc, "web-01", None, 1, 1)
    assert subject.endswith("Certificate expires tomorrow on web-01")


def _async(value):
    """Wrap a value in an awaitable, for monkeypatching async functions."""
    async def _inner(*_a, **_k):
        return value
    return _inner()
