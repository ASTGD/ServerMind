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
    """One account per database, named after it, so a leak is bounded to that database."""
    base = db_name[: _MAX - 5].rstrip("_")
    return f"{base}_user"


def generate_password(length: int = 24) -> str:
    """A password nobody has to think of, long enough that nobody has to worry about it."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
