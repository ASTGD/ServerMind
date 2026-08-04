"""Copy a site to a new domain — on this server or another one. Ploi's "Clone site".

Ploi is admirably plain about what a clone does and does not include, and that honesty is
the part worth copying:

**Copied** — a new site on the chosen server, all of the site's files, and its repository
setup if it has one.
**Not copied** — a hand-edited web-server configuration, the HTTPS certificate, and **the
database**.

Those three are omissions on purpose. A config written for one domain does not describe
another. A certificate is issued *for* a domain, and copying its private key to a second
machine is the one thing certificates exist to prevent. And a database is a decision with
its own consequences, so it stays a separate, deliberate act.

**The trap, which Ploi's own screen does not mention.** The files are copied and the
database is not, so the clone's configuration file still names the ORIGINAL database, with
the original password. On a same-server clone those credentials still work — so the copy
quietly shares the live site's data, and anything typed into what the customer thinks is a
staging copy changes the real site. Nothing here can safely rewrite somebody's application
config, so the answer is to say it, unmissably, as the first thing after a clone finishes.

**Two things are checked before anything is copied, because both take down more than the
site being cloned:**

* whether the destination has room. Filling a disk stops every site on that machine, not
  just this one, and a half-copied site on a full disk is worse than no site at all;
* whether the payload contains PHP. If it does and the new site is created without PHP
  turned on, nginx hands `wp-config.php` to anyone who asks for it — the database password,
  downloadable. So the answer is read off the files themselves and defaults to ON.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass

#: Where a cross-server clone's archive is staged, on both machines.
STAGE_DIR = "/var/tmp"

#: How much more room the destination needs than the site measures. The archive lands
#: first and is then unpacked beside itself, so the peak is roughly twice the site — and a
#: disk filled to the last byte is its own kind of outage.
HEADROOM = 2.4

#: Files whose presence in the parent of a `public/` folder mean the application lives one
#: level up. Laravel and Symfony both serve `public/` and keep the application above it, so
#: copying only the served folder produces a clone that is a 500 page.
_APP_MARKERS = ("artisan", "composer.json", "package.json")

#: The placeholder page the empty-site installer writes. Recognised by its own words so a
#: clone never deletes a file the customer put there — and pinned by a test that reads the
#: real installer, because a reworded placeholder would silently stop being recognised and
#: the placeholder would then outrank the cloned site's own index.
PLACEHOLDER_MARK = "created by ServerAlly"


class CloneError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


@dataclass
class Survey:
    """What the source site actually is, read off the machine rather than assumed."""

    scope: str          # "app" (the folder above public/) or "docroot"
    source: str         # the folder that gets copied
    bytes: int
    files: int
    has_php: bool

    @property
    def app_scope(self) -> bool:
        return self.scope == "app"


def check_request(site, source_server, dest_server, dest_domain: str) -> str:
    """Everything that can be refused before a single byte moves. Returns the new domain.

    Deliberately strict about the destination domain: a clone writes files into whatever
    folder that domain resolves to, so a domain that already exists somewhere is refused by
    the create path rather than being merged into. The one case that has to be caught HERE
    is cloning a site onto itself, which the duplicate check would report as a confusing
    "already exists" rather than as what it is.
    """
    from app.services import site_service

    if getattr(source_server, "connection_type", None) != "ssh":
        raise CloneError("A site can only be cloned from a Linux server we reach over SSH.")
    if getattr(dest_server, "connection_type", None) != "ssh":
        raise CloneError("A site can only be cloned to a Linux server we reach over SSH.")
    if getattr(dest_server, "panel_type", None):
        raise CloneError(
            f"{dest_server.name} is managed by {dest_server.panel_type}, which owns its "
            f"web-server settings. Add the site through the panel instead — anything "
            f"written behind its back is invisible to it.")
    if not (getattr(site, "doc_root", None) or "").strip():
        raise CloneError(
            "We do not know which folder holds this site, so there is nothing to copy. "
            "Open the site and check its configuration first.")

    try:
        domain = site_service.clean_domain(dest_domain)
    except Exception as exc:  # InvalidDomain, defined in site_service
        raise CloneError(str(exc)) from exc
    if not site_service.is_real_domain(domain):
        raise CloneError(f"'{domain}' does not look like a domain name.")

    if str(dest_server.id) == str(site.server_id) and domain == site.domain:
        raise CloneError(
            f"That is the same site. Give the copy a different domain, or choose another "
            f"server to put {site.domain} on.")
    return domain


def site_type_for(survey: Survey) -> str:
    """What the copy is created as: an empty site, with PHP on or off.

    On when the files contain any PHP at all, and that is not a nicety. A PHP site served
    by a web server with no PHP handler does not fail — it hands the SOURCE of every file
    to anyone who asks, and `wp-config.php` holds the database password in clear text. So
    the question is answered by the files, and the safe answer is the default.
    """
    return "php" if survey.has_php else "static"


# ── Looking at the source ─────────────────────────────────────────────────────

def build_survey_command(doc_root: str) -> str:
    """Read what is there. Read-only, and bounded so a huge site cannot hang the request.

    Bounded matters more than it looks: our SSH channel gives up after 60 seconds of
    silence, so an unbounded `du` over a large site surfaces to the customer as a
    connection error rather than as "this is taking a while".
    """
    doc = shlex.quote((doc_root or "").rstrip("/"))
    markers = " ".join(shlex.quote(m) for m in _APP_MARKERS)
    return (
        f'set -e; '
        f'DOC={doc}; '
        f'[ -d "$DOC" ] || {{ echo "MISSING"; exit 3; }}; '
        f'SRC="$DOC"; SCOPE=docroot; '
        # Only a folder literally named `public` is widened, and only when its parent holds
        # something that says an application lives there. Widening on a guess would copy a
        # neighbour's files on a shared account home.
        f'case "$DOC" in */public) P="${{DOC%/public}}"; '
        f'  for m in {markers}; do '
        f'    if [ -f "$P/$m" ]; then SRC="$P"; SCOPE=app; break; fi; done ;; esac; '
        f'_t() {{ if command -v timeout >/dev/null 2>&1; then timeout "$@"; else shift; "$@"; fi; }}; '
        f'KB="$(_t 40 du -sk "$SRC" 2>/dev/null | awk \'NR==1{{print $1}}\')"; '
        # A size we could not measure is a refusal, not a guess. The fit check is the only
        # thing standing between a clone and a full disk, and a disk filled by us takes out
        # every other site on that machine.
        f'[ -n "$KB" ] || {{ echo "UNMEASURED"; exit 4; }}; '
        f'echo "SCOPE=$SCOPE"; echo "SRC=$SRC"; '
        f'echo "BYTES=$((KB * 1024))"; '
        f'echo "FILES=$(_t 30 find "$SRC" -type f 2>/dev/null | wc -l | tr -d " ")"; '
        f'if _t 30 find "$SRC" -type f -name "*.php" -print 2>/dev/null | head -1 | grep -q .; '
        f'  then echo "PHP=yes"; else echo "PHP=no"; fi'
    )


def parse_survey(output: str, code: int = 0) -> Survey:
    """Turn the probe's output into an answer, or a refusal a customer can act on."""
    text = output or ""
    if "MISSING" in text:
        raise CloneError(
            "This site's folder is not on the server any more, so there is nothing to "
            "copy.")
    if "UNMEASURED" in text or code == 4:
        raise CloneError(
            "We could not measure how big this site is, so we will not start copying it — "
            "a copy that fills the destination's disk would take every site on that server "
            "down. Try again in a moment.")

    fields: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip()

    source = fields.get("SRC", "")
    if not source:
        raise CloneError("We could not read this site's folder, so nothing was copied.")
    try:
        size = int(fields.get("BYTES") or 0)
    except ValueError:
        size = 0
    try:
        files = int(fields.get("FILES") or 0)
    except ValueError:
        files = 0
    return Survey(
        scope="app" if fields.get("SCOPE") == "app" else "docroot",
        source=source,
        bytes=size,
        files=files,
        # Anything other than a clear "no" means PHP stays on. The consequence of being
        # wrong in the other direction is publishing a database password.
        has_php=fields.get("PHP") != "no",
    )


def build_docroot_command(domain: str) -> str:
    """Ask the destination server which folder it serves this domain from.

    Read off the machine rather than worked out from the installer's variables. The formula
    is `<sites folder>/<domain>/public` today and a copy of it here would be a second answer
    to a question that already has one — the kind that is right until the day somebody
    changes the installer. Same technique the site guards and the PHP probe already use.
    """
    d = shlex.quote(domain)
    return (
        f'CFG="$(grep -rl -- {d} /etc/nginx /etc/apache2 /etc/httpd 2>/dev/null | head -1)"; '
        f'[ -n "$CFG" ] || {{ echo "NOCONFIG"; exit 3; }}; '
        f'R="$(grep -m1 -oE "(root|DocumentRoot)[[:space:]]+[^;[:space:]]+" "$CFG" '
        f'  | awk "{{print \\$2}}")"; '
        f'[ -n "$R" ] || {{ echo "NOROOT"; exit 4; }}; '
        f'echo "ROOT=$R"'
    )


def parse_docroot(output: str) -> str:
    for line in (output or "").splitlines():
        if line.startswith("ROOT="):
            root = line[5:].strip().rstrip("/")
            if root.startswith("/"):
                return root
    raise CloneError(
        "The new site was created, but we could not work out which folder it serves, so "
        "nothing was copied into it.")


def destination_target(scope: str, dest_doc_root: str) -> str:
    """Where the payload is unpacked on the destination.

    An app-scope copy holds the application's own folder — `public/` included — so it goes
    one level ABOVE the served folder. Unpacking it into the served folder instead would
    put the site one directory too deep and publish the application's source, `.env` and
    all, at a guessable address.

    So the two shapes have to agree, and a mismatch is refused rather than resolved. It
    cannot happen with the site we create here; that is exactly why it should stop the
    clone if it ever does.
    """
    root = (dest_doc_root or "").rstrip("/")
    if scope != "app":
        return root
    if not root.endswith("/public"):
        raise CloneError(
            "This site keeps its application above the folder it serves, and the new site "
            "is not laid out the same way. Copying it as it stands would publish the "
            "application's own files, so nothing was copied.")
    return root[: -len("/public")]


def build_fit_command(path: str) -> str:
    """How much room the destination has, at the nearest folder that exists.

    Walks up because the new site's own folder has not been made yet — asking `df` about a
    path that does not exist answers about nothing.
    """
    return (
        f'D={shlex.quote(path)}; '
        f'while [ ! -d "$D" ] && [ "$D" != / ]; do D="$(dirname "$D")"; done; '
        f"df -Pk \"$D\" 2>/dev/null | awk 'NR==2{{printf \"FREE=%d\\n\", $4 * 1024}}'"
    )


def parse_free(output: str) -> int | None:
    for line in (output or "").splitlines():
        if line.startswith("FREE="):
            try:
                return int(line[5:].strip())
            except ValueError:
                return None
    return None


def check_fit(size: int, free: int | None) -> None:
    """Refuse a copy the destination has no room for.

    Unknown free space is refused too. This check exists precisely because the failure it
    prevents is not this site breaking — it is the destination server's disk filling and
    every site on it stopping, which is not a risk to take on an unknown.
    """
    if free is None:
        raise CloneError(
            "We could not tell how much disk space the destination server has left, so we "
            "will not start copying onto it.")
    need = int(size * HEADROOM)
    if free < need:
        raise CloneError(
            f"There is not enough room. This site is {human(size)} and the destination "
            f"server has {human(free)} free — a copy needs about {human(need)}, because "
            f"the files are packed up and then unpacked again. Free some space, or choose "
            f"another server."
        )


def check_transfer_size(size: int, *, same_server: bool) -> None:
    """Cross-server copies go through us, so they carry a cap. Same-server ones do not.

    Stated rather than discovered halfway through: the two machines have no way to talk to
    each other — each has its own credential and neither holds a key for the other — so the
    archive travels down to ServerAlly and back up. That is a real limit and pretending
    otherwise would mean failing at 90%.
    """
    if same_server:
        return
    from app.services.file_service import MAX_TRANSFER_BYTES

    if size > MAX_TRANSFER_BYTES:
        raise CloneError(
            f"This site is {human(size)}, and a copy to a different server travels through "
            f"ServerAlly, which is capped at {human(MAX_TRANSFER_BYTES)}. Cloning to a new "
            f"domain on the SAME server has no such limit, because the files never leave "
            f"the machine."
        )


def human(size: int) -> str:
    step = float(max(size, 0))
    for unit in ("bytes", "KB", "MB", "GB"):
        if step < 1024 or unit == "GB":
            return f"{step:.0f} {unit}" if unit != "GB" else f"{step:.1f} GB"
        step /= 1024
    return f"{step:.1f} GB"


# ── Copying ───────────────────────────────────────────────────────────────────

def _clear_placeholder(dest: str) -> str:
    """Remove the empty-site placeholder page, and nothing else.

    The new site is seconds old and holds one file we wrote. It still has to go before the
    copy lands, because `index index.php index.html` means an `index.html` left behind can
    outrank the cloned site's own index — the clone would then serve "this site is ready"
    for ever and look like it had failed silently.

    Recognised by its own text rather than by us remembering we wrote it. A guard that
    depends on "trust me, I made this" is not a guard.
    """
    d = shlex.quote(dest)
    return (
        f'for f in {d}/index.html {d}/public/index.html; do '
        f'  if [ -f "$f" ] && grep -q {shlex.quote(PLACEHOLDER_MARK)} "$f" 2>/dev/null; '
        f'    then rm -f "$f"; fi; done; '
    )


def _no_nesting(src: str, dst: str) -> str:
    """Refuse a copy of a folder into itself or into its own child — that never terminates."""
    s, d = shlex.quote(src), shlex.quote(dst)
    return (
        f'case "{d}/" in {s}/*) echo "That copy would put a folder inside itself."; '
        f'  exit 5 ;; esac; '
        f'case "{s}/" in {d}/*) echo "That copy would put a folder inside itself."; '
        f'  exit 5 ;; esac; '
    )


def _while_it_works(work: str, note: str, *, on_fail: str) -> str:
    """Run something slow, and say so every twenty seconds while it runs.

    Not decoration. Our SSH channel gives up after **60 seconds of silence**, and copying
    files says nothing at all until it is finished — so the clone big enough to be worth
    watching is exactly the one that would be reported as a connection failure while it was
    working perfectly. The same lesson as the apt-lock wait: a long silent step needs a
    heartbeat or it looks like a dead connection.

    The status is taken from `wait`, so a failure inside the background job is still the
    failure of the whole command rather than something the loop swallows.
    """
    return (
        f'( {work} ) & _P=$!; _i=0; '
        f'while kill -0 "$_P" 2>/dev/null; do sleep 2; _i=$((_i + 1)); '
        f'  [ $((_i % 10)) -eq 0 ] && echo {shlex.quote(note)}; done; '
        f'if wait "$_P"; then :; else echo {shlex.quote(on_fail)}; exit 6; fi; '
    )


def build_local_copy_command(source: str, dest: str) -> str:
    """Copy on one machine, without an archive and without a size limit.

    `cp -a "$SRC/."` rather than `"$SRC"/*`: the `/.` is what brings the dotfiles — `.env`,
    `.htaccess`, `.git` — and a copy that quietly drops those is a clone missing exactly the
    files that make the site work. `-a` keeps permissions, ownership and symlinks as they
    were.
    """
    s, d = shlex.quote(source), shlex.quote(dest)
    return (
        f'set -e; '
        f'[ -d {s} ] || {{ echo "The site\'s folder is not there."; exit 3; }}; '
        f'[ -d {d} ] || {{ echo "The new site\'s folder was not created."; exit 4; }}; '
        + _no_nesting(source, dest)
        + _clear_placeholder(dest)
        + _while_it_works(f'cp -a {s}/. {d}/', "... still copying",
                          on_fail="The files could not be copied.")
        + f'echo "copied"'
    )


def archive_path(domain: str) -> str:
    """Where the archive is staged. Named for the domain so two clones cannot collide."""
    safe = "".join(c if c.isalnum() or c in "-." else "_" for c in domain)[:80]
    return f"{STAGE_DIR}/serverally-clone-{safe}.tar.gz"


def build_pack_command(source: str, archive: str) -> str:
    """Pack the site on the machine it lives on. Read-only as far as the site is concerned."""
    s, a = shlex.quote(source), shlex.quote(archive)
    return (
        f'set -e; '
        f'[ -d {s} ] || {{ echo "The site\'s folder is not there."; exit 3; }}; '
        f'rm -f {a}; '
        + _while_it_works(f'tar -C {s} -czf {a} .', "... still packing it up",
                          on_fail="The site could not be packed up.")
        + f'[ -s {a} ] || {{ echo "The site could not be packed up."; exit 4; }}; '
        f'echo "packed"'
    )


def build_unpack_command(archive: str, dest: str) -> str:
    """Unpack on the destination, then remove the archive whatever happened.

    The archive goes even when the unpack fails: it is a full copy of somebody\'s website
    sitting in a world-readable temp folder, and leaving it there because an unrelated step
    failed is not a defensible default.
    """
    a, d = shlex.quote(archive), shlex.quote(dest)
    return (
        f'set -e; '
        f'[ -f {a} ] || {{ echo "The copy did not arrive."; exit 3; }}; '
        f'[ -d {d} ] || {{ rm -f {a}; echo "The new site\'s folder was not created."; exit 4; }}; '
        + _clear_placeholder(dest)
        + f'_finish() {{ rm -f {a}; }}; trap _finish EXIT; '
        + _while_it_works(f'tar -C {d} -xzf {a}', "... still unpacking",
                          on_fail="The copy could not be unpacked on the destination server.")
        + f'echo "copied"'
    )


def build_discard_command(archive: str) -> str:
    """Throw an archive away. Only ever our own staged file, never a path from a caller."""
    a = shlex.quote(archive)
    return (
        f'case {a} in {STAGE_DIR}/serverally-clone-*) rm -f {a} ;; '
        f'  *) echo "Refusing that path."; exit 4 ;; esac; echo removed'
    )


# ── Saying what happened ──────────────────────────────────────────────────────

def database_warning(app_type: str | None, *, same_server: bool) -> str | None:
    """The sentence that matters most after a clone of an application.

    Only for something that actually has a database, so it is not noise on a copy of a
    static site — and worded differently for a same-server clone, because that is the case
    where the copied credentials still WORK and the danger is real rather than theoretical.
    """
    if (app_type or "") not in ("wordpress", "laravel", "php", "unknown"):
        return None
    if same_server:
        return (
            "The database was not copied — and the copied files still point at the "
            "ORIGINAL site's database, with credentials that work on this server. Until "
            "you give the copy its own database and change its settings, anything you "
            "change on the copy changes the live site."
        )
    return (
        "The database was not copied. The copied files still name the original site's "
        "database, so the clone will not connect until you create a database for it and "
        "update its settings."
    )


_OUTCOMES: dict[int, str] = {
    3: "The site's folder was not found, so nothing was copied.",
    4: "The new site's folder was not created, so there was nothing to copy into.",
    5: "The copy could not be unpacked on the destination server.",
}


def explain(code: int, output: str) -> tuple[bool, str]:
    if code == 0:
        return True, "The files were copied."
    if code in _OUTCOMES:
        return False, _OUTCOMES[code]
    tail = (output or "").strip().splitlines()
    return False, (tail[-1] if tail else "The files could not be copied.")
