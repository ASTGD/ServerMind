"""OAuth Authorization Server metadata guarantees (docs/MCP-SERVER-PLAN.md §5.4).

The one that matters: the AS metadata MUST advertise ``"none"`` as a token-endpoint
auth method. Claude Desktop / claude.ai register as a PUBLIC client
(``token_endpoint_auth_method="none"`` + PKCE, no secret); a spec-strict client reads
this metadata and, if ``"none"`` is absent, ABORTS the flow *before* calling ``/token``
— which is exactly the "Authorization with ServerAlly failed" failure we hit live. The
MCP SDK hardcodes the list to ``["client_secret_post","client_secret_basic"]`` and omits
``"none"``; ``_advertise_public_clients`` corrects it. This test fails if that correction
is ever lost (e.g. an SDK bump that rebuilds the route without our override).
"""
from __future__ import annotations

import asyncio
import json

from app.mcp.http_auth import _AS_METADATA_PATH, oauth_root_routes


def _fetch_as_metadata() -> dict:
    """Drive the real metadata route through Starlette's ASGI interface."""
    routes = oauth_root_routes()
    matches = [r for r in routes if getattr(r, "path", None) == _AS_METADATA_PATH]
    assert len(matches) == 1, f"expected exactly one AS-metadata route, got {len(matches)}"
    route = matches[0]

    async def drive() -> dict:
        scope = {
            "type": "http",
            "method": "GET",
            "path": _AS_METADATA_PATH,
            "headers": [],
            "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        sent: list[dict] = []

        async def send(message):
            sent.append(message)

        await route.handle(scope, receive, send)
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        return json.loads(body)

    return asyncio.run(drive())


def test_as_metadata_advertises_public_client_support():
    """A public client (Claude) must see ``"none"`` at the token endpoint, or it aborts."""
    meta = _fetch_as_metadata()
    methods = meta.get("token_endpoint_auth_methods_supported")
    assert methods is not None, "token_endpoint_auth_methods_supported missing entirely"
    assert "none" in methods, (
        "AS metadata must advertise 'none' — a public OAuth client (Claude Desktop / "
        "claude.ai, PKCE, no secret) aborts before /token if it is absent. "
        f"got: {methods}"
    )


def test_revocation_endpoint_also_advertises_none():
    """Public clients revoke without a secret too — keep the two lists consistent."""
    meta = _fetch_as_metadata()
    methods = meta.get("revocation_endpoint_auth_methods_supported")
    assert methods is not None and "none" in methods, (
        f"revocation_endpoint_auth_methods_supported must include 'none'; got: {methods}"
    )


def test_metadata_still_has_the_core_oauth_fields():
    """Guard against the override accidentally dropping required AS fields."""
    meta = _fetch_as_metadata()
    for field in (
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "registration_endpoint",
        "code_challenge_methods_supported",
    ):
        assert meta.get(field), f"AS metadata lost required field: {field}"
    assert meta["code_challenge_methods_supported"] == ["S256"], "PKCE S256 must be advertised"
