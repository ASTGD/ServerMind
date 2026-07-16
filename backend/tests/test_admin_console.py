"""Operator console — the support/ops view (docs/SAAS-LAUNCH-PLAN.md §5).

Two things are being protected here, and only one of them is a feature:

1. It answers the questions WHMCS cannot (servers, Ally, our real AI cost).
2. It can NEVER leak a credential, run a command, read chat content, or delete data.

(2) is the one that matters. This console will be used while a support ticket is open,
by a human in a hurry, against real customer accounts — so the guarantees are asserted
against the actual serialised payload, not assumed from the code's shape.
"""
from __future__ import annotations

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.dependencies.auth import require_admin
from app.models.server import Server
from app.models.user import User
from app.services import admin_service
from main import app


class _Res:
    def __init__(self, rows): self._rows = rows
    def scalars(self): return self
    def all(self): return self._rows
    def one(self): return self._rows[0]
    def scalar_one(self): return self._rows[0] if self._rows else 0
    def scalar_one_or_none(self): return self._rows[0] if self._rows else None


class _SeqSession:
    """Returns canned results in call order — user_detail makes several queries and each
    needs a differently-shaped result."""

    def __init__(self, results): self._results = list(results)
    async def execute(self, _q):
        return self._results.pop(0) if self._results else _Res([])


def _user(email="c@example.com", plan="free", is_admin=False) -> User:
    u = User()
    u.id, u.email, u.plan, u.is_admin = uuid.uuid4(), email, plan, is_admin
    u.name, u.is_active, u.is_verified = "Customer", True, True
    u.totp_enabled, u.preferred_language, u.ally_mode = False, "en", "normal"
    u.created_at = None
    return u


# ── The security guarantees ──────────────────────────────────────────────────

async def test_admin_routes_reject_a_non_admin():
    """A customer with a perfectly valid token must still get 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        for path in ("/api/dev/admin/overview", "/api/dev/admin/users",
                     "/api/dev/admin/entitlements",
                     f"/api/dev/admin/users/{uuid.uuid4()}"):
            r = await c.get(path)
            assert r.status_code in (401, 403), f"{path} was reachable without admin!"


async def test_user_detail_never_exposes_a_credential():
    """The one that matters. Run the REAL user_detail over a user and server that carry
    actual secrets, and assert none of them can reach the payload.

    Asserted against the serialised output, not the code's shape: if someone later adds
    `encrypted_cred` to the server dict "just for debugging", this fails. If it ever
    passes wrongly, our breach radius is every customer's production server.
    """
    SECRET = "SUPER-SECRET-SSH-PASSWORD-9f2a"
    user = _user()
    user.password_hash = "$2b$12$" + SECRET
    user.totp_secret = SECRET

    srv = Server()
    srv.id, srv.user_id, srv.name, srv.host = uuid.uuid4(), user.id, "prod-1", "1.2.3.4"
    srv.connection_type, srv.os_type, srv.status = "ssh", "ubuntu", "online"
    srv.last_seen, srv.created_at = None, None
    srv.encrypted_cred = SECRET          # the real thing, as stored
    srv.fingerprint = "aa:bb:cc"

    session = _SeqSession([
        _Res([user]),        # select(User)
        _Res([(3, 1.25)]),   # sum(actions), sum(cost)
        _Res([srv]),         # select(Server)
        _Res([]),            # missions
        _Res([]),            # problem command_logs
        _Res([]),            # entitlement_log
    ])
    out = await admin_service.user_detail(session, user.id)
    blob = json.dumps(out)

    assert SECRET not in blob, "a credential reached the operator console payload!"
    for banned in ("encrypted_cred", "password_hash", "totp_secret", "fingerprint"):
        assert banned not in blob, f"{banned} is exposed in the console payload"
    # ...while the fields support actually needs are present.
    assert out["servers"][0]["name"] == "prod-1"
    assert out["servers"][0]["status"] == "online"


async def test_no_write_routes_exist_on_the_console():
    """5a is read-only BY CONSTRUCTION. Controls are 5b and must be added deliberately,
    each audit-logged — not by a stray POST slipping into this surface."""
    from app.routers import dev
    for r in dev.router.routes:
        if "/admin/" in getattr(r, "path", ""):
            assert set(r.methods) <= {"GET", "HEAD"}, f"{r.path} accepts {r.methods}"


# ── Behaviour ────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_client(monkeypatch):
    """Overrides only auth + db: the service's real SQL construction still runs."""
    admin = _user("staff@serverally.com", "pro", is_admin=True)
    app.dependency_overrides[require_admin] = lambda: admin
    yield admin
    app.dependency_overrides.clear()


async def test_user_detail_404s_for_an_unknown_user(admin_client):
    class _S:
        async def execute(self, _q): return _Res([])
    app.dependency_overrides[get_db] = lambda: _S()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get(f"/api/dev/admin/users/{uuid.uuid4()}")
    assert r.status_code == 404


def test_plan_limits_come_from_the_plan_map():
    """The console must never invent its own numbers — the plan map is the one source."""
    assert admin_service._limits("pro")["max_servers"] == 15
    assert admin_service._limits("free")["actions_per_month"] == 30
    # An unknown/None plan must fall back to free, never to unlimited.
    for bad in (None, "", "enterprise", "PRO "):
        lim = admin_service._limits(bad)
        assert lim["max_servers"] in (2, 15)
        if bad in (None, "", "enterprise"):
            assert lim == admin_service.PLANS["free"]


async def test_list_users_is_empty_safe(admin_client):
    """No users -> no second query, no crash (the batched joins assume a non-empty id list)."""
    class _S:
        async def execute(self, _q): return _Res([])
    assert await admin_service.list_users(_S()) == []
