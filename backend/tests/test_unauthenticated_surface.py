"""Which routes answer with no credentials at all — and whether anyone decided that.

The status-page work (2026-07-25) called itself "the app's first unauthenticated read
surface" and was built leak-proof for it: an explicit field allowlist, because a
`model_dump()` would publish every column the first time somebody added one.

Walking the account-level screens found **two more** that answer anonymously, neither of
which anyone had reasoned about:

    GET /api/runbooks/built-in   200   (no Authorization header)
    GET /api/webhooks/events     200

Neither leaks customer data today — both are reference content — but both serialise
whatever the underlying structure holds, so each is one added field away from publishing
something. And a surface nobody knows is public is one nobody reviews.

**This sweep drives the app rather than reading it.** An earlier attempt inferred auth from
function signatures and produced false positives for the whole `/api/v1` (API key) and
`/api/dev` (admin) families, which are properly protected. Behaviour cannot be fooled by a
dependency being renamed — and for a SECURITY sweep, a false all-clear is the worst
possible outcome.
"""
from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, "tests")
from routes import all_routes  # noqa: E402

#: Routes that MUST answer without credentials, each for a stated reason.
DELIBERATELY_OPEN = {
    # Signing in, and the flows that precede having a session at all.
    "/api/auth/login", "/api/auth/register", "/api/auth/refresh",
    "/api/auth/claim", "/api/auth/verify-email",
    # The public status page — decided 2026-07-25, built with a field allowlist.
    "/api/public/status/{slug}",
    # Authenticated by the token in the path, not by a session.
    "/api/public/ack/{token}",
    # Authenticated by an HMAC signature over the raw body — decided 2026-07-28.
    "/api/deploy/hook/{target_id}",
    # Authenticated by the X-Entitlement-Key shared secret (WHMCS).
    "/api/admin/entitlements/set", "/api/admin/entitlements/reconcile",
    "/api/admin/entitlements/ping", "/api/admin/entitlements/{email}",
}

PROTECTED = {401, 403}


def api_routes():
    from main import app

    out = []
    for r in all_routes(app):
        path = getattr(r, "path", "")
        methods = (getattr(r, "methods", set()) or set()) - {"HEAD", "OPTIONS"}
        if not path.startswith("/api/") or not methods:
            continue
        for m in sorted(methods):
            out.append((m, path))
    return sorted(set(out))


def concrete(path: str) -> str:
    """A callable URL — path parameters filled with a value that exists nowhere."""
    out = []
    for part in path.split("/"):
        out.append("00000000-0000-0000-0000-000000000000" if part.startswith("{") else part)
    return "/".join(out)


def test_the_route_table_is_not_empty():
    """The sweep below proves a negative, and an empty list has no violations in it. This
    is what stopped the last route sweep from silently passing when FastAPI 0.140 changed
    where the routes live."""
    assert len(api_routes()) > 150, len(api_routes())


def open_routes(app, routes, allowed) -> list[str]:
    """Every route that answers without credentials. Factored out so the sweep can be
    pointed at a deliberately-open app and PROVE it still catches one — see
    `test_the_sweep_would_actually_catch_an_open_route`. Without that, weakening the
    accepted status codes changes no result at all, because a passing sweep has nothing
    left to find."""
    client = TestClient(app, raise_server_exceptions=False)
    found = []
    for method, path in routes:
        if path in allowed:
            continue
        try:
            resp = client.request(method, concrete(path))
        except Exception:                      # a route that blows up unauthenticated
            found.append(f"{method} {path} -> raised")
            continue
        if resp.status_code not in PROTECTED:
            found.append(f"{method} {path} -> {resp.status_code}")
    return found


def test_the_sweep_would_actually_catch_an_open_route():
    """The mechanism, not today's result.

    Mutation testing found this gap: widening `PROTECTED` to accept 200 broke nothing,
    because with the two real findings fixed the sweep had nothing left to flag. A check
    that cannot fail is not a check.
    """
    from fastapi import FastAPI

    probe = FastAPI()

    @probe.get("/api/wide-open")
    async def wide_open() -> dict:
        return {"secret": "everything"}

    assert open_routes(probe, [("GET", "/api/wide-open")], set()) == [
        "GET /api/wide-open -> 200"]
    # And an allowlisted one is not reported.
    assert open_routes(probe, [("GET", "/api/wide-open")], {"/api/wide-open"}) == []


def test_no_route_answers_anonymously_unless_someone_decided_it_should():
    from main import app

    surprises = open_routes(app, api_routes(), DELIBERATELY_OPEN)

    assert surprises == [], (
        "these answer without credentials and are not in DELIBERATELY_OPEN. Either add the "
        "auth dependency, or add the path with a comment saying why it must be public: "
        + "; ".join(surprises))


@pytest.mark.parametrize("path", sorted(DELIBERATELY_OPEN))
def test_every_open_route_still_exists(path):
    """An allowlist that names routes which no longer exist stops being a decision and
    becomes decoration — and would hide the next one that quietly opens."""
    assert path in {p for _m, p in api_routes()}, f"{path} is allowlisted but has no route"
