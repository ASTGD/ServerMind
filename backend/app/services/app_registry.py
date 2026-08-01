"""What we can actually do for the application running on a site.

A site is a domain and a folder; what runs *inside* it is a different thing with its own
vocabulary. WordPress has plugins and themes; Nextcloud has apps and an ``occ`` command;
Ghost has none of that. Writing one screen that tries to cover all of them produces a screen
that serves none of them, so each gets its own — and this is the list of which ones exist.

**One entry per application.** Adding support for Nextcloud should be an entry here plus a
service that implements it, not a new branch in the site page, the menu, and the router. The
second copy is what drifts.

**A section appears only when we genuinely have tools for that application.** A site running
something we have no support for shows no application section at all, rather than an empty
one — the same rule the server menu follows, for the same reason: a permanently dead row is
noise on every visit, and worse, it implies the feature exists and is merely switched off.

The key is ``sites.app_type``, which discovery already sets from what it finds on the server,
so a site the customer installed WordPress onto by hand gets the section too.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppSpec:
    """One application we know how to work with."""

    #: Matches ``sites.app_type``.
    id: str
    #: What the customer calls it. Becomes the menu section's name.
    label: str
    #: The command-line tool this application is managed through, named so a server that
    #: does not have it can say which one to install rather than showing an empty screen.
    requires: str


APPS: dict[str, AppSpec] = {
    "wordpress": AppSpec(id="wordpress", label="WordPress", requires="wp-cli"),
}


def app_for(app_type: str | None) -> AppSpec | None:
    """The application section for a site, or ``None`` when there is nothing to show.

    ``php``, ``static`` and ``unknown`` are deliberately absent: they describe how a site is
    served, not an application we can operate. A generic "PHP" section would have nothing in
    it that the site's own Files, Logs and HTTPS sections do not already cover.
    """
    return APPS.get((app_type or "").lower())


def supported() -> list[str]:
    """Every application type with a section, for the frontend's menu."""
    return sorted(APPS)
