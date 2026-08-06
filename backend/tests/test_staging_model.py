"""Staging sites — the schema and the rules that decide whether a copy can exist.

The rules are pure so they are tested directly, and two of them are refusals: a copy that
cannot be given its own identity should not be created at all.
"""
import pytest

from app.services import site_service as s


class FakeSite:
    def __init__(self, domain="shop.example.com", environment="production",
                 status="live", doc_root="/var/www/shop.example.com/public"):
        self.domain, self.environment = domain, environment
        self.status, self.doc_root = status, doc_root


# ── The suggested domain ─────────────────────────────────────────────────────

def test_a_plain_domain_gets_a_staging_prefix():
    assert s.staging_domain_for("shop.example.com") == "staging.shop.example.com"


def test_a_leading_www_is_stripped():
    """`staging.www.shop.com` is a name nobody wants, and a certificate for it would have to
    cover a label that means nothing."""
    assert s.staging_domain_for("www.shop.example.com") == "staging.shop.example.com"


def test_a_domain_that_is_already_staging_is_left_alone():
    """`staging.staging.shop.com` is a suggestion nobody accepts."""
    assert s.staging_domain_for("staging.shop.example.com") == "staging.shop.example.com"


def test_case_and_a_trailing_dot_do_not_change_the_answer():
    assert s.staging_domain_for("WWW.Shop.Example.COM.") == "staging.shop.example.com"


def test_a_site_with_no_domain_is_refused():
    with pytest.raises(s.SiteError):
        s.staging_domain_for("")


# ── What counts as staging ───────────────────────────────────────────────────

def test_staging_is_decided_by_the_environment_not_the_name():
    """A site somebody called `staging.shop.com` by hand is not staging in the sense that
    matters — nothing knows what it is a copy of, so nothing can safely promote it."""
    assert s.is_staging(FakeSite(environment="staging")) is True
    assert s.is_staging(FakeSite(domain="staging.shop.example.com")) is False


# ── When a copy may be made ──────────────────────────────────────────────────

def test_a_normal_live_site_can_have_a_copy():
    ok, why = s.can_have_staging(FakeSite())
    assert ok is True and why is None


def test_a_staging_site_cannot_have_its_own_staging():
    """Promoting it would have two possible destinations."""
    ok, why = s.can_have_staging(FakeSite(environment="staging"))
    assert ok is False and "already a staging copy" in why


def test_a_site_still_being_built_cannot_be_copied():
    ok, why = s.can_have_staging(FakeSite(status="installing"))
    assert ok is False and "still being set up" in why


def test_a_site_whose_folder_we_do_not_know_cannot_be_copied():
    ok, why = s.can_have_staging(FakeSite(doc_root=""))
    assert ok is False and "nothing to copy" in why


# ── The domain the copy is created at ────────────────────────────────────────

def test_the_copy_may_not_take_the_live_site_s_own_domain():
    """The duplicate rule downstream would report this as "already exists on this server",
    which reads as a system error rather than as what the customer actually asked for."""
    with pytest.raises(s.SiteError) as exc:
        s.check_staging_domain(FakeSite(), "shop.example.com")
    assert "the live site" in str(exc.value)
    # and it suggests the one they probably wanted
    assert "staging.shop.example.com" in str(exc.value)


def test_a_different_domain_is_accepted_and_normalised():
    assert s.check_staging_domain(FakeSite(), "HTTPS://Staging.Shop.Example.com/") \
        == "staging.shop.example.com"


@pytest.mark.parametrize("bad", ["", "not a domain", "shop", "//evil"])
def test_a_copy_domain_that_is_not_a_domain_is_refused(bad):
    with pytest.raises(s.SiteError):
        s.check_staging_domain(FakeSite(), bad)


# ── The schema ───────────────────────────────────────────────────────────────

def test_deleting_the_live_site_must_not_delete_the_copy():
    """SET NULL, never CASCADE. The copy is a real website with real files on a real server;
    cascading would delete somebody's work as a side effect of tidying up."""
    from app.models.site import Site

    fk = next(f for f in Site.__table__.foreign_keys if f.column.table.name == "sites")
    assert fk.ondelete == "SET NULL"


def test_the_three_fields_reach_the_browser():
    """Returned on every payload so the list can group live sites with their copies without
    a second request per row."""
    class Row(FakeSite):
        id = "1"; server_id = None; aliases = []; source = "manual"
        app_type = "wordpress"; app_version = ""; has_ssl = True; is_present = True
        install_error = None; install_run_id = None; requested_type = "wordpress"
        first_seen = None; last_seen = None; parent_site_id = None; no_index = True

    out = s.serialize(Row(environment="staging"))
    assert out["environment"] == "staging"
    assert out["no_index"] is True
    assert "parent_site_id" in out
