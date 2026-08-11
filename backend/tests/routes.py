"""Every route the app actually serves, flattened.

Three tests sweep the route table to prove security properties — that no paid create is
ungated, that the automation API cannot touch account security, that each cloud-lifecycle
path reaches its own handler. All three read `app.routes` directly, and **as of FastAPI
0.140 that no longer contains the routes**: `include_router` leaves an `_IncludedRouter`
wrapper whose real routes hang off `original_router`.

That is why those sweeps failed in CI while passing locally — the pinned requirement is
0.140.13 and the local virtualenv had drifted to 0.136.3, so the suite had never once run
against the version CI and the production image build from.

The flattening lives here rather than in each test because it is the same question three
times, and a fourth sweep written later would otherwise start out silently empty — which for
a *security* sweep means passing, since an empty list has no violations in it.
"""
from __future__ import annotations


def all_routes(app) -> list:
    """Every route, including those inside included routers, at any depth."""
    found: list = []
    seen: set[int] = set()

    def walk(routes) -> None:
        for route in routes or []:
            if id(route) in seen:
                continue
            seen.add(id(route))
            inner = getattr(route, "original_router", None)   # FastAPI >= 0.140
            if inner is not None:
                walk(getattr(inner, "routes", []))
                continue
            found.append(route)
            nested = getattr(route, "routes", None)           # Mount, sub-application
            if nested and nested is not routes:
                walk(nested)

    walk(getattr(app, "routes", []))
    return found


def paths(app) -> set[str]:
    """Just the path strings, for the "is this route registered at all" questions."""
    return {p for p in (getattr(r, "path", "") for r in all_routes(app)) if p}


def route_for(app, path: str, method: str = "POST"):
    """The single route serving one path and method, or None."""
    for route in all_routes(app):
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or ()):
            return route
    return None
