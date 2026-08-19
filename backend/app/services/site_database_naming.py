"""Naming a database for a site, so nobody has to invent one.

Small and separate from ``site_database_service`` because that module reads what a site
already uses; this decides what to call a new one. Both stay pure and testable.
"""
from __future__ import annotations

import re
import secrets

#: What ``database_service.validate_name`` will accept, minus the length allowance we keep
#: for the ``_user`` suffix.
_SAFE = re.compile(r"[^a-z0-9]+")
_MAX = 48
#: MySQL caps an ACCOUNT name at 32 characters — shorter than the database-name limit, and
#: it is a hard error rather than a truncation: `String 'x' is too long for user name`.
#: Found by generating names for a long domain: `suggest_user` was producing 48, so a site
#: on a long domain would have failed at CREATE USER after its database already existed.
_MAX_USER = 32

#: Deliberately no backslash and no quote. A backslash in a MySQL password is read as an
#: escape, so the user is created, success is reported, and the password then does not
#: work — a real MariaDB is what taught us that. A generated password has no reason to
#: risk it, so the alphabet simply excludes the characters that need escaping at all.
_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789-_.+="


def suggest_name(domain: str) -> str:
    """A database name from a domain: ``shop.example.com`` → ``shop_example_com``.

    Falls back rather than failing, because the name is a convenience — a domain made
    entirely of characters we cannot use still gets a working suggestion.
    """
    slug = _SAFE.sub("_", (domain or "").strip().lower()).strip("_")
    slug = slug[:_MAX].rstrip("_")
    if not slug or not slug[0].isalpha():
        # Must start with a letter. A domain like `123shop.com` is perfectly ordinary.
        slug = f"db_{slug}" if slug else "db_site"
    return slug[:_MAX]


def suggest_user(db_name: str) -> str:
    """One account per database, named after it, so a leak is bounded to that database.

    Capped to what MySQL will actually accept for an account. A name that is too long is
    refused outright, and by then the database itself has already been created — leaving a
    half-made site behind.
    """
    base = db_name[: _MAX_USER - 5].rstrip("_")
    return f"{base}_user"


def generate_password(length: int = 24) -> str:
    """A password nobody has to think of, long enough that nobody has to worry about it."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def find_named_after(domain: str, engines: list[dict]) -> dict | None:
    """A database on this server named after this site, if there is one.

    Needed because a plain PHP site has no configuration file to read, so after we make a
    database for it the page cannot see what it just made — it would say "no database" and
    offer to make another, which then fails with a name clash and explains nothing.

    A guess, and labelled as one wherever it is shown: a matching name is evidence that a
    database belongs to this site, not proof, because the site's own settings are the only
    thing that actually decides.
    """
    wanted = suggest_name(domain)
    for engine in engines or []:
        for db in engine.get("databases") or []:
            name = db.get("name") if isinstance(db, dict) else db
            if name == wanted:
                return {"engine": engine.get("engine"), "name": name}
    return None
