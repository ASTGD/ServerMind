"""Naming a database for a site, so nobody has to invent one.

Whatever this suggests has to be something `database_service` will actually accept — a
suggestion the very next call rejects is worse than no suggestion, because the customer
did not type it and cannot see what is wrong with it.
"""
import pytest

from app.services import database_service as dbs
from app.services import site_database_naming as naming


@pytest.mark.parametrize("domain,expected", [
    ("shop.example.com", "shop_example_com"),
    ("SHOP.Example.COM", "shop_example_com"),
    ("my-shop.co.uk", "my_shop_co_uk"),
    ("lv1.serverally.org", "lv1_serverally_org"),
])
def test_a_domain_becomes_a_readable_name(domain, expected):
    assert naming.suggest_name(domain) == expected


def test_a_name_must_start_with_a_letter():
    """`123shop.com` is an ordinary domain and an illegal identifier."""
    assert naming.suggest_name("123shop.com").startswith("db_")


@pytest.mark.parametrize("domain", [
    "", "...", "---", "☃.com", "a" * 200, "123.456.789", "-leading-dash.com",
])
def test_an_awkward_domain_still_produces_a_usable_name(domain):
    """Falling over here would block creating a database for a site that exists."""
    assert dbs.validate_name(naming.suggest_name(domain), what="database name")


def test_the_user_is_named_after_its_database():
    """One account per database, so a leaked password reaches that database and no other."""
    assert naming.suggest_user("shop_example_com") == "shop_example_com_user"


def test_a_very_long_domain_still_leaves_room_for_the_user_suffix():
    name = naming.suggest_name("a-very-long-subdomain.of-a-long-domain.example.co.uk")
    user = naming.suggest_user(name)
    assert dbs.validate_name(name, what="database name")
    assert dbs.validate_name(user, what="user name")


# ── The generated password ───────────────────────────────────────────────────

def test_the_password_is_accepted_by_the_thing_that_will_set_it():
    assert dbs.validate_password(naming.generate_password())


def test_the_password_has_no_backslash_and_no_quote():
    """A backslash inside a MySQL string literal is an escape, so the account is created,
    success is reported, and the password then does not work — a real MariaDB taught us
    that. The escaping handles it either way; a generated password has no reason to go
    anywhere near the problem."""
    for _ in range(200):
        p = naming.generate_password()
        assert "\\" not in p and "'" not in p and '"' not in p


def test_the_password_survives_being_put_into_sql_unchanged():
    """The real proof: whatever we generate must come out of the quoting untouched, on
    both engines."""
    for _ in range(100):
        p = naming.generate_password()
        assert dbs._quote_password("mysql", p) == p
        assert dbs._quote_password("postgres", p) == p


def test_two_passwords_are_not_the_same():
    assert len({naming.generate_password() for _ in range(50)}) == 50
