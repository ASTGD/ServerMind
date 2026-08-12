"""Make a safe copy of a live website to try changes on.

Ploi's version of this is a creation-time convenience: it makes a second empty site with a
`staging.` prefix and search engines blocked, and copies nothing. In the owner's own test it
produced a half-installed WordPress beside a Laravel site. **An empty staging site is not a
staging site — it is a second empty site with a longer name.** So this one copies.

**One rule shapes every decision here: a staging copy must never be left pointing at the
live database.** Copy a live site's files and leave the configuration alone and the copy is
now WRITING to the live database — somebody "testing" a bulk delete deletes real orders.
That is not a warning to show; it is a reason to refuse. If the configuration cannot be
repointed, the whole thing is rolled back and nothing is left behind, because a staging site
connected to live data is worse than no staging site at all.

Two consequences worth stating:

* **for an app with a database, copying the database is not optional.** A WordPress staging
  site with an empty database shows the install wizard, which is exactly the half-built thing
  Ploi produced;
* **the copy is repointed, not stripped.** `.env` and `wp-config.php` are copied and then
  rewritten — a staging site with no configuration at all cannot boot, and cannot then be
  checked.
"""
from __future__ import annotations

import shlex

#: Never copied. Caches and dependency trees are rebuilt, and copying them wastes the disk
#: check's entire budget on files the copy does not need.
#:
#: `.git` is deliberately NOT here. A staging site with its history is more useful than one
#: without, and it is what makes "promote through the repository" possible later.
EXCLUDE = (
    "storage/framework/cache/*", "storage/framework/sessions/*",
    "storage/framework/views/*", "storage/logs/*",
    "node_modules", "bootstrap/cache/*.php",
    "wp-content/cache", "wp-content/uploads/cache",
    ".serverally-clone-*", "*.log",
)

#: How much more room than the source is needed. The copy lands beside the original and a
#: database dump is written and imported, so the peak is more than the site's own size.
HEADROOM = 1.6


class StagingError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def rsync_excludes() -> str:
    return " ".join(f"--exclude={shlex.quote(p)}" for p in EXCLUDE)


def needs_database(app_type: str | None) -> bool:
    """Whether a copy of this site is meaningless without its own database.

    WordPress and Laravel both store everything that makes the site a site in the database —
    posts, pages, users, settings. A copy without one is an install wizard.
    """
    return (app_type or "").lower() in ("wordpress", "laravel", "php")


def check_room(source_bytes: int, free_bytes: int | None) -> None:
    """Refuse a copy the disk cannot hold, with the real numbers.

    Filling a disk stops every site on that machine, not just this one — and an unmeasurable
    size is refused rather than guessed at, because the guess is the only thing standing
    between a staging copy and an outage.
    """
    if free_bytes is None:
        raise StagingError(
            "We could not tell how much disk space this server has left, so the copy was "
            "not started.")
    need = int(max(source_bytes, 0) * HEADROOM)
    if free_bytes < need:
        raise StagingError(
            f"This site is {human(source_bytes)} and the server has {human(free_bytes)} "
            f"free. A copy needs about {human(need)} — the files, plus a database dump "
            f"while it is being imported. Free some space first."
        )


def human(size: int) -> str:
    step = float(max(size, 0))
    for unit in ("bytes", "KB", "MB", "GB"):
        if step < 1024 or unit == "GB":
            return f"{step:.1f} GB" if unit == "GB" else f"{step:.0f} {unit}"
        step /= 1024
    return f"{step:.1f} GB"


#: Read the live site's database name out of its own configuration.
#:
#: Written with no literal quote characters, so the program survives being handed to a shell
#: as a single argument. `\047` is awk's own escape for an apostrophe — the value in a `.env`
#: may be bare, single-quoted or double-quoted, and all three mean the same database.
_ENV_DB_AWK = (
    r'/^DB_DATABASE=/ { v = substr($0, 13); gsub(/["\047]/, "", v); '
    r'gsub(/\r/, "", v); gsub(/^[ \t]+|[ \t]+$/, "", v); print v; exit }'
)

#: Which engine the live site talks to. A copy on a different engine is not a copy — and
#: `sqlite` is the one that matters most, because there is no server database to make at all:
#: the whole database is a FILE inside the site, so it travels with the copy already and
#: repointing `DB_DATABASE` at a database name would break it.
_ENV_CONN_AWK = (
    r'/^DB_CONNECTION=/ { v = substr($0, 15); gsub(/["\047]/, "", v); '
    r'gsub(/\r/, "", v); gsub(/^[ \t]+|[ \t]+$/, "", v); print v; exit }'
)

#: The same for WordPress. Splitting on the apostrophe makes the value the field two along
#: from the name, which holds for `define( 'DB_NAME', 'x' );` and `define('DB_NAME','x');`
#: alike — no regex to escape, and nothing that a password or a database name could break.
_WP_DB_AWK = (
    r'/define/ && /DB_NAME/ { for (i = 1; i <= NF; i++) '
    r'if ($i == "DB_NAME") { print $(i + 2); exit } }'
)


def build_survey_command(doc_root: str) -> str:
    """What is there and whether it will fit. Read-only, and bounded."""
    doc = shlex.quote((doc_root or "").rstrip("/"))
    return (
        f'set -e; DOC={doc}; '
        f'[ -d "$DOC" ] || {{ echo "MISSING"; exit 3; }}; '
        # Laravel and Symfony keep the application above the folder they serve, so copying
        # only the served folder produces a staging site that is a 500 page.
        f'SRC="$DOC"; SCOPE=docroot; '
        f'case "$DOC" in */public) P="${{DOC%/public}}"; '
        f'  for m in artisan composer.json; do '
        f'    if [ -f "$P/$m" ]; then SRC="$P"; SCOPE=app; break; fi; done ;; esac; '
        f'_t() {{ if command -v timeout >/dev/null 2>&1; then timeout "$@"; else shift; "$@"; fi; }}; '
        f'KB="$(_t 40 du -sk "$SRC" 2>/dev/null | awk \'NR==1{{print $1}}\')"; '
        f'[ -n "$KB" ] || {{ echo "UNMEASURED"; exit 4; }}; '
        f'echo "SCOPE=$SCOPE"; echo "SRC=$SRC"; echo "BYTES=$((KB * 1024))"; '
        f'D="$(dirname "$SRC")"; '
        f'echo "$(df -Pk "$D" 2>/dev/null | awk \'NR==2{{printf "FREE=%d", $4 * 1024}}\')"; '
        # Which configuration file will have to be repointed. If we cannot find one for an
        # app that needs a database, the copy is refused rather than created pointing at
        # live data.
        # Whether the copy needs PHP, answered by the FILES rather than by what we believe
        # this site is. A PHP site served with no PHP handler does not fail — it hands the
        # SOURCE of every file to anyone who asks, and wp-config.php holds the database
        # password in clear text. Anything but a clear "no" leaves PHP on.
        f'if _t 30 find "$SRC" -type f -name "*.php" -print 2>/dev/null | head -1 | grep -q .; '
        f'  then echo "PHP=yes"; else echo "PHP=no"; fi; '
        f'CFGF=""; '
        f'if [ -f "$SRC/.env" ]; then echo "CONFIG=laravel"; CFGF="$SRC/.env"; '
        f'elif [ -f "$SRC/wp-config.php" ]; then echo "CONFIG=wordpress"; CFGF="$SRC/wp-config.php"; '
        f'elif [ -f "$DOC/wp-config.php" ]; then echo "CONFIG=wordpress"; CFGF="$DOC/wp-config.php"; '
        f'else echo "CONFIG=none"; fi; '
        # WHICH database the live site uses. Without this the copy gets a database of its
        # own that is EMPTY — and an empty database is not a copy: WordPress renders it as
        # the install wizard, which is the exact half-built thing this feature exists to
        # avoid. Read here, while we are already looking, rather than in a second round trip.
        f'if [ -n "$CFGF" ]; then case "$CFGF" in '
        f'  *.env) SDB="$(awk {shlex.quote(_ENV_DB_AWK)} "$CFGF" 2>/dev/null)"; '
        f'         SEN="$(awk {shlex.quote(_ENV_CONN_AWK)} "$CFGF" 2>/dev/null)" ;; '
        f'  *) SDB="$(awk -F"\'" {shlex.quote(_WP_DB_AWK)} "$CFGF" 2>/dev/null)"; '
        # WordPress only ever speaks to MySQL or MariaDB, so there is nothing to read.
        f'     SEN=mysql ;; '
        f'esac; [ -n "${{SDB:-}}" ] && echo "SOURCE_DB=$SDB"; '
        f'[ -n "${{SEN:-}}" ] && echo "SOURCE_ENGINE=$SEN"; fi; true'
    )


def parse_survey(output: str, code: int = 0) -> dict:
    text = output or ""
    if "MISSING" in text:
        raise StagingError("This site's folder is not on the server, so there is nothing "
                           "to copy.")
    if "UNMEASURED" in text or code == 4:
        raise StagingError(
            "We could not measure how big this site is, so the copy was not started — a "
            "copy that fills the disk would take every site on this server down.")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            fields[k.strip()] = v.strip()
    if not fields.get("SRC"):
        raise StagingError("We could not read this site's folder, so nothing was copied.")

    def num(key: str) -> int | None:
        try:
            return int(fields[key])
        except (KeyError, ValueError):
            return None

    return {
        "scope": "app" if fields.get("SCOPE") == "app" else "docroot",
        "source": fields["SRC"],
        "bytes": num("BYTES") or 0,
        "free": num("FREE"),
        "config": fields.get("CONFIG", "none"),
        "source_db": fields.get("SOURCE_DB", ""),
        "engine": normalise_engine(fields.get("SOURCE_ENGINE", "")),
        # Anything other than a clear "no" means PHP stays on. Being wrong the other way
        # publishes a database password.
        "has_php": fields.get("PHP") != "no",
    }


def normalise_engine(value: str) -> str:
    """Which database engine the live site talks to: mysql, postgres or sqlite.

    A copy on a different engine is not a copy, so this is read from the site rather than
    chosen. MySQL is the fallback because it is what an unreadable or absent value almost
    always is — WordPress speaks nothing else, and it is Laravel's own default.
    """
    v = (value or "").strip().lower()
    if v in ("pgsql", "postgres", "postgresql"):
        return "postgres"
    if v == "sqlite":
        return "sqlite"
    return "mysql"


def check_can_copy_data(app_type: str | None, source_db: str, *,
                        engine: str = "mysql") -> bool:
    """Whether the copy gets its own database, filled with the live site's data.

    **For a site that keeps its content in a database this is not a choice**, and that is
    deliberate. Offering to skip it produces the one thing this feature exists to prevent:
    with no database of its own there is nothing to repoint the copy at, so it goes on
    reading and writing the LIVE site's data. Anyone who genuinely wants only the files
    wants *Clone site*, which is exactly that and says so.

    The refusal here is the twin of `check_can_repoint`. That one stops a copy that would
    WRITE to live data; this one stops a copy that would read from nothing — an application
    with a database of its own that is EMPTY is not a copy of anything. WordPress renders
    exactly that as the install wizard, which is the half-built thing Ploi's version produced
    and this feature exists to avoid.

    Returns whether to make one; raises when the data cannot be found.
    """
    if not needs_database(app_type):
        return False
    # SQLite keeps the whole database in a FILE inside the site, so the copy already has its
    # own the moment the files land. Making a database server account for it would be
    # pointless, and repointing `DB_DATABASE` — which holds a file path — at a database name
    # would break the copy outright.
    if engine == "sqlite":
        return False
    if not (source_db or "").strip():
        raise StagingError(
            "We could not tell which database this site uses, so the copy would have been "
            "made with an empty one — which is an install wizard, not a copy of your site. "
            "Nothing was created."
        )
    return True


def site_type_for(survey: dict) -> str:
    """What the staging site is created as: an empty site, with PHP on or off.

    Deliberately NOT the live site's own type. Creating the copy as `wordpress` would run
    the WordPress installer and build a fresh site we are about to overwrite — slower, and
    able to fail on its own. The copy's content comes from the copy.
    """
    return "php" if survey.get("has_php", True) else "static"


def check_can_repoint(app_type: str | None, config: str) -> None:
    """The refusal that gives this feature its meaning.

    An application that needs a database, whose configuration file we cannot find, cannot be
    repointed — so the copy would run against the LIVE database. Refused, and the message
    says why rather than describing a missing file, because the consequence is the point.
    """
    if not needs_database(app_type):
        return
    if config not in ("laravel", "wordpress"):
        raise StagingError(
            "This site stores its data in a database, but we could not find the file that "
            "tells it which database to use (.env or wp-config.php). Without that, the copy "
            "would read and write the LIVE site's data — someone testing a change would be "
            "changing the real site. So the copy was not made."
        )


def _db_lines(db_name: str, name: str, user: str, pw: str) -> str:
    """The three keys that point the copy at its own database — or nothing at all.

    Nothing at all when there is no database to point at: a SQLite site, whose database is a
    FILE that travelled with the copy, or a site that keeps nothing in one. Blanking the keys
    in that case would break a copy that was working.
    """
    if not db_name:
        return "  # No database of its own to point at — this site does not use one."
    return (f"  _set DB_DATABASE {name}\n"
            f"  _set DB_USERNAME {user}\n"
            f"  _set DB_PASSWORD {pw}")


def _db_readback(db_name: str) -> str:
    """Writing is not the same as having written — a rewrite can silently match nothing."""
    if not db_name:
        return "  :"
    return f'  grep -q "^DB_DATABASE={db_name}$" "$CFG" || FAILED=1'


def _wp_db_lines(db_name: str, name: str, user: str, pw: str) -> str:
    """WordPress's three, quoted the same way Laravel's are.

    A database name or a generated password reaches the shell as one word here, so it is
    quoted rather than trusted to contain nothing interesting.
    """
    if not db_name:
        return "  # No database of its own to point at."
    return (f"  _wpset DB_NAME {name}\n"
            f"  _wpset DB_USER {user}\n"
            f"  _wpset DB_PASSWORD {pw}")


def _wp_readback(db_name: str) -> str:
    if not db_name:
        return "  :"
    return f'  grep -q {shlex.quote(db_name)} "$CFG" || FAILED=1'


def build_stage_command(*, source: str, target: str, domain: str, source_domain: str,
                        config: str, db_name: str = "", db_user: str = "",
                        db_pass: str = "", php: str = "php") -> str:
    """Copy the site, give it its own database, and repoint it — or leave nothing behind.

    The order is the safety: everything that can be refused happens before the copy, the
    repoint happens before the site is ever served, and a repoint that fails removes the
    whole copy. There is no state in which a staging site exists pointing at live data.
    """
    src, dst = shlex.quote(source.rstrip("/")), shlex.quote(target.rstrip("/"))
    dom, sdom = shlex.quote(domain), shlex.quote(source_domain)
    name, user, pw = shlex.quote(db_name), shlex.quote(db_user), shlex.quote(db_pass)
    php_q = shlex.quote(php)

    if config == "laravel":
        # awk with `-v`, not `sed`. Two reasons, and the second is the one that bites:
        # `sed -i` needs an argument on BSD and not on GNU, so the same command cannot run
        # both places — and a sed REPLACEMENT treats `&` as "the whole match" and `|` as the
        # delimiter, so a generated password containing either would be silently written
        # wrong and the site would fail to connect with no explanation. An awk `-v` value is
        # a literal string with no metacharacters at all.
        repoint = f'''
CFG="$DST/.env"
[ -f "$CFG" ] || {{ echo ">>> ERROR: the copy has no .env to repoint."; FAILED=1; }}
if [ -z "$FAILED" ]; then
  _set() {{
    awk -v k="$1" -v v="$2" '
      BEGIN {{ done = 0 }}
      $0 ~ "^" k "=" {{ print k "=" v; done = 1; next }}
      {{ print }}
      END {{ if (!done) print k "=" v }}' "$CFG" > "$CFG.new" && mv "$CFG.new" "$CFG"
  }}
{_db_lines(db_name, name, user, pw)}
  _set APP_URL "https://{domain}"
  _set APP_ENV staging
  # On, because a staging site exists to show you what went wrong. Safe here for exactly
  # the reason it is not safe live: nobody else is looking.
  _set APP_DEBUG true
  # Proof, not assumption: read the value back out of the file we just wrote.
{_db_readback(db_name)}
fi
'''
    elif config == "wordpress":
        repoint = f'''
CFG="$DST/wp-config.php"
[ -f "$CFG" ] || CFG="$DST/public/wp-config.php"
[ -f "$CFG" ] || {{ echo ">>> ERROR: the copy has no wp-config.php to repoint."; FAILED=1; }}
if [ -z "$FAILED" ]; then
  # Literal string matching, not a regex. `define(` alone needs escaping in an awk regex,
  # and a value could contain anything — `index()` has no metacharacters at all. The quote
  # is built with sprintf so it never has to survive three layers of shell quoting.
  _wpset() {{
    awk -v k="$1" -v v="$2" '
      BEGIN {{ q = sprintf("%c", 39) }}
      index($0, "define") && index($0, q k q) {{
        print "define( " q k q ", " q v q " );"; next }}
      {{ print }}' "$CFG" > "$CFG.new" && mv "$CFG.new" "$CFG"
  }}
{_wp_db_lines(db_name, name, user, pw)}
{_wp_readback(db_name)}
  # Without this every link, image and redirect on the copy sends the visitor to the LIVE
  # site — which looks like the copy working and is the copy doing nothing.
  if [ -z "$FAILED" ] && command -v wp >/dev/null 2>&1; then
    (cd "$DST" && wp search-replace {sdom} {dom} --skip-columns=guid \\
      --allow-root --quiet >/dev/null 2>&1) || true
  fi
fi
'''
    else:
        repoint = "\n# Nothing to repoint — this site has no database configuration.\n"

    return f'''#!/bin/bash
set -uo pipefail
SRC={src}; DST={dst}; FAILED=""

[ -d "$SRC" ] || {{ echo ">>> ERROR: the live site's folder is not there."; exit 3; }}

# The copy lands on a site ServerAlly has just created, so the folder EXISTS and holds the
# placeholder page that site was given. Anything else in it is somebody's work, and is
# refused — the same rule `adopt_dir` follows in the shared site guards.
if [ -e "$DST" ]; then
  if find "$DST" -mindepth 1 \\
       ! -path "$DST/public" ! -path "$DST/public/index.html" \\
       ! -path "$DST/index.html" 2>/dev/null | grep -q .; then
    echo ">>> ERROR: $DST already exists. Nothing was changed."; exit 4
  fi
  # The placeholder must GO, not be copied over: a live WordPress brings an index.php, and
  # a leftover index.html wins — so the staging site would serve "your site is ready"
  # while reporting success.
  rm -rf "$DST"
fi

echo ">>> Copying the site"
mkdir -p "$DST"
# Copying a real site is minutes of SILENCE, and our SSH channel gives up after 60 seconds
# of it — so the copy big enough to be worth watching is exactly the one that would be
# reported as a connection failure while working perfectly. The same lesson the clone
# feature learned on a real server.
( rsync -a {rsync_excludes()} "$SRC/" "$DST/" >/dev/null 2>&1 ) & _P=$!
_i=0
while kill -0 "$_P" 2>/dev/null; do
  sleep 2; _i=$((_i + 1))
  [ $((_i % 10)) -eq 0 ] && echo ">>> still copying ($((_i * 2))s)"
done
if ! wait "$_P"; then
  rm -rf "$DST"; echo ">>> ERROR: the copy did not finish."; exit 5
fi

echo ">>> Pointing the copy at its own settings"
{repoint}

# THE rule. A staging site that reads and writes the live database is worse than no staging
# site, so a repoint that failed takes the whole copy with it rather than leaving something
# half-made that looks finished.
if [ -n "$FAILED" ]; then
  rm -rf "$DST"
  echo ">>> ERROR: the copy could not be given its own settings, so it was removed."
  echo "    Nothing was left pointing at the live site's data."
  exit 6
fi

# Ownership from the ORIGINAL, so the copy can write exactly what the live site can.
OWNER="$(stat -c %U:%G "$SRC" 2>/dev/null || true)"
[ -n "$OWNER" ] && chown -R "$OWNER" "$DST" 2>/dev/null || true

# Written LAST, and only here — past the FAILED check, so the record can only exist for a
# copy that really has its own database and really got repointed at it.
{build_record_db(domain, db_name, db_user, db_pass)}
echo ">>> The copy is ready at $DST"
'''


def creds_path(domain: str) -> str:
    """Where a site's own database is recorded on the server.

    Chosen by the REMOVER, not by us: `site-remove` drops the database named in
    `/root/<domain>_db.txt` and never guesses one from the domain, because guessing would
    drop a database belonging to another site. Every installer that makes a database writes
    this file; a staging copy makes one too, so it has to write it as well.
    """
    return f"/root/{domain}_db.txt"


def build_record_db(domain: str, db_name: str, db_user: str, db_pass: str) -> str:
    """Record the copy's own database, in the exact shape the remover reads.

    Two things depend on this file existing, and both were broken without it:

    1. **Removing the copy leaves its database behind.** `site-remove` reads the `database:`
       and `user:` lines here; with no file it says so honestly and removes nothing, so
       every copy an agency makes and deletes orphans a database with a password nobody
       has, and no way to tell later which orphans are safe to drop.
    2. **The password exists nowhere the owner can reach.** It is generated for the copy and
       written into its wp-config or .env and nowhere else. This is the same root-only
       record every installer leaves.

    Returns an empty string when there is no database — a copy of a site that has none must
    not leave a file claiming otherwise, because the remover would then try to drop a
    database called nothing.
    """
    if not (db_name and db_user):
        return ""
    dom = shlex.quote(domain)
    creds = shlex.quote(creds_path(domain))
    # `printf` with the values as ARGUMENTS: a password is data, and putting it in the
    # format string would let a `%` in it be read as a directive.
    return f'''
printf 'Staging database for %s\\n\\ndatabase: %s\\nuser:     %s\\npassword: %s\\n' \\
  {dom} {shlex.quote(db_name)} {shlex.quote(db_user)} {shlex.quote(db_pass)} > {creds}
chmod 600 {creds}
echo ">>> Recorded this copy's database in {creds_path(domain)} (root only)"
'''


def build_forget_db_record(domain: str) -> str:
    """Remove that record when the copy is thrown away.

    The record names a database; if the copy is undone the database is dropped, and a file
    left behind would point the remover at something that no longer exists.
    """
    return f"rm -f {shlex.quote(creds_path(domain))}"


def build_discard_command(target: str) -> str:
    """Remove a copy that could not be finished.

    This is the only destructive command in the feature, so the path is checked ON the
    machine as well as here — a guard that exists in Python but not in the shell is not a
    guard. It only ever runs against a folder the SERVER told us it serves the new staging
    site from, never against anything a caller supplied.
    """
    dst = shlex.quote(target.rstrip("/"))
    return (
        f'D={dst}; '
        f'case "$D" in /|/home|/var|/var/www|/usr|/etc|/root) '
        f'  echo "REFUSED"; exit 1 ;; esac; '
        # Anything shallower than three parts is a system folder, not a website.
        f'[ "$(echo "$D" | awk -F/ \'{{print NF - 1}}\')" -ge 3 ] || {{ echo "REFUSED"; exit 1; }}; '
        f'rm -rf "$D"; echo "discarded"'
    )


_OUTCOMES: dict[int, str] = {
    3: "The live site's folder is not on the server, so there was nothing to copy.",
    4: "A folder for the copy already exists, so nothing was changed.",
    5: "The files could not be copied, and the half-made copy was removed.",
    6: ("The copy could not be given its own database settings, so it was removed entirely. "
        "Nothing was left pointing at the live site's data — which is the point: a staging "
        "site connected to live data is worse than no staging site."),
}


def explain(code: int, output: str) -> tuple[bool, str]:
    if code == 0:
        return True, ("The copy is ready. It has its own database and its own settings, so "
                      "nothing you do on it can reach the live site.")
    if code in _OUTCOMES:
        return False, _OUTCOMES[code]
    tail = [ln for ln in (output or "").strip().splitlines() if ln.startswith(">>> ERROR")]
    return False, (tail[-1].replace(">>> ERROR: ", "") if tail
                   else "The staging copy could not be made.")


# ── Copying the data ──────────────────────────────────────────────────────────

def build_copy_data_command(*, engine: str, source_db: str, target_db: str) -> str:
    """Dump the live database and import it into the copy's own.

    **The dump never carries a password on a command line.** The engines are reached as the
    local superuser over a socket, exactly as the database manager already does — and the
    dump file is created mode-600 and removed afterwards, because between those two moments
    it is a complete copy of the customer's data sitting on disk.

    Refuses rather than continues on an empty dump: an import that "succeeded" against zero
    bytes leaves a staging site whose database exists and is empty, which for WordPress is
    the install wizard — the exact half-built thing this feature exists to avoid.
    """
    src, dst = shlex.quote(source_db), shlex.quote(target_db)
    if engine == "postgres":
        dump, load = f"pg_dump {src}", f"psql -q {dst}"
        who = "sudo -u postgres "
    else:
        dump, load = f"mysqldump --single-transaction --quick {src}", f"mysql {dst}"
        who = ""
    return (
        f'set -e; '
        f'D="$(mktemp)"; chmod 600 "$D"; '
        "trap 'rm -f \"$D\"' EXIT; "
        f'{who}{dump} > "$D" 2>/dev/null || {{ echo "DUMPFAILED"; exit 7; }}; '
        # An empty dump is not a successful copy. Importing it produces a database that
        # exists and holds nothing, which WordPress renders as the install wizard.
        f'[ -s "$D" ] || {{ echo "EMPTYDUMP"; exit 8; }}; '
        f'{who}{load} < "$D" 2>/dev/null || {{ echo "IMPORTFAILED"; exit 9; }}; '
        f'echo "bytes=$(wc -c < "$D" | tr -d " ")"; echo "copied"'
    )


DATA_OUTCOMES: dict[int, str] = {
    7: ("The live site's database could not be read, so the copy has no data. Nothing was "
        "left connected to the live database."),
    8: ("The live site's database came back empty, so there was nothing to copy. A staging "
        "site with an empty database is an install wizard, not a copy — so it was not made."),
    9: ("The data could not be loaded into the copy's own database, so the copy has no "
        "data of its own."),
}


def explain_data(code: int, output: str) -> tuple[bool, str]:
    if code == 0:
        for line in (output or "").splitlines():
            if line.startswith("bytes="):
                return True, f"Copied {human(int(line[6:] or 0))} of data."
        return True, "The data was copied."
    return False, DATA_OUTCOMES.get(code, "The data could not be copied.")
