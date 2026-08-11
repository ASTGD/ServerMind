"""Saying what a site is, when looking at the server could not tell.

Detection is better than asking WHEN IT WORKS, and has nothing to fall back on when it does
not: a site we cannot name stays `unknown` for ever and gets no application section at all.
Three sites in the owner's own account are in exactly that state.

**One rule holds the feature together: a scan may fill a gap, but it may not overrule a
person.** Without it the next discovery run undoes the choice a few minutes later and the
setting appears to revert by itself — which is worse than never offering it, because the
customer cannot tell whether they did something wrong.
"""
import pytest

from app.services import site_service as ss


class Row:
    """A site row, only as far as sync and the type rules touch it."""

    def __init__(self, **kw):
        self.domain = kw.get("domain", "shop.example.com")
        self.app_type = kw.get("app_type", "unknown")
        self.app_version = kw.get("app_version")
        self.type_source = kw.get("type_source", "detected")
        self.source = kw.get("source", "nginx")
        self.doc_root = kw.get("doc_root", "/var/www/shop.example.com")
        self.status = kw.get("status", "live")
        self.is_present = True
        self.install_error = None
        self.has_ssl = False
        self.last_seen = None


# ── Who decided ──────────────────────────────────────────────────────────────

def test_a_type_nobody_chose_is_detected():
    assert ss.type_is_chosen(Row()) is False
    assert ss.type_is_chosen(Row(type_source="detected")) is False


def test_a_type_the_owner_set_is_chosen():
    assert ss.type_is_chosen(Row(type_source="chosen")) is True


def test_a_row_from_before_this_existed_counts_as_detected():
    """Every site that already exists was typed by a scan — that is all there was."""
    class Old:
        pass
    assert ss.type_is_chosen(Old()) is False


# ── What may be chosen ───────────────────────────────────────────────────────

@pytest.mark.parametrize("value", list(ss.CHOOSABLE_TYPES))
def test_every_offered_type_is_accepted(value):
    assert ss.check_chosen_type(value) == value


def test_only_types_we_have_tools_for_are_offered():
    """Ploi offers Statamic, Craft and Symfony because their tab is the same either way.
    Ours would promise an application section that does not exist — the same "absent, not
    disabled" rule the menus already follow, one level down."""
    from app.services import app_registry

    for value in ss.CHOOSABLE_TYPES:
        # `static` has no application section by design: a folder of files has nothing to
        # operate. Everything else offered must actually have one.
        if value == "static":
            continue
        assert app_registry.app_for(value) is not None, \
            f"{value} is offered with no tools behind it"


def test_a_type_we_have_no_tools_for_is_refused():
    for value in ("statamic", "craft", "symfony", "nodejs", "drupal"):
        with pytest.raises(ss.SiteError) as exc:
            ss.check_chosen_type(value)
        assert "not a type we have tools for" in str(exc.value)


def test_the_refusal_names_what_they_can_pick():
    with pytest.raises(ss.SiteError) as exc:
        ss.check_chosen_type("statamic")
    msg = str(exc.value)
    for value in ss.CHOOSABLE_TYPES:
        assert value in msg
    assert "detected" in msg


def test_empty_hands_the_question_back_to_detection():
    """A wrong choice has to be undoable, and the only honest way back is to let the server
    answer again."""
    assert ss.check_chosen_type("") == ""
    assert ss.check_chosen_type("   ") == ""


def test_the_choice_is_not_case_sensitive():
    assert ss.check_chosen_type("WordPress") == "wordpress"


# ── THE rule: a scan fills a gap, it does not overrule a person ──────────────
#
# Those live in `test_site_lifecycle.py`, beside the `_scan` helper that runs the REAL
# `sync`. A local copy of the update branch here would pass with the guard deleted — which
# is precisely the trap that helper's own docstring was written to warn about, and I walked
# into it once already writing this file.


# ── Handing the question back ────────────────────────────────────────────────

def test_choosing_a_type_records_that_a_person_chose_it():
    assert ss.next_type_state("wordpress") == ("wordpress", "chosen")


def test_forgetting_a_choice_makes_the_site_unknown_again():
    """Found by reverting a real site in the browser: keeping the chosen value left the
    screen saying "detected by looking at the server" about an answer a PERSON gave — true
    only after the next scan, and a lie until then. The only way to be in the chosen state
    is to have chosen, so forgetting it means we do not know again until we look."""
    assert ss.next_type_state("") == ("unknown", "detected")
