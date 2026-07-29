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


def test_recipe_catalog_is_present_and_well_formed():
    """Lock the shipped recipe catalog + require every recipe to have the fields the
    gallery/modal need (a missing summary or goal_template ships a broken card)."""
    recipes = {r.slug: r for r in sk.list_recipes("linux")}
    expected = {
        "cyberpanel-host-website", "github-deploy", "migrate-website",
        "harden-server", "setup-backups", "domain-ssl",
    }
    assert expected <= set(recipes), f"missing recipes: {expected - set(recipes)}"
    for r in recipes.values():
        assert r.mode == "mission", r.slug
        assert r.summary, r.slug
        assert r.icon, r.slug
        assert r.goal_template, r.slug
        # budgets are clamped to the mission range
        assert 10 <= sk.resolve_mission_budget(r) <= 40, r.slug


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
        # A recipe that declares which servers it applies to is only routable ON such a
        # server — and that is exactly how it is used: the form picks a target, and the
        # chat handler passes that server's panel. Testing it without one would assert a
        # property nothing depends on, and two runbooks sharing a trigger would look
        # broken when they are not.
        need = (r.requires or "").strip().lower()
        panel = "cyberpanel" if need == "panel" else "" if need else None
        matched = sk.match(msg, os_type, panel=panel)
        assert matched is not None, f"{r.slug}: goal_template routes to nothing: {msg!r}"
        assert matched.slug == r.slug, (
            f"{r.slug}: goal_template routes to {matched.slug!r} instead of itself: {msg!r}"
        )


# ── two runbooks, one trigger, told apart by the server ──────────────────────
def test_the_website_runbooks_are_told_apart_by_the_server():
    """"Host a website" means something different on a CyberPanel box than on a plain one.
    Before the panel gate, every request routed to the CyberPanel runbook — which then
    stopped and refused on a plain server, so Ally declined a job it could have done."""
    msg = "host a website at shop.example.com"
    assert sk.match(msg, "ubuntu", panel="cyberpanel").slug == "cyberpanel-host-website"
    assert sk.match(msg, "ubuntu", panel="").slug == "host-website-plain"


def test_a_runbook_is_not_offered_for_a_server_it_cannot_run_on():
    """The menu is what the model picks from when keywords miss. Listing a runbook that
    immediately refuses wastes a turn and reads as a dead end."""
    plain = sk.menu_for("ubuntu", panel="")
    panel = sk.menu_for("ubuntu", panel="cyberpanel")
    assert "host-website-plain" in plain and "cyberpanel-host-website" not in plain
    assert "cyberpanel-host-website" in panel and "host-website-plain" not in panel


def test_an_unknown_server_hides_nothing():
    """A detail we have not read yet must not silently remove the right runbook."""
    menu = sk.menu_for("ubuntu", panel=None)
    assert "host-website-plain" in menu and "cyberpanel-host-website" in menu


def test_a_runbook_with_no_requirement_applies_anywhere():
    for panel in (None, "", "cyberpanel"):
        real = next(s for s in sk.load_skills() if not s.requires)
        assert sk.server_ok(real, panel), f"{real.slug} should apply anywhere"


def test_a_server_with_no_panel_recorded_is_a_plain_server_not_an_unknown_one():
    """The bug this exists to stop, found against the real database: a plain server's
    panel_type is NULL, not "". Treating null as "we do not know" meant every plain server
    — the exact case the runbook is for — still got the CyberPanel one. Callers holding a
    server pass `panel_type or ""`, because null on a real record is an answer."""
    msg = "host a website at shop.example.com"
    stored = None                                   # what the database actually returns
    assert sk.match(msg, "ubuntu", panel=stored or "").slug == "host-website-plain"
    # And a caller with no server at all still sees everything.
    assert sk.match(msg, "ubuntu", panel=None) is not None


def test_every_caller_that_has_a_server_passes_its_panel():
    """A call site that forgets this silently routes every plain server to the wrong
    runbook, and nothing fails — so it is checked here rather than left to review."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    for path in ("websocket/terminal.py", "services/dev_service.py",
                 "services/ai_context_service.py"):
        text = (root / path).read_text()
        assert 'panel=server.panel_type or ""' in text, f"{path} does not pass the panel"


def test_the_recipe_list_is_gated_by_the_server_too():
    """The list a customer picks from must match the machine they picked, or they are
    offered a recipe that refuses the moment it starts."""
    for panel, want in (("cyberpanel", "cyberpanel-host-website"),
                        ("", "host-website-plain")):
        offered = [s.slug for s in sk.list_recipes("ubuntu")
                   if sk.server_ok(s, panel) and "host-website" in s.slug]
        assert offered == [want], f"panel={panel!r} offered {offered}"
