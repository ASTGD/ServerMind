"""Metric alerts: one message when it breaks, one when it recovers, nothing in between.

An alert with no matching all-clear is worse than no alert — the person told their disk was
filling has to go and check whether it still is, which is the work they bought this to
avoid. But a recovery notice that repeats every sweep is just as bad, so the transition is
what matters, and that is what these tests pin.

Deterministic — no Postgres, no SMTP. The session is faked; what is under test is the
worker's state machine.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.workers import alert_worker


class _Alert:
    """Stand-in for the Alert row, mutable so the fake UPDATE can be applied to it."""

    def __init__(self, *, threshold=80.0, condition="gt", is_breaching=False,
                 last_triggered=None):
        self.id = uuid.uuid4()
        self.user_id = uuid.uuid4()
        self.metric = "disk"
        self.condition = condition
        self.threshold = threshold
        self.channel = "email"
        self.channel_target = "owner@example.com"
        self.is_active = True
        self.last_triggered = last_triggered
        self.is_breaching = is_breaching


class _Metric:
    def __init__(self, disk):
        self.cpu_percent = None
        self.ram_percent = None
        self.disk_percent = disk
        self.recorded_at = datetime.now(tz=timezone.utc)


class _Server:
    def __init__(self):
        self.id = uuid.uuid4()
        self.name = "web1"


class _Rows:
    def __init__(self, value):
        self._v = value

    def scalar_one_or_none(self):
        return self._v

    def scalars(self):
        return self

    def all(self):
        return self._v


class _FakeSession:
    """Serves the three SELECTs the worker makes, and applies its UPDATEs to the object."""

    def __init__(self, metric, server, alerts):
        self._queue = [_Rows(metric), _Rows(server), _Rows(alerts)]
        self._alerts = alerts
        self.updates: list[dict] = []

    async def execute(self, stmt):
        if self._queue:
            return self._queue.pop(0)
        # An UPDATE — capture it and apply so later logic sees the new state.
        # Keys are Column objects: `str(col)` is "alerts.is_breaching", so use `.name` or
        # the attribute never lands on the object and every assertion here passes vacuously.
        values = dict(getattr(stmt, "_values", {}) or {})
        applied = {
            getattr(k, "name", str(k)): (v.value if hasattr(v, "value") else v)
            for k, v in values.items()
        }
        self.updates.append(applied)
        for a in self._alerts:
            for k, v in applied.items():
                setattr(a, k, v)
        return _Rows(None)

    async def commit(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def wired(monkeypatch):
    """Capture what would have been sent, without sending anything."""
    sent = {"alerts": [], "recoveries": [], "resolved": []}

    async def fake_fire_alert(alert, name, value):
        sent["alerts"].append((name, round(value, 1)))

    async def fake_fire_recovery(alert, name, value):
        sent["recoveries"].append((name, round(value, 1)))

    async def fake_resolve_key(db, user_id, key):
        sent["resolved"].append(key)

    async def fake_raise_for(*a, **k):
        return None  # no escalation policy — the ordinary one-shot alert path

    import app.services.incident_service as incident_service
    import app.services.notification_service as notification_service
    monkeypatch.setattr(notification_service, "fire_alert", fake_fire_alert)
    monkeypatch.setattr(notification_service, "fire_recovery", fake_fire_recovery)
    monkeypatch.setattr(incident_service, "resolve_key", fake_resolve_key)
    monkeypatch.setattr(incident_service, "raise_for", fake_raise_for)
    return sent


async def _run(monkeypatch, *, disk, alert):
    server = _Server()
    session = _FakeSession(_Metric(disk), server, [alert])
    monkeypatch.setattr(alert_worker, "AsyncSessionLocal", lambda: session)
    await alert_worker.check_alerts_for_server(str(server.id))
    return session


@pytest.mark.asyncio
async def test_breach_notifies_and_records_the_state(wired, monkeypatch):
    alert = _Alert(threshold=80.0)
    await _run(monkeypatch, disk=91.0, alert=alert)
    assert wired["alerts"] == [("web1", 91.0)], "a fresh breach must notify"
    assert alert.is_breaching is True, "the breach must be recorded for the recovery check"


@pytest.mark.asyncio
async def test_recovery_notifies_exactly_once(wired, monkeypatch):
    alert = _Alert(threshold=80.0, is_breaching=True,
                   last_triggered=datetime.now(tz=timezone.utc) - timedelta(hours=2))
    await _run(monkeypatch, disk=42.0, alert=alert)
    assert wired["recoveries"] == [("web1", 42.0)], "coming back under the threshold must say so"
    assert alert.is_breaching is False

    # Second sweep, still healthy — silence.
    wired["recoveries"].clear()
    await _run(monkeypatch, disk=41.0, alert=alert)
    assert wired["recoveries"] == [], "a recovered alert must not keep announcing itself"


@pytest.mark.asyncio
async def test_a_never_breached_alert_never_sends_a_recovery(wired, monkeypatch):
    """The common case: a healthy server with an alert rule should be totally silent."""
    alert = _Alert(threshold=80.0, is_breaching=False)
    await _run(monkeypatch, disk=12.0, alert=alert)
    assert wired["recoveries"] == []
    assert wired["alerts"] == []


@pytest.mark.asyncio
async def test_a_breach_silenced_by_cooldown_produces_no_recovery(wired, monkeypatch):
    """Never announce the end of something we never announced the start of.

    A breach inside the cooldown window is deliberately not sent, so it must also not set
    the breaching flag — otherwise the customer gets "disk is back to normal" about a
    problem they were never told about, which reads like a bug in our monitoring.
    """
    alert = _Alert(threshold=80.0, is_breaching=False,
                   last_triggered=datetime.now(tz=timezone.utc) - timedelta(minutes=5))
    await _run(monkeypatch, disk=95.0, alert=alert)
    assert wired["alerts"] == [], "cooldown should suppress the breach notice"
    assert alert.is_breaching is False, "a silenced breach must not arm a recovery message"

    await _run(monkeypatch, disk=10.0, alert=alert)
    assert wired["recoveries"] == [], "so recovering from it stays silent too"


@pytest.mark.asyncio
async def test_recovery_still_clears_the_flag_when_sending_fails(monkeypatch):
    """A broken mail server must not leave the alert stuck 'breaching' forever.

    If the flag survived a send failure, the rule would try to send a recovery on every
    single sweep from then on.
    """
    sent = {"resolved": []}

    async def boom(alert, name, value):
        raise RuntimeError("smtp down")

    async def fake_resolve_key(db, user_id, key):
        sent["resolved"].append(key)

    async def fake_raise_for(*a, **k):
        return None

    import app.services.incident_service as incident_service
    import app.services.notification_service as notification_service
    monkeypatch.setattr(notification_service, "fire_recovery", boom)
    monkeypatch.setattr(incident_service, "resolve_key", fake_resolve_key)
    monkeypatch.setattr(incident_service, "raise_for", fake_raise_for)

    alert = _Alert(threshold=80.0, is_breaching=True)
    await _run(monkeypatch, disk=20.0, alert=alert)
    assert alert.is_breaching is False, "the flag must clear even if the notice could not be sent"


@pytest.mark.asyncio
async def test_recovery_works_for_a_below_threshold_rule(wired, monkeypatch):
    """`lt` rules exist too — "alert me if free memory drops" is the same machinery."""
    alert = _Alert(threshold=20.0, condition="lt", is_breaching=True)
    await _run(monkeypatch, disk=55.0, alert=alert)
    assert wired["recoveries"] == [("web1", 55.0)]
