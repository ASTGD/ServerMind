"""The guard the route sweeps were missing.

Three tests prove security properties by walking every route: no paid create is ungated, the
automation API cannot touch account security, each cloud-lifecycle path reaches its own
handler. Every one of them asks "is there a violation in this list?" — and **an empty list has
no violations in it**.

That is not hypothetical. FastAPI 0.140 stopped putting included routers' routes in
`app.routes`, so in CI those sweeps walked a list of 11 top-level routes instead of 388 and
reported nothing wrong. Two of them happened to fail for a different reason and gave the game
away; had they been written slightly differently they would have passed, green, protecting
nothing, for as long as nobody looked.

So the sweeps now get a floor: prove the app is visible before believing what a sweep says
about it.
"""
import main

from tests.routes import all_routes, paths, route_for


def test_the_flattener_sees_the_whole_app():
    """A number, deliberately. If a future framework version hides routes again this fails
    loudly instead of quietly reporting that nothing is wrong."""
    routes = all_routes(main.app)
    assert len(routes) > 200, (
        f"only {len(routes)} routes visible — the route sweeps are walking a fraction of the "
        f"app and would report no violations because they can see none")


def test_the_routes_a_security_sweep_exists_to_check_are_actually_visible():
    """Named individually. Counting alone would pass on 300 routes that happened to exclude
    the very ones the sweeps care about."""
    seen = paths(main.app)
    for path in ("/api/api-keys",            # minting a key must need a session
                 "/api/webhooks",
                 "/api/autopilot/tasks",     # paid creates that must be gated
                 "/api/v1/servers",          # the bounded automation surface
                 "/api/cloud-accounts",
                 "/api/servers"):
        assert path in seen, f"{path} is invisible to the sweeps"


def test_a_route_can_still_be_resolved_to_its_handler():
    """`route_for` underpins "this path reaches its OWN handler", which is how a catch-all
    swallowing two more important routes was caught once already."""
    route = route_for(main.app, "/api/servers", "POST")
    assert route is not None
    assert getattr(route, "name", None), "a route with no name cannot be checked for identity"


def test_nothing_is_counted_twice():
    """Recursion over nested routers must not double-count, or "exactly one handler" checks
    would start seeing phantom duplicates."""
    routes = all_routes(main.app)
    assert len(routes) == len({id(r) for r in routes})
