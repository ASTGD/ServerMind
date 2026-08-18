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

from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.routes import (
    build_metadata,
    build_resource_metadata_url,
    cors_middleware,
    create_auth_routes,
    create_protected_resource_routes,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions

_AS_METADATA_PATH = "/.well-known/oauth-authorization-server"


def _advertise_public_clients(metadata):
    """Add ``"none"`` to the token/revocation auth-method lists in the AS metadata.

    The SDK hardcodes ``token_endpoint_auth_methods_supported`` to
    ``["client_secret_post", "client_secret_basic"]`` and omits ``"none"``. A
    spec-strict OAuth client (Claude Desktop / claude.ai) that registered as a
    PUBLIC client — ``token_endpoint_auth_method="none"`` + PKCE, no secret — reads
    this metadata, sees that ``"none"`` is not advertised at the token endpoint, and
    ABORTS the flow *before* ever calling ``/token`` (the exact failure we hit: the
    consent redirect delivered the code, but no token exchange followed). Our provider
    *does* accept public clients — the whole flow completes when the metadata check is
    skipped — so we correct the advertised metadata to match reality.
    """
    for field in ("token_endpoint_auth_methods_supported", "revocation_endpoint_auth_methods_supported"):
        methods = getattr(metadata, field, None)
        if methods is not None and "none" not in methods:
            setattr(metadata, field, [*methods, "none"])
    return metadata

from app.config import settings
from app.mcp.oauth_provider import ALL_SCOPES, SCOPE_READ, oauth_provider


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
    client_registration_options = ClientRegistrationOptions(
        enabled=True,                 # Dynamic Client Registration (oauth_dcr)
        valid_scopes=ALL_SCOPES,
        # What a client may REQUEST when it does not declare a scope of its own —
        # everything we advertise. What it is GRANTED is the consent page's choice,
        # which defaults to read-only. See oauth_provider.requestable_scope().
        default_scopes=ALL_SCOPES,
    )
    revocation_options = RevocationOptions(enabled=True)
    routes = create_auth_routes(
        provider=oauth_provider,
        issuer_url=issuer,
        client_registration_options=client_registration_options,
        revocation_options=revocation_options,
    )

    # Replace the SDK's AS-metadata route with one that advertises public-client
    # ("none") support, so strict clients (Claude) proceed to the token exchange.
    corrected = _advertise_public_clients(
        build_metadata(issuer, None, client_registration_options, revocation_options)
    )
    _handle = MetadataHandler(corrected).handle

    async def metadata_endpoint(request):
        # The SDK's handler pins Cache-Control: max-age=3600. If a client cached a
        # PREVIOUS (wrong) metadata doc, it would reuse it for up to an hour and keep
        # failing even after we correct it. Serve a short cache so a retry always sees
        # the current metadata; the endpoint is a tiny static lookup, so re-fetching
        # costs nothing.
        response = await _handle(request)
        response.headers["Cache-Control"] = "public, max-age=60"
        return response

    metadata_route = Route(
        _AS_METADATA_PATH,
        endpoint=cors_middleware(metadata_endpoint, ["GET", "OPTIONS"]),
        methods=["GET", "OPTIONS"],
    )
    routes = [metadata_route if getattr(r, "path", None) == _AS_METADATA_PATH else r for r in routes]

    routes.extend(
        create_protected_resource_routes(
            resource_url=resource_url(),
            authorization_servers=[issuer],
            scopes_supported=ALL_SCOPES,
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
    # Every connection needs at least read; write tools additionally require mcp:write.
    guarded = RequireAuthMiddleware(
        streamable_app, required_scopes=[SCOPE_READ], resource_metadata_url=resource_metadata
    )
    guarded = AuthContextMiddleware(guarded)
    guarded = AuthenticationMiddleware(guarded, backend=BearerAuthBackend(oauth_provider))
    return guarded
