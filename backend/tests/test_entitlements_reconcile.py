"""Reconciliation — the only thing that detects billing drift (SAAS-LAUNCH-PLAN §3.3).

Renewal is silence: a paying customer's renewal calls nothing, so a MISSED suspend
leaves a non-paying customer on Pro forever and nobody ever complains. WHMCS pushes
the full truth nightly; this endpoint makes reality match.

It can also mass-downgrade every customer, so most of these tests are about the
guards, not the happy path: a truncated or empty billing list must never empty the
customer base, and a refusal must be LOUD (a silent 200 would recreate the very
failure the endpoint exists to catch).
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.routers import entitlements
from main import app

KEY = "test-reconcile-key"
HEADERS = {"X-Entitlement-Key": KEY}


class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def scalars(self): return self
    def all(self): return self._rows


class _FakeSession:
    """Stands in for the DB: returns a fixed user set, records commits.

    The endpoint's logic (who upgrades, who downgrades, the guards) is pure over the
    rows it gets back, so a fake keeps these tests offline and deterministic.
    """

    def __init__(self, users): self.users, self.commits = users, 0
    async def execute(self, _q): return _FakeResult(self.users)
    async def commit(self): self.commits += 1
    def add(self, _obj): pass


def _user(email: str, plan: str, is_admin: bool = False) -> User:
    u = User()
    u.id, u.email, u.plan, u.is_admin = uuid.uuid4(), email, plan, is_admin
    return u


@pytest.fixture
def users() -> list[User]:
    # 10 Pro so the 20% ratio guard allows 3 downgrades (max(floor=3, 20% of 10 = 2)).
    return [_user(f"pro{i}@x.com", "pro") for i in range(10)] + [_user("free1@x.com", "free")]


@pytest.fixture
async def client(users, monkeypatch):
    monkeypatch.setattr(settings, "ENTITLEMENT_API_KEY", KEY)
    session = _FakeSession(users)
    app.dependency_overrides[get_db] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        c.session = session  # type: ignore[attr-defined]
        yield c
    app.dependency_overrides.clear()


async def _post(client, **body):
    return await client.post("/api/admin/entitlements/reconcile", json=body, headers=HEADERS)


# ── Auth ─────────────────────────────────────────────────────────────────────

async def test_reconcile_requires_the_key(client, users):
    r = await client.post("/api/admin/entitlements/reconcile",
                          json={"active_pro_emails": ["pro0@x.com"]},
                          headers={"X-Entitlement-Key": "wrong"})
    assert r.status_code == 401


# ── The guards (the reason this endpoint is dangerous) ───────────────────────

async def test_empty_list_is_refused(client, users):
    """A billing query that returns nothing is a bug, not "we lost every customer"."""
    r = await _post(client, active_pro_emails=[])
    assert r.status_code == 422
    assert "every customer" in r.json()["detail"]
    assert all(u.plan == "pro" for u in users[:10])   # nothing changed
    assert client.session.commits == 0


async def test_a_truncated_list_is_refused_loudly(client, users):
    """The real failure mode: WHMCS returns 2 of 10 Pro customers. Downgrading 8 would
    be catastrophic and silent — it must 409, not 200."""
    r = await _post(client, active_pro_emails=["pro0@x.com", "pro1@x.com"])
    assert r.status_code == 409
    d = r.json()["detail"]
    assert d["would_downgrade"] == 8 and d["allowed_without_force"] == 3
    assert all(u.plan == "pro" for u in users[:10])   # untouched
    assert client.session.commits == 0


async def test_normal_churn_is_allowed(client, users):
    """3 of 10 churning is plausible — the guard must not block real work."""
    active = [f"pro{i}@x.com" for i in range(7)]
    r = await _post(client, active_pro_emails=active)
    assert r.status_code == 200
    assert len(r.json()["downgraded"]) == 3
    assert users[7].plan == "free" and users[0].plan == "pro"


async def test_force_overrides_the_guard(client, users):
    r = await _post(client, active_pro_emails=["pro0@x.com"], force=True)
    assert r.status_code == 200
    assert len(r.json()["downgraded"]) == 9


async def test_force_allows_an_empty_list(client, users):
    r = await _post(client, active_pro_emails=[], force=True)
    assert r.status_code == 200
    assert len(r.json()["downgraded"]) == 10


# ── Behaviour ────────────────────────────────────────────────────────────────

async def test_dry_run_changes_nothing(client, users):
    r = await _post(client, active_pro_emails=[f"pro{i}@x.com" for i in range(7)], dry_run=True)
    assert r.status_code == 200
    assert len(r.json()["downgraded"]) == 3        # reports what it WOULD do...
    assert all(u.plan == "pro" for u in users[:10])  # ...but touches nothing
    assert client.session.commits == 0


async def test_missed_create_event_is_healed(client, users):
    """The other direction: billing says paying, we have them on free."""
    active = [f"pro{i}@x.com" for i in range(10)] + ["free1@x.com"]
    r = await _post(client, active_pro_emails=active)
    assert r.json()["upgraded"] == ["free1@x.com"]
    assert users[10].plan == "pro"


async def test_admins_are_never_downgraded(client):
    """Staff are Pro by hand and don't exist in WHMCS — a nightly reconcile must not
    demote the team every night."""
    staff = _user("staff@serverally.com", "pro", is_admin=True)
    session = _FakeSession([staff] + [_user(f"pro{i}@x.com", "pro") for i in range(10)])
    app.dependency_overrides[get_db] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/admin/entitlements/reconcile",
                         json={"active_pro_emails": [f"pro{i}@x.com" for i in range(10)]},
                         headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["downgraded"] == []
    assert staff.plan == "pro"


async def test_unknown_emails_are_reported_never_created(client, users):
    """Provisioning stays with CreateAccount — it's the only event that can email the
    customer their claim link. Reconcile only reports the gap."""
    active = [f"pro{i}@x.com" for i in range(10)] + ["ghost@x.com"]
    r = await _post(client, active_pro_emails=active)
    assert r.json()["unknown"] == ["ghost@x.com"]
    assert r.json()["upgraded"] == []


async def test_is_idempotent(client, users):
    """The cron runs nightly — a no-drift run must be a clean no-op."""
    active = [f"pro{i}@x.com" for i in range(10)]
    r1 = await _post(client, active_pro_emails=active)
    r2 = await _post(client, active_pro_emails=active)
    for r in (r1, r2):
        assert r.json()["upgraded"] == [] and r.json()["downgraded"] == []
    assert client.session.commits == 0   # nothing to write == no write


async def test_email_case_and_whitespace_are_normalised(client, users):
    """WHMCS stores whatever the customer typed; we store lowercase."""
    active = [f"PRO{i}@X.com" for i in range(10)]
    r = await _post(client, active_pro_emails=active)
    assert r.json()["downgraded"] == [] and r.json()["unknown"] == []
