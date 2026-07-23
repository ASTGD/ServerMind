"""Root-level OAuth wiring for the MCP server (docs/MCP-SERVER-PLAN.md §4).

We serve the OAuth 2.1 Authorization Server at the ROOT origin (issuer = MCP_BASE_URL)
so RFC 8414 discovery is unambiguous — a client takes the issuer and finds metadata at
``<issuer>/.well-known/oauth-authorization-server`` with no sub-path guessing. The /mcp
endpoint is the Resource Server, guarded by the bearer middleware; an unauthenticated
call gets a 401 whose ``WWW-Authenticate`` header points at the protected-resource
metadata, which in turn names this AS.

The SDK owns all protocol correctness (PKCE, DCR, metadata shapes, the 401 handshake);
we only choose the mount point (root) and provide the storage-backed provider.
"""
from __future__ import annotations

from pydantic import AnyHttpUrl
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import Route

from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.routes import (
    build_resource_metadata_url,
    create_auth_routes,
    create_protected_resource_routes,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions

from app.config import settings
from app.mcp.oauth_provider import SCOPE, oauth_provider


def issuer_url() -> AnyHttpUrl:
    """The OAuth issuer — this backend's public origin."""
    return AnyHttpUrl(settings.MCP_BASE_URL.rstrip("/"))


def resource_url() -> AnyHttpUrl:
    """The protected resource identifier — the MCP endpoint."""
    return AnyHttpUrl(settings.MCP_BASE_URL.rstrip("/") + "/mcp")


def oauth_root_routes() -> list[Route]:
    """The AS endpoints (metadata, /authorize, /token, /register, /revoke) plus the
    protected-resource metadata — all served at the root origin."""
    issuer = issuer_url()
    routes = create_auth_routes(
        provider=oauth_provider,
        issuer_url=issuer,
        client_registration_options=ClientRegistrationOptions(
            enabled=True,                 # Dynamic Client Registration (oauth_dcr)
            valid_scopes=[SCOPE],
            default_scopes=[SCOPE],
        ),
        revocation_options=RevocationOptions(enabled=True),
    )
    routes.extend(
        create_protected_resource_routes(
            resource_url=resource_url(),
            authorization_servers=[issuer],
            scopes_supported=[SCOPE],
            resource_name=settings.APP_NAME,
        )
    )

    # SlowAPIMiddleware names every matched route's endpoint via ``endpoint.__name__``
    # to decide rate-limit exemption. The SDK wraps these metadata/OAuth handlers in a
    # CORSMiddleware (so browsers can fetch the metadata cross-origin), and a middleware
    # *instance* has no ``__name__`` — which would crash SlowAPI on every request to
    # them. Give each a stable name. Our limiter has no default limits, so naming them is
    # enough: they stay unlimited (rate-limiting the OAuth endpoints is a Phase-5 item).
    for route in routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None and not hasattr(endpoint, "__name__"):
            try:
                endpoint.__name__ = f"mcp_oauth:{getattr(route, 'path', 'route')}"
            except (AttributeError, TypeError):  # pragma: no cover — defensive
                pass
    return routes


def guard_mcp_app(streamable_app):
    """Wrap the MCP streamable app in the bearer middleware stack.

    Order (outer → inner): authenticate the bearer → publish it to the auth context
    (so tools can read the caller) → require a valid token, else 401 + the
    ``WWW-Authenticate: Bearer resource_metadata="…"`` handshake.
    """
    resource_metadata = build_resource_metadata_url(resource_url())
    guarded = RequireAuthMiddleware(
        streamable_app, required_scopes=[SCOPE], resource_metadata_url=resource_metadata
    )
    guarded = AuthContextMiddleware(guarded)
    guarded = AuthenticationMiddleware(guarded, backend=BearerAuthBackend(oauth_provider))
    return guarded
