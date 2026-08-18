"""Connecting ChatGPT — the scope wall, and why the client's own declaration is not a gate.

Reported live: "when I use OAuth it shows an error". The access log gave the exact answer,
which no amount of reading would have:

    GET /authorize?…&scope=mcp:read mcp:write mcp:admin   -> 302
    Location: …?error=invalid_scope
              &error_description=Client+was+not+registered+with+scope+mcp:write

Our own server refused it. The registered clients tell the rest of the story:

    Claude   scope = "mcp:read mcp:write mcp:admin"     works
    ChatGPT  scope = "mcp:read"                         refused

Claude declares its scopes when it registers; ChatGPT does not. A client that omits `scope`
is stamped with the server's registration default (`register.py:62`), and every scope it
later asks for is checked against that stamp (`shared/auth.py:99`). ChatGPT then reads our
metadata, asks for the three scopes we advertise in `scopes_supported`, and is refused for
asking for exactly what we advertised — our metadata contradicting itself.

**The reason widening it is safe is the property pinned below: the client's request never
decided anything.** What is granted comes only from the access level the person picks on the
consent page, which overrides the request entirely. So the stamp was not a control — it was
only ever able to refuse a legitimate connection.

The fix is applied on READ, so it is a live property rather than a value frozen at
registration: the three ChatGPT clients already stored read-only heal on their next attempt.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import types

import pytest

from app.mcp import http_auth
from app.mcp.oauth_provider import (
    ALL_SCOPES,
    SCOPE_ADMIN,
    SCOPE_READ,
    SCOPE_WRITE,
    ServerAllyOAuthProvider,
    requestable_scope,
    scopes_for_access_level,
)

#: Exactly what ChatGPT asked for on 2026-08-18, from the production access log.
CHATGPT_REQUESTED = "mcp:read mcp:write mcp:admin"

#: Exactly what was stored for it, from the production `oauth_clients` row.
CHATGPT_REGISTERED = "mcp:read"


def code(fn) -> str:
    """Executable lines only — the docstrings here quote the error text they explain."""
    return "\n".join(ln for ln in inspect.getsource(fn).splitlines()
                     if not ln.strip().startswith("#"))


def stored_client(scope: str):
    """A client record shaped like the one Dynamic Client Registration writes."""
    return types.SimpleNamespace(data={
        "client_id": "3dac4e36-5110-4e21-b211-4a99f9949491",
        "client_name": "ChatGPT",
        "redirect_uris": ["https://chatgpt.com/connector/oauth/wDsswqb4gjM9"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": scope,
    })


def load_client(scope: str, monkeypatch):
    """Run the REAL `get_client` over a stored row, with only the database replaced.

    Driving the real method matters: the fix lives there, and a test that built the client
    object itself would prove nothing about what the SDK is handed.
    """
    class _Result:
        def scalar_one_or_none(self):
            return stored_client(scope)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *_a, **_k):
            return _Result()

    monkeypatch.setattr("app.mcp.oauth_provider.AsyncSessionLocal", lambda: _Session())
    return asyncio.run(ServerAllyOAuthProvider().get_client("3dac4e36-5110-4e21-b211-4a99f9949491"))


# ── the bug itself ───────────────────────────────────────────────────────────

def test_chatgpts_exact_request_is_accepted(monkeypatch):
    """The regression. This is the live failure, reproduced: a client stored read-only asks
    for the three scopes we advertise. It raised
    `InvalidScopeError: Client was not registered with scope mcp:write`.
    """
    client = load_client(CHATGPT_REGISTERED, monkeypatch)
    assert client.validate_scope(CHATGPT_REQUESTED) == CHATGPT_REQUESTED.split()


def test_a_client_already_stored_read_only_heals_on_read(monkeypatch):
    """Applied at the read, so the rows written before the fix are not left broken — and
    nobody has to remember a one-off repair."""
    client = load_client(CHATGPT_REGISTERED, monkeypatch)
    assert client.scope == requestable_scope()


def test_a_client_that_declares_everything_still_works(monkeypatch):
    """Claude's shape. The fix must not disturb the connections that already work."""
    client = load_client(" ".join(ALL_SCOPES), monkeypatch)
    assert client.validate_scope(CHATGPT_REQUESTED) == CHATGPT_REQUESTED.split()


def test_an_unknown_client_is_still_unknown(monkeypatch):
    """Widening what a KNOWN client may ask for must not conjure one that was never
    registered."""
    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *_a, **_k):
            return _Result()

    monkeypatch.setattr("app.mcp.oauth_provider.AsyncSessionLocal", lambda: _Session())
    assert asyncio.run(ServerAllyOAuthProvider().get_client("nope")) is None


# ── why widening is safe: the request never decided the grant ────────────────

def test_the_consent_page_decides_the_grant_not_the_request():
    """The property the whole fix rests on. If this ever stops being true, widening what a
    client may ASK for would start widening what it RECEIVES."""
    from app.routers import mcp_oauth

    src = code(mcp_oauth.consent_submit)
    assert "scopes_for_access_level(access_level)" in src, (
        "the granted scopes no longer come from the access level the person chose")
    assert "create_authorization_code(data, str(user.id), scopes=scopes)" in src, (
        "the chosen scopes are no longer what the code is minted with")


def test_asking_for_admin_does_not_grant_admin():
    """A client may now request `mcp:admin`. It only receives it if the person chooses
    "Full power" on the consent page."""
    assert scopes_for_access_level("read") == [SCOPE_READ]
    assert scopes_for_access_level("full") == [SCOPE_READ, SCOPE_WRITE]
    assert scopes_for_access_level("admin") == [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN]


@pytest.mark.parametrize("level", ["", "nonsense", None, "READ", "Full"])
def test_an_unrecognised_access_level_grants_read_only(level):
    """Fails closed. The consent page is now the only thing standing between a request for
    admin and a token carrying it."""
    assert scopes_for_access_level(level) == [SCOPE_READ]


# ── the metadata and the ceiling cannot drift apart ──────────────────────────

def _as_metadata() -> dict:
    routes = http_auth.oauth_root_routes()
    route = next(r for r in routes if getattr(r, "path", None) == http_auth._AS_METADATA_PATH)

    async def drive() -> dict:
        scope = {"type": "http", "method": "GET", "path": http_auth._AS_METADATA_PATH,
                 "headers": [], "query_string": b""}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        sent: list[dict] = []

        async def send(message):
            sent.append(message)

        await route.handle(scope, receive, send)
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return json.loads(body)

    return asyncio.run(drive())


def test_a_client_may_request_everything_we_advertise():
    """The rule in one line, and the reason the refusal was a self-contradiction: we publish
    `scopes_supported`, so a client asking for that list must not be turned away. Read off
    the live metadata so adding a fourth scope cannot leave the two disagreeing."""
    advertised = _as_metadata()["scopes_supported"]
    assert set(advertised) == set(requestable_scope().split()), (
        f"we advertise {advertised} but only allow {requestable_scope().split()} to be "
        f"requested — a client that believes our metadata gets invalid_scope")


def test_a_registration_that_names_no_scope_is_stored_honestly():
    """Data hygiene: the stored row should say what the client may do, rather than saying
    read-only while the read says otherwise."""
    opts = None
    real = http_auth.create_auth_routes

    def spy(**kwargs):
        nonlocal opts
        opts = kwargs.get("client_registration_options")
        return real(**kwargs)

    http_auth.create_auth_routes = spy
    try:
        http_auth.oauth_root_routes()
    finally:
        http_auth.create_auth_routes = real

    assert opts is not None, "registration options were never passed"
    assert list(opts.default_scopes) == list(ALL_SCOPES)
    assert list(opts.valid_scopes) == list(ALL_SCOPES)


def test_a_scope_we_do_not_support_is_still_refused(monkeypatch):
    """Widening is to what we advertise, not to anything at all."""
    from mcp.shared.auth import InvalidScopeError

    client = load_client(CHATGPT_REGISTERED, monkeypatch)
    with pytest.raises(InvalidScopeError):
        client.validate_scope("mcp:read mcp:root")
