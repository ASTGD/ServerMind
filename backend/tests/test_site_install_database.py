"""Creating a site with a database — the two failures that made the ordinary flow unusable.

Found by driving the real API against a real server, which is the only thing that would
have found them: both live in the gap between an installer script and the layer that fills
its variables, and each half looks correct on its own.

    POST /servers/{id}/sites  {"domain": "...", "site_type": "wordpress"}
    -> 422  "This installer still needs DB_PASS."

    POST /servers/{id}/sites  {"domain": "...", "site_type": "laravel"}
    -> 201, then the install failed:
       "a database called 'laravel' already exists. Choose another name so an existing
        application's data is not touched."

So **WordPress could not be created at all**, and **the second site of a type failed** —
on a server that already had one. Two sites on one server is the ordinary case for an
agency, not an edge case.

Both come from the installers declaring fixed defaults (`wordpress`/`wpuser`,
`laravel`/`laravel`) and `DB_PASS` being required-but-empty, with nothing deriving a value
per site. The naming module the per-site database feature already uses now fills them, so
"what is this site's database called" has one answer rather than two that drift.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.services import site_database_naming as naming
from app.services.playbook_service import OFFICIAL_PLAYBOOKS
from app.services.site_service import SITE_TYPES, _derived_database, install_variables

#: Exactly what the installer scripts accept — they validate rather than escape, because
#: these end up in SQL.
INSTALLER_ACCEPTS = re.compile(r"^[a-zA-Z0-9_]+$")

WITH_DB = ["wordpress", "laravel"]
WITHOUT_DB = ["php", "static"]


def playbook(slug: str):
    return SimpleNamespace(**next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == slug))


def vars_for(site_type: str, domain: str, supplied: dict | None = None) -> dict:
    spec = SITE_TYPES[site_type]
    return install_variables(playbook(spec["playbook"]), spec, domain, supplied,
                             takeover=False)


# ── the two live failures ────────────────────────────────────────────────────

def test_wordpress_can_be_created_with_nothing_but_a_domain():
    """The first failure. `DB_PASS` is declared required with an empty default, so the
    substitution guard refused the whole run — WordPress, the most common site type there
    is, could not be created through the ordinary flow at all."""
    v = vars_for("wordpress", "shop.example.com")
    assert v.get("DB_PASS"), "no password was derived, so the install is refused before it runs"
    assert len(v["DB_PASS"]) >= 16


@pytest.mark.parametrize("site_type", WITH_DB)
def test_two_sites_on_one_server_get_two_databases(site_type):
    """The second failure. The defaults are fixed, so the second site of a type collided
    with the first and was refused — after the first had already claimed the name."""
    one = vars_for(site_type, "one.example.com")
    two = vars_for(site_type, "two.example.com")
    assert one["DB_NAME"] != two["DB_NAME"]
    assert one["DB_USER"] != two["DB_USER"]


@pytest.mark.parametrize("site_type", WITH_DB)
def test_the_name_follows_the_site_rather_than_the_playbook_default(site_type):
    """The bug in one line: `wordpress` and `laravel` are what the installers declare, and
    a name shared by every site of that type is what made the second one fail."""
    v = vars_for(site_type, "shop.example.com")
    assert v["DB_NAME"] == "shop_example_com"
    assert v["DB_NAME"] not in {"wordpress", "laravel"}


# ── it must not break what worked ────────────────────────────────────────────

@pytest.mark.parametrize("site_type", WITHOUT_DB)
def test_a_site_that_needs_no_database_is_given_none(site_type):
    """PHP and static sites create fine today. Handing them database variables their
    installer never asked for would be inventing work — and a database nobody uses."""
    v = vars_for(site_type, "shop.example.com")
    for key in ("DB_NAME", "DB_USER", "DB_PASS"):
        assert key not in v, f"{site_type} was given {key}"


def test_the_customers_own_answer_still_wins():
    """Advanced settings exist so somebody can name the database themselves. A derived
    value that overrode them would take the choice away."""
    v = vars_for("wordpress", "shop.example.com",
                 {"DB_NAME": "chosen_by_hand", "DB_USER": "chosen_user"})
    assert v["DB_NAME"] == "chosen_by_hand"
    assert v["DB_USER"] == "chosen_user"


def test_the_domain_is_still_not_the_customers_to_override():
    v = vars_for("wordpress", "real.example.com", {"DOMAIN": "somewhere-else.example.com"})
    assert v["DOMAIN"] == "real.example.com"


# ── the names have to survive the server ─────────────────────────────────────

@pytest.mark.parametrize("domain", [
    "shop.example.com", "a.io", "UPPER.Example.COM", "123start.example.com",
    "xn--bcher-kva.example.com", "a-really-long-subdomain.example-company-name.co.uk",
])
def test_derived_names_pass_the_installers_own_validation(domain):
    """The scripts validate these rather than escaping them, because they end up in SQL.
    A derived name the installer then refuses would be us breaking our own install."""
    v = vars_for("wordpress", domain)
    assert INSTALLER_ACCEPTS.match(v["DB_NAME"]), v["DB_NAME"]
    assert INSTALLER_ACCEPTS.match(v["DB_USER"]), v["DB_USER"]


@pytest.mark.parametrize("domain", [
    "a-really-long-subdomain.example-company-name.co.uk",
    "an-even-longer-one.with-several.parts.example-company.co.uk",
])
def test_the_account_name_fits_what_mysql_accepts(domain):
    """MySQL caps an account name at 32 characters and REFUSES a longer one outright —
    by which point the database itself has already been created, leaving half a site.

    `suggest_user` was building from the 48-character database limit, so a long domain
    produced a 48-character account. Found by generating names rather than by reading.
    """
    user = naming.suggest_user(naming.suggest_name(domain))
    assert len(user) <= 32, f"{user} is {len(user)} characters"


def test_a_generated_password_cannot_break_its_own_login():
    """A backslash in a MySQL password is read as an escape: the account is created,
    success is reported, and the password then does not work. A real MariaDB taught us
    that, so the alphabet excludes the characters that need escaping at all."""
    for _ in range(200):
        pw = naming.generate_password()
        assert not any(c in pw for c in ("\\", "'", '"', "`")), pw


# ── one answer, not two ──────────────────────────────────────────────────────

def test_naming_comes_from_the_shared_module():
    """`site_database_service` already answers "what is this site's database called" for
    the per-site database screen. A second answer here is how the two start disagreeing
    about the same site."""
    import inspect

    body = inspect.getsource(_derived_database)
    assert "site_database_naming" in body
    assert "suggest_name(" in body and "suggest_user(" in body


def test_it_only_fills_what_the_installer_asks_for():
    """Driven off the playbook's declared variables, so a new installer that wants a
    database gets one by declaring it — and one that does not is left alone."""
    class _Pb:
        variables = [{"name": "DOMAIN"}, {"name": "DB_NAME"}]

    out = _derived_database(_Pb(), "shop.example.com")
    assert set(out) == {"DB_NAME"}
