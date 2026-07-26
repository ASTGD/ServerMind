"""The rate-limit bucket must be per ROUTE, not per URL.

Found live: 35 POSTs to ``/api/public/ack/{token}`` with 35 different tokens never hit the
30/minute limit, while 35 with the *same* token did. slowapi defaults to
``key_style="url"``, which puts the path-parameter value into the bucket key — so every
guessed token got its own fresh allowance, removing all protection from precisely the attack
the limit exists to stop. The same flaw applied to status-page slug enumeration.

This is one line of configuration guarding two public endpoints, so it gets a test that
fails loudly if anyone changes it back.
"""
from __future__ import annotations

from app.services.rate_limit_service import limiter


def test_limits_are_bucketed_by_endpoint_not_by_url():
    """With key_style="url", a route with a path parameter is effectively unlimited."""
    assert limiter._key_style == "endpoint", (
        "slowapi must bucket by endpoint. With the default 'url' style, "
        "/api/public/ack/<guess> gets a fresh allowance per guess."
    )


def test_the_public_endpoints_that_depend_on_this_are_still_limited():
    """If a limit is removed from a public route, this test should be the one that notices —
    these two are the only unauthenticated surfaces in the app."""
    import app.routers.escalation as escalation
    import app.routers.status_pages as status_pages

    registered = set(limiter._route_limits)
    for module, name in (
        (escalation, "acknowledge_by_link"),
        (status_pages, "public_status"),
    ):
        assert any(name in key for key in registered), f"{module.__name__}.{name} is not rate-limited"
