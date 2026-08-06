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

import shlex
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
    "laravel": AppSpec(id="laravel", label="Laravel", requires="artisan"),
    # PHP is a runtime rather than an application, and it earns a section for one reason:
    # the limits a site actually runs under are the answer to "why does my upload fail" and
    # "why does it say memory exhausted", and they are per-POOL — so the server's PHP page,
    # which reports the server default, cannot answer them for this site.
    "php": AppSpec(id="php", label="PHP", requires="php"),
    # Node, Next.js, Python, Go — whatever our Web-application installer was pointed at. It
    # is runtime-agnostic by design (a systemd unit and a reverse proxy), so the section is
    # named for what it IS rather than for one language, and the probe names the runtime it
    # actually finds. Ploi calls theirs "NodeJS" and cannot show the other three.
    "app": AppSpec(id="app", label="Application", requires="systemd"),
}


def app_for(app_type: str | None) -> AppSpec | None:
    """The application section for a site, or ``None`` when there is nothing to show.

    ``static`` and ``unknown`` are deliberately absent: a folder of files has nothing to
    operate, and "unknown" means the scan could not tell — offering a section for it would
    be guessing at what is there.
    """
    return APPS.get((app_type or "").lower())


def supported() -> list[str]:
    """Every application type with a section, for the frontend's menu."""
    return sorted(APPS)


def owner_prelude(doc_root: str, *, marker: str, sentinel: str) -> str:
    """Shell that locates an application's root and decides which account its CLI runs as.

    Shared by every application rather than written once per service, because this is the
    part that damages a site when it is wrong, and two copies of it would drift. The damage
    is the same shape for all of them: a command run as **root** writes root-owned files
    into the application's own writable folders — ``wp-content`` for WordPress,
    ``storage`` and ``bootstrap/cache`` for Laravel — and the application, which runs as the
    web-server user, can then no longer write there. Uploads stop; the next deploy fails.
    None of it happens at the moment of the command, which is what makes it easy to ship.

    ``marker`` is the file that identifies the application's root (``wp-load.php``,
    ``artisan``). The document root often IS that root, but a framework serving from
    ``public/`` keeps it one level up, so both are looked at rather than assumed.

    Emits ``SENTINEL|path|…`` and ``SENTINEL|owner|…``, or ``SENTINEL|error|noapp`` /
    ``|nosudo``, and leaves ``$APP_PATH``, ``$OWNER`` and ``$RUNAS`` set for the caller.
    """
    root = shlex.quote(doc_root or "")
    m = shlex.quote(marker)
    return f"""
_t() {{ local n=$1; shift; if command -v timeout >/dev/null 2>&1; then timeout "$n" "$@"; else "$@"; fi; }}

APP_PATH=""
for d in {root} {root}/.. ; do
  if [ -f "$d"/{m} ]; then APP_PATH=$(cd "$d" && pwd); break; fi
done
if [ -z "$APP_PATH" ]; then echo "{sentinel}|error|noapp"; exit 0; fi
echo "{sentinel}|path|$APP_PATH"

ME=$(id -un)
OWNER=$(stat -c%U "$APP_PATH" 2>/dev/null || echo "")
[ -z "$OWNER" ] && OWNER="$ME"
echo "{sentinel}|owner|$OWNER"

RUNAS=""
if [ "$OWNER" != "$ME" ]; then
  # -n so a server without passwordless sudo fails immediately rather than waiting for a
  # password nobody is there to type.
  if ! sudo -n -u "$OWNER" true 2>/dev/null; then echo "{sentinel}|error|nosudo"; exit 0; fi
  RUNAS="sudo -n -u $OWNER --"
fi
"""
