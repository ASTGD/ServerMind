"""Ally Recipes — the one-click mission gallery is just promoted mission skills, so the
risk is entirely in (a) parsing the recipe frontmatter and (b) the composed goal_template
still routing to its OWN skill. Both are locked here (no API/DB needed)."""
from __future__ import annotations

import re

import pytest

from app.services import skill_service as sk


@pytest.fixture(autouse=True)
def _fresh_cache():
    sk.reset_cache()
    yield
    sk.reset_cache()


def test_variables_parser():
    v = sk._parse_variables("domain:required, title:optional:{{domain}}, email:optional:admin@{{domain}}")
    assert v == [
        {"name": "domain", "required": True, "default": ""},
        {"name": "title", "required": False, "default": "{{domain}}"},
        # default may contain ':' — the '@{{domain}}' form has none, but a URL default would
        {"name": "email", "required": False, "default": "admin@{{domain}}"},
    ]
    assert sk._parse_variables("") == []
    assert sk._parse_variables(None) == []
    # a bare name with no flag → optional, no default
    assert sk._parse_variables("repo") == [{"name": "repo", "required": False, "default": ""}]


def test_promoted_skills_are_recipes():
    recipes = sk.list_recipes("linux")
    slugs = {r.slug for r in recipes}
    assert "cyberpanel-host-website" in slugs
    assert "github-deploy" in slugs
    for r in recipes:
        assert r.mode == "mission"           # a recipe is always a mission runbook
        assert r.recipe is True
        assert r.goal_template               # must have a message to send
        assert r.summary                     # user-facing card text


def test_reactive_skills_are_not_recipes():
    """Diagnostic/reactive runbooks must NOT appear in the browse-and-click gallery
    (docs/ALLY-RECIPES.md 'catalog rule: proactive only')."""
    slugs = {r.slug for r in sk.list_recipes(None)}
    assert "security-incident-response" not in slugs
    # a plain knowledge skill is never a recipe either
    assert "server-slow-triage" not in slugs


def test_recipes_are_os_gated():
    # all current recipes are linux; a windows target should see none of them
    assert sk.list_recipes("windows") == []
    assert len(sk.list_recipes("linux")) >= 2


def _fill(template: str) -> str:
    """Fill every {{var}} with a routable placeholder — routing depends on the template's
    static words, not the values."""
    return re.sub(r"\{\{[^}]+\}\}", "example.com", template)


@pytest.mark.parametrize("os_type", ["linux"])
def test_goal_template_routes_back_to_its_own_skill(os_type):
    """The composed sentence a Recipe sends must start ITS mission — i.e. match() on the
    filled goal_template resolves to the same skill. This is the whole contract: a recipe
    that routes elsewhere would silently run the wrong mission."""
    for r in sk.list_recipes(os_type):
        msg = _fill(r.goal_template)
        matched = sk.match(msg, os_type)
        assert matched is not None, f"{r.slug}: goal_template routes to nothing: {msg!r}"
        assert matched.slug == r.slug, (
            f"{r.slug}: goal_template routes to {matched.slug!r} instead of itself: {msg!r}"
        )
