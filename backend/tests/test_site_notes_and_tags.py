"""A note about a site, and the grouping that makes fifty sites readable — Ploi's Settings.

Neither can be recovered by looking at a server, which is the whole reason they need a home
here. That also makes them the two fields on a site that are purely the customer's own.

The bound on a tag is legibility rather than safety: it never reaches a shell, a path or a
config file. What matters is that it stays MATCHABLE — a tag silently truncated, or one that
differs from another only in case, groups nothing.
"""
import pytest

from app.services import site_service as ss


# ── Tags ─────────────────────────────────────────────────────────────────────

def test_the_tags_come_back_tidied():
    assert ss.check_tags(["  Acme  ", "", "  ", "Client X"]) == ["Acme", "Client X"]


def test_two_spellings_of_one_tag_are_one_tag():
    """"Acme" and "acme" on two sites would look like two groups and group nothing. The
    FIRST spelling is kept, because that is the one the customer already sees elsewhere."""
    assert ss.check_tags(["Acme", "acme", "ACME"]) == ["Acme"]


def test_inner_whitespace_is_collapsed_not_kept():
    assert ss.check_tags(["client   acme"]) == ["client acme"]


def test_a_tag_that_is_too_long_is_refused_not_cut():
    """Truncating produces a tag that no longer matches the ones on other sites — silently,
    and grouping is the entire point."""
    with pytest.raises(ss.SiteError) as exc:
        ss.check_tags(["x" * 41])
    assert "too long" in str(exc.value)


def test_too_many_tags_is_refused():
    with pytest.raises(ss.SiteError):
        ss.check_tags([f"tag{i}" for i in range(ss.MAX_TAGS + 1)])


def test_the_limit_itself_is_reachable():
    """A bound nobody can reach is a bound that is really zero."""
    assert len(ss.check_tags([f"tag{i}" for i in range(ss.MAX_TAGS)])) == ss.MAX_TAGS


def test_no_tags_is_an_empty_list_not_null():
    assert ss.check_tags(None) == []
    assert ss.check_tags([]) == []


# ── Notes ────────────────────────────────────────────────────────────────────

def test_an_empty_note_clears_it():
    """Deleting a note has to be possible, and the natural way somebody does it is by
    selecting the text and pressing delete — which sends "" and must not save a blank."""
    assert ss.check_notes("") is None
    assert ss.check_notes("   \n  ") is None


def test_a_note_keeps_its_own_line_breaks():
    """It is a note, not a label. A list of renewal dates is the obvious use."""
    assert ss.check_notes("renews March\npays annually") == "renews March\npays annually"


def test_an_enormous_note_is_refused():
    with pytest.raises(ss.SiteError):
        ss.check_notes("x" * (ss.MAX_NOTES + 1))


# ── They reach the page ──────────────────────────────────────────────────────

def test_both_are_serialised_for_the_screen():
    class Row:
        pass

    row = Row()
    for name, value in (("id", "1"), ("domain", "shop.com"), ("aliases", []),
                        ("server_id", None), ("doc_root", None), ("source", "manual"),
                        ("app_type", "php"), ("app_version", None), ("has_ssl", False),
                        ("is_present", True), ("first_seen", None), ("last_seen", None),
                        ("notes", "renews March"), ("tags", ["Acme"])):
        setattr(row, name, value)

    out = ss.serialize(row)
    assert out["notes"] == "renews March"
    assert out["tags"] == ["Acme"]


def test_a_row_from_before_this_existed_serialises_cleanly():
    """Every site that already exists has neither, and a missing attribute must read as
    empty rather than raise on a page that shows fifty of them."""
    class Old:
        id = "1"
        domain = "shop.com"
        aliases: list = []
        server_id = None
        doc_root = None
        source = "manual"
        app_type = "php"
        app_version = None
        has_ssl = False
        is_present = True
        first_seen = None
        last_seen = None

    out = ss.serialize(Old())
    assert out["notes"] is None
    assert out["tags"] == []


# ── The endpoint ─────────────────────────────────────────────────────────────

import uuid as _uuid

import pytest as _pytest

from app.database import AsyncSessionLocal, engine
from app.models import escalation as _escalation  # noqa: F401 — servers FK needs its table
from app.models.server import Server
from app.models.site import Site
from app.models.user import User
from app.routers import sites as sites_router
from app.services import crypto_service


@_pytest.fixture(autouse=True)
async def _fresh_pool():
    yield
    await engine.dispose()


async def _one_site(db, **kw):
    tag = _uuid.uuid4().hex[:8]
    user = User(email=f"notes-{tag}@example.com", password_hash="x", is_verified=True)
    db.add(user)
    await db.flush()
    server = Server(user_id=user.id, name=f"srv-{tag}", host="10.0.0.9", port=22,
                    username="root", auth_type="password", connection_type="ssh",
                    encrypted_cred=crypto_service.encrypt("pw"))
    db.add(server)
    await db.flush()
    site = Site(user_id=user.id, server_id=server.id, domain=f"{tag}.example.com",
                aliases=[], doc_root="/var/www/x", source="nginx", app_type="php",
                has_ssl=False, is_present=True, status="live", **kw)
    db.add(site)
    await db.flush()
    return user, site


@_pytest.mark.asyncio
async def test_only_what_was_sent_is_changed():
    """Two screens edit this row. A notes form that also sent `tags: []` would wipe the
    grouping somebody set on the other one, and nothing would say so."""
    async with AsyncSessionLocal() as db:
        user, site = await _one_site(db, notes="keep me", tags=["Acme"])
        await db.commit()

        out = await sites_router.set_site_details(
            str(site.id), sites_router.SiteDetailsIn(tags=["Acme", "Retainer"]), db, user)
        assert out["notes"] == "keep me", "the note must survive a tags-only save"

        out = await sites_router.set_site_details(
            str(site.id), sites_router.SiteDetailsIn(notes="new note"), db, user)
        assert out["tags"] == ["Acme", "Retainer"], "the tags must survive a notes-only save"


@_pytest.mark.asyncio
async def test_a_site_belonging_to_someone_else_cannot_be_annotated():
    from fastapi import HTTPException

    async with AsyncSessionLocal() as db:
        _mine, site = await _one_site(db)
        other, _theirs = await _one_site(db)
        await db.commit()

        with _pytest.raises(HTTPException) as exc:
            await sites_router.set_site_details(
                str(site.id), sites_router.SiteDetailsIn(notes="hello"), db, other)
        assert exc.value.status_code == 404


@_pytest.mark.asyncio
async def test_the_tag_list_offers_what_has_already_been_used():
    """Offering them is what makes grouping work: a customer who retypes "acme" as "Acme"
    has created a second group without noticing."""
    async with AsyncSessionLocal() as db:
        user, first = await _one_site(db, tags=["Acme", "Retainer"])
        second = Site(user_id=user.id, server_id=first.server_id,
                      domain=f"b-{_uuid.uuid4().hex[:8]}.example.com", aliases=[],
                      doc_root="/var/www/y", source="nginx", app_type="php",
                      has_ssl=False, is_present=True, status="live", tags=["acme", "Bravo"])
        db.add(second)
        await db.commit()

        out = await sites_router.list_site_tags(db, user)

    # One "Acme", not two spellings of it.
    assert [t.lower() for t in out["tags"]] == ["acme", "bravo", "retainer"]
