"""Operating a Laravel site: what state it is in, and the few commands that fix it.

The registry's second entry, and deliberately not shaped like the first. WordPress is
content you administer — plugins, themes, users. Laravel is a codebase you deploy, so the
questions are different ones: is it in production mode, are there migrations waiting, is the
config cached, is anything actually running the queue and the scheduler.

Everything goes through **artisan**, the tool Laravel itself is administered with.

Two findings here are worth the whole screen, because neither is visible from outside and
both are common:

- **APP_DEBUG left on in production.** Laravel's debug page prints the stack trace *and the
  environment* — database password included — to anybody who can make the site throw an
  error. It is the single most damaging Laravel misconfiguration there is.
- **No scheduler entry in cron.** Laravel runs every scheduled job through one crontab line.
  Without it nothing scheduled ever runs, and nothing anywhere reports a failure, because
  from the application's point of view nothing was ever asked to happen.

The ownership rule is shared with every other application (``app_registry.owner_prelude``):
artisan run as root leaves root-owned files in ``storage`` and ``bootstrap/cache``, and the
site — running as the web-server user — then cannot write its own logs, sessions or cache.
"""
from __future__ import annotations

import logging
import re

from app.models.server import Server
from app.services import app_registry, connection_manager

logger = logging.getLogger(__name__)

_S = "___SM_LARAVEL___"
_T = 25


class LaravelError(Exception):
    """Something the customer can read and act on."""


def _prelude(doc_root: str) -> str:
    """Locate the app, choose the account, and resolve php to an absolute path."""
    return app_registry.owner_prelude(doc_root, marker="artisan", sentinel=_S) + f"""
# Absolute, because the command may run through sudo, which replaces PATH with its own
# secure_path — looking php up as ourselves and running it as somebody else is how a check
# passes and the command after it fails.
# The default `php` is often NOT the one this site runs under. On a real CyberPanel box
# /usr/bin/php is 8.3 while the site runs 8.4, and Composer's platform check then aborts
# EVERY artisan command with a fatal error — found the hard way on a live server. So the
# candidates are tried newest-first and each is asked the only question that decides it:
# can it actually boot this application? `artisan --version` runs the autoloader and the
# platform check, so a PHP that answers it is a PHP that can run the commands below.
PHP_BIN=""
# /usr/local/bin is the default prefix when PHP is built from source, and it is where the
# official images put it too. Leaving it out reported "we could not find PHP" on a machine
# that plainly had it, and every Laravel action failed with it — found by running these
# against a real Laravel rather than by reading the list. `command -v` comes last, so an
# explicit versioned binary still wins; each candidate is still proved by `artisan --version`
# below, so widening the search can never pick a wrong one.
for _c in $(ls -d /usr/local/lsws/lsphp*/bin/php /usr/bin/php8* /usr/local/bin/php8* \
                  /usr/bin/php /usr/local/bin/php 2>/dev/null | sort -rV) \
          $(command -v php 2>/dev/null); do
  [ -x "$_c" ] || continue
  if [ -f "$APP_PATH/artisan" ] \
     && $RUNAS "$_c" "$APP_PATH/artisan" --version >/dev/null 2>&1; then
    PHP_BIN="$_c"; break
  fi
  [ -z "$PHP_BIN" ] && PHP_BIN="$_c"   # a fallback, so the error below stays accurate
done
if [ -z "$PHP_BIN" ]; then echo "{_S}|error|nophp"; exit 0; fi
# Composer's autoloader is what artisan boots from. Without it every command below dies with
# a PHP fatal, which the redirects turn into silence — and silence renders as a healthy app
# with nothing to report.
if [ ! -f "$APP_PATH/vendor/autoload.php" ]; then echo "{_S}|error|novendor"; exit 0; fi
ART="$RUNAS $PHP_BIN $APP_PATH/artisan"
"""


def build_probe_command(doc_root: str) -> str:
    """One read-only round trip. Nothing here writes, and a test asserts it."""
    return _prelude(doc_root) + f"""
echo "{_S}|php|$($PHP_BIN -r 'echo PHP_VERSION;' 2>/dev/null)"
# The BINARY, not just its version. Anything that later runs artisan for this site has to
# use the same one — the default `php` may be too old to boot the app at all.
echo "{_S}|phpbin|$PHP_BIN"
echo "{_S}|version|$(_t {_T} $ART --version 2>/dev/null | head -1)"

# `about` answers from the BOOTED application, which is the only authority once the config
# has been cached: after `artisan config:cache`, Laravel stops reading .env entirely, so a
# .env saying APP_DEBUG=false can sit above a live site that is running with debug ON.
# Reading the file would report the reassuring value and be wrong exactly when it matters.
echo "{_S}|about|$(_t {_T} $ART about --json --no-ansi 2>/dev/null | tr -d '\\n')"

# Fallback for Laravel 8 and older, which has no `about`. Only these two lines are read out
# of .env, never the file — it also holds the database password, and this screen has no
# business carrying one (the same rule the discovery probe follows about wp-config.php).
# A .env line carries whatever follows the value:
#     APP_DEBUG=false     # MUST be false in production
# Taking everything after the "=" swallows the comment too. Harmless for "false" — but
# reverse it, `APP_DEBUG=true  # turn off before launch`, and the value stops equalling
# "true", so debug reads as OFF on a site that has it ON. That is a false negative on the
# most important finding here, and it was found on a real .env that carries exactly that
# comment.
_envval() {{ grep -m1 "^$1=" "$APP_PATH/.env" 2>/dev/null | cut -d= -f2- \\
  | sed -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \\
  | tr -d '\\"'\\'''; }}
echo "{_S}|env|$(_envval APP_ENV)"
echo "{_S}|debug|$(_envval APP_DEBUG)"

# Which of the production caches are warm. A cached config that no longer matches .env is
# the classic "my change did nothing" — so it is shown, not hidden.
[ -f "$APP_PATH/bootstrap/cache/config.php" ] && echo "{_S}|cache_config|yes" || echo "{_S}|cache_config|no"
ls "$APP_PATH"/bootstrap/cache/routes*.php >/dev/null 2>&1 \\
  && echo "{_S}|cache_routes|yes" || echo "{_S}|cache_routes|no"
[ -f "$APP_PATH/bootstrap/cache/events.php" ] && echo "{_S}|cache_events|yes" || echo "{_S}|cache_events|no"

# `artisan down` writes this. Checked as a file rather than asked of artisan, because a site
# people take down is often one that is already too broken to answer.
{{ [ -f "$APP_PATH/storage/framework/down" ] || [ -f "$APP_PATH/storage/framework/maintenance.php" ]; }} \\
  && echo "{_S}|maintenance|yes" || echo "{_S}|maintenance|no"

# Uploads are served through this symlink; without it every uploaded image 404s.
[ -L "$APP_PATH/public/storage" ] && echo "{_S}|storage_link|yes" || echo "{_S}|storage_link|no"

# Needs the database, so it is bounded and its FAILURE is not the same as "none pending".
echo "{_S}|migrations|$(_t {_T} $ART migrate:status --no-ansi 2>/dev/null | tr -d '\\r' | tr '\\n' '~')"

# Something has to be running these, and on most broken Laravel sites nothing is.
# Our own shell's arguments contain this pattern's text, so it must not count itself. It
# happens not to today — the parentheses are regex syntax rather than literal characters —
# but that is luck, and a self-matching grep is a mistake this codebase has made before.
if pgrep -f "artisan queue:(work|listen)" 2>/dev/null | grep -qvx -e "$$" -e "$PPID"; then
  echo "{_S}|queue|yes"
else
  echo "{_S}|queue|no"
fi
(crontab -l 2>/dev/null; crontab -l -u "$OWNER" 2>/dev/null; cat /etc/cron.d/* 2>/dev/null) \\
  | grep -q "schedule:run" && echo "{_S}|scheduler|yes" || echo "{_S}|scheduler|no"
true
"""


_ERRORS = {
    "noapp": "This site does not look like a Laravel application — no artisan file in its "
             "folder.",
    "nophp": "PHP is not installed on this server, so Laravel cannot run here.",
    "novendor": "This Laravel application has no vendor folder, so it cannot start. Its "
                "dependencies have never been installed — run composer install, or deploy "
                "it again.",
    "nosudo": "We could not run commands as the account that owns this site's files. "
              "Running them as root instead would leave files Laravel itself cannot write "
              "to, so nothing was run.",
}

#: `migrate:status` lists one row per migration. The word we count is the one Laravel prints
#: in the "Ran?" column for a migration that has not been applied.
_PENDING = re.compile(r"\bPending\b", re.I)


def _on(value) -> bool:
    """Is this Laravel flag on?

    ``about --json`` reports these inconsistently across versions — a real boolean in some,
    and one of ``ENABLED``/``OFF``/``ON``/``DISABLED`` in others — so both are read rather
    than one being assumed. Anything unrecognised counts as OFF, because these flags drive
    warnings and inventing one would train people to ignore them.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "on", "enabled", "yes")


def _about(raw: str) -> dict:
    """The flat facts out of ``artisan about --json``, or nothing.

    Flattened because the sections it groups them under have been renamed between versions,
    while the leaf names have not. Never raises: a Laravel too old for `about` prints a usage
    error, and this simply falls back to the files.
    """
    import json

    raw = (raw or "").strip()
    if not raw.startswith("{"):
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    flat: dict = {}
    for section, body in (data.items() if isinstance(data, dict) else []):
        if isinstance(body, dict):
            for k, v in body.items():
                flat.setdefault(str(k).lower(), v)
            flat[f"__section__{str(section).lower()}"] = body
    return flat


def _cached(about: dict, what: str, fallback: str | None) -> bool:
    """Whether one of the production caches is warm.

    ``about`` groups these under a "cache" section, read directly because the flattened
    lookup would collide with other keys. Its values are a real BOOLEAN in Laravel 11/12 and
    the strings ``CACHED``/``NOT CACHED`` in older ones — reading only the strings called a
    fully cached production application uncached.
    """
    section = about.get("__section__cache")
    if isinstance(section, dict) and what in {str(k).lower() for k in section}:
        value = next(v for k, v in section.items() if str(k).lower() == what)
        # Laravel 11/12 report a real boolean here; older versions report the strings
        # CACHED / NOT CACHED. Reading only the strings called a fully cached production
        # application uncached, which was found by looking at a real one.
        if isinstance(value, bool):
            return value
        return str(value).strip().upper() == "CACHED"
    return fallback == "yes"


def parse_probe(stdout: str) -> dict:
    """Turn probe output into what the screen shows. Pure, so every state is testable."""
    fields: dict[str, str] = {}
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith(_S):
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            fields[parts[1]] = parts[2].strip()

    if "error" in fields:
        return {"ok": False, "reason": _ERRORS.get(fields["error"],
                                                   "Laravel could not be read here.")}

    # Every artisan call redirects stderr so a warning cannot corrupt what it captures, which
    # makes a failure silent — and silence renders as a healthy app with nothing to report.
    # The version string is the proof artisan actually booted.
    version_line = fields.get("version", "")
    if not version_line:
        return {"ok": False,
                "reason": "Laravel is here, but artisan could not start. The application "
                          "may be misconfigured, or its files may belong to a different "
                          "account."}

    raw_migrations = fields.get("migrations", "")
    # An empty answer means the command could not reach the database. That is NOT the same as
    # "nothing is pending", and reporting zero would be a reassuring guess.
    migrations_known = bool(raw_migrations.strip())
    pending = len(_PENDING.findall(raw_migrations)) if migrations_known else 0

    # `about` wins wherever it answers, because it reports the RUNNING configuration; .env is
    # only consulted for a Laravel too old to have it.
    about = _about(fields.get("about", ""))
    env = (about.get("environment") or fields.get("env", "") or "").strip().lower()
    debug = (_on(about["debug_mode"]) if "debug_mode" in about
             else (fields.get("debug", "") or "").strip().lower() in ("true", "1", "on", "yes"))

    return {
        "ok": True,
        "path": fields.get("path", ""),
        "runs_as": fields.get("owner", ""),
        "php_version": about.get("php_version") or fields.get("php", ""),
        "php_bin": fields.get("phpbin", ""),
        # "Laravel Framework 11.9.2" — the number is what anyone actually wants.
        "version": (about.get("laravel_version")
                    or (version_line.split()[-1] if version_line else "")),
        "version_line": version_line,
        "environment": env or "unknown",
        "debug": debug,
        # The finding that matters most: a debug page prints the environment, database
        # password included, to whoever can make the site throw an error.
        "debug_in_production": debug and env == "production",
        "pending_migrations": pending,
        "migrations_known": migrations_known,
        "cache_config": _cached(about, "config", fields.get("cache_config")),
        "cache_routes": _cached(about, "routes", fields.get("cache_routes")),
        "cache_events": _cached(about, "events", fields.get("cache_events")),
        "maintenance": (_on(about["maintenance_mode"]) if "maintenance_mode" in about
                        else fields.get("maintenance") == "yes"),
        "storage_link": fields.get("storage_link") == "yes",
        "queue_worker": fields.get("queue") == "yes",
        "scheduler": fields.get("scheduler") == "yes",
    }


async def read(server: Server, doc_root: str) -> dict:
    """Everything the Laravel section shows. Never raises."""
    try:
        stdout, _stderr, _code = await connection_manager.execute(
            server, build_probe_command(doc_root))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Laravel probe failed on %s: %s", server.host, exc)
        return {"ok": False, "reason": "We could not reach the server to look."}
    return parse_probe(stdout)


# --- Actions ------------------------------------------------------------------------------
#
# Each is ONE named artisan command, never something the caller composes. None of them takes
# a target, so there is no customer input in any of these command lines at all.

#: Grouped the way Ploi groups them, because 20 buttons in a row is a wall and the groups
#: are how somebody finds the one they came for. Every entry is ONE named artisan command
#: chosen from this map — never something the caller composes.
ACTIONS: dict[str, dict] = {
    # Caches — the everyday ones.
    "optimize": {"group": "Optimise", "label": "Cache everything",
                 "cmd": "optimize", "t": 120,
                 "blurb": "Cache the configuration, routes and views so pages load faster."},
    "clear": {"group": "Optimise", "label": "Clear everything",
              "cmd": "optimize:clear", "t": 120,
              "blurb": "Clear every cache. Safe, and the first thing to try when a change "
                       "does not appear."},
    "cache_clear": {"group": "Cache", "label": "Clear application cache",
                    "cmd": "cache:clear", "t": 120,
                    "blurb": "Empty the data the application itself cached."},
    "config_clear": {"group": "Config", "label": "Clear config cache",
                     "cmd": "config:clear", "t": 60,
                     "blurb": "Read the settings from the files again."},
    "config_cache": {"group": "Config", "label": "Cache the config",
                     "cmd": "config:cache", "t": 60,
                     "blurb": "Faster, but the settings file is then ignored until you "
                              "clear it again."},
    "route_cache": {"group": "Routes", "label": "Cache the routes",
                    "cmd": "route:cache", "t": 60,
                    "blurb": "Faster page routing. Some applications cannot use this."},
    "route_clear": {"group": "Routes", "label": "Clear the route cache",
                    "cmd": "route:clear", "t": 60, "blurb": "Undo route caching."},
    "view_cache": {"group": "Views", "label": "Compile the templates",
                   "cmd": "view:cache", "t": 120,
                   "blurb": "Compile every page template up front."},
    "view_clear": {"group": "Views", "label": "Clear compiled templates",
                   "cmd": "view:clear", "t": 60,
                   "blurb": "Throw the compiled templates away and build them again."},

    # Database.
    "migrate": {"group": "Database", "label": "Run migrations",
                "cmd": "migrate --force", "t": 300,
                "blurb": "Apply the database changes this version of the code needs."},

    # Availability.
    "down": {"group": "General", "label": "Maintenance mode on",
             "cmd": "down", "t": 60,
             "blurb": "Show visitors a maintenance page instead of the site."},
    "up": {"group": "General", "label": "Maintenance mode off",
           "cmd": "up", "t": 60, "blurb": "Put the site back."},

    # Queue.
    "queue_restart": {"group": "Queue", "label": "Restart the workers",
                      "cmd": "queue:restart", "t": 60,
                      "blurb": "Make the background workers pick up the new code. Without "
                               "this they keep running the previous version."},
    "queue_retry_all": {"group": "Queue", "label": "Retry every failed job",
                        "cmd": "queue:retry all", "t": 120,
                        "blurb": "Put the failed jobs back in the queue to be tried again."},
    "queue_flush": {"group": "Queue", "label": "Delete the failed jobs",
                    "cmd": "queue:flush", "t": 60,
                    "blurb": "Throw away the record of every failed job. They cannot be "
                             "retried afterwards."},

    # Scheduler and storage.
    "schedule_run": {"group": "Scheduler", "label": "Run due tasks now",
                     "cmd": "schedule:run", "t": 300,
                     "blurb": "Run whatever the scheduler is due to run, immediately."},
    "storage_link": {"group": "Storage", "label": "Link the uploads folder",
                     "cmd": "storage:link", "t": 60,
                     "blurb": "Make uploaded files reachable from the web."},
}

#: The ones a customer should be asked about first, and WHY — because "are you sure" with no
#: reason teaches people to click through it.
#:
#: `migrate` can lose data (a migration may drop a column); it is still offered, because a
#: deploy is not finished without it. `queue:flush` destroys the record of work that failed,
#: so nobody can ever see what went wrong or retry it. `queue:retry all` re-runs jobs that
#: may have half-succeeded — the classic outcome is a customer charged or emailed twice.
#: `schedule:run` fires real scheduled work outside its schedule.
DESTRUCTIVE = {"migrate", "queue_flush", "queue_retry_all", "schedule_run"}

#: Artisan commands nobody should reach through a web panel, whatever they type. Each one
#: EMPTIES the database, and there is no undo anywhere in this system.
#:
#: Refused rather than confirmed: a confirmation is a thing people click, and the cost here
#: is the customer's entire dataset. Somebody who genuinely means it has a terminal.
FORBIDDEN_COMMANDS = ("db:wipe", "migrate:fresh", "migrate:reset", "migrate:refresh",
                      "migrate:rollback", "tinker")


def build_action_command(action: str, doc_root: str) -> str:
    """One named command from the map above. The key indexes a table; there is no path by
    which caller text becomes part of the command line."""
    spec = ACTIONS.get(action)
    if spec is None:
        raise LaravelError(f"'{action}' is not something we can do to a Laravel site.")
    # `migrate --force` carries its flag in the map because artisan otherwise refuses to run
    # migrations unattended in production, and there is nobody at a terminal to confirm.
    return _prelude(doc_root) + f"_t {spec['t']} $ART {spec['cmd']} --no-ansi" + "\n"


def check_custom(command: str) -> str:
    """A command the customer typed. Returns it cleaned, or refuses.

    Ploi offers this and it is genuinely useful — an application's own commands are the whole
    reason artisan exists. The bound is not a list of what is allowed (we cannot know a
    customer's own command names) but a list of what is REFUSED, plus a shape that cannot
    become a second command.
    """
    raw = command or ""
    # Newlines FIRST, before whitespace is normalised. Collapsing them into spaces would turn
    # a two-line paste into one command with surprise arguments — silently, and the check
    # below could then never fire on the character it names.
    if "\n" in raw or "\r" in raw:
        raise LaravelError("One artisan command at a time — that looks like more than one "
                           "line.")
    text = " ".join(raw.split())
    if not text:
        raise LaravelError("Type an artisan command to run.")
    if len(text) > 200:
        raise LaravelError("That command is too long.")

    # A shell metacharacter would let one command become several. The command is quoted
    # before it reaches the shell as well, so this is the second layer, not the only one —
    # but a message naming the character beats a mysterious quoting failure.
    bad = set(text) & set(";|&`$><\n\\\"'")
    if bad:
        raise LaravelError(
            f"Remove {' '.join(sorted(bad))} — one artisan command at a time, and no shell "
            f"characters.")
    if text.split()[0] in ("php", "artisan", "./artisan"):
        raise LaravelError("Just the artisan command itself, for example `about` or "
                           "`app:send-invoices`.")

    name = text.split()[0].lower()
    if name in FORBIDDEN_COMMANDS:
        raise LaravelError(
            f"`{name}` empties the database, and nothing in ServerAlly can undo that. "
            f"If you really mean it, run it over SSH where you can see what you are doing.")
    return text


def build_custom_command(command: str, doc_root: str) -> str:
    import shlex

    safe = check_custom(command)
    # Quoted WORD BY WORD, not as one string. `shlex.quote` on the whole thing would hand
    # artisan a single argument literally named "app:send-invoices --dry", which is not a
    # command — the same mistake the daemons work made with systemd's ExecStart, inverted.
    # The quoting is the second layer; the validation above is what makes it correct.
    words = " ".join(shlex.quote(w) for w in safe.split())
    return _prelude(doc_root) + f"_t 300 $ART {words} --no-ansi\n"


async def act(server: Server, doc_root: str, action: str) -> dict:
    """Run one action and report honestly what happened.

    artisan's own message names the real problem — a syntax error in a migration, a database
    it cannot reach, a folder it cannot write — far better than anything written here.
    """
    try:
        stdout, stderr, code = await connection_manager.execute(
            server, build_action_command(action, doc_root))
    except Exception as exc:  # noqa: BLE001
        raise LaravelError(f"We could not reach the server: {exc}") from exc

    output = (stdout or "") + (("\n" + stderr) if stderr else "")
    for marker, message in _ERRORS.items():
        if f"{_S}|error|{marker}" in output:
            raise LaravelError(message)
    body = "\n".join(l for l in output.splitlines() if not l.startswith(_S)).strip()
    if code != 0:
        raise LaravelError(body[-600:] or "Laravel reported a failure.")
    return {"output": body}


async def act_custom(server: Server, doc_root: str, command: str) -> dict:
    """Run a command the customer typed, and report exactly what artisan said.

    Its own message is the useful part — a command that does not exist, a missing argument,
    an exception inside the job — and nothing written here could improve on it.
    """
    from app.services.secret_redact import redact_secrets

    try:
        stdout, stderr, code = await connection_manager.execute(
            server, build_custom_command(command, doc_root))
    except Exception as exc:  # noqa: BLE001
        raise LaravelError(f"We could not reach the server: {exc}") from exc

    output = (stdout or "") + (("\n" + stderr) if stderr else "")
    for marker, message in _ERRORS.items():
        if f"{_S}|error|{marker}" in output:
            raise LaravelError(message)
    body = "\n".join(l for l in output.splitlines() if not l.startswith(_S)).strip()
    text, hidden = redact_secrets(body[:_MAX_OUTPUT])
    return {"ok": code == 0, "output": text, "hidden": hidden,
            "trimmed": len(body) > _MAX_OUTPUT}


# --- Reads --------------------------------------------------------------------------------
#
# Kept as their own map rather than mixed into ACTIONS, and that separation is the point: a
# read and a write are different kinds of thing, and one list holding both is one typo away
# from a "look at this" button that changes the site. Nothing here alters anything — the
# guarantee is asserted by a test, not by intention.
#
# Until now we shipped only the WRITING half: we could run migrations but not show which were
# pending, restart the queue but not show what had failed. That is backwards for
# troubleshooting, which is what somebody opens this screen to do.

READS: dict[str, dict] = {
    "about": {
        "label": "Overview",
        "blurb": "Laravel and PHP versions, the environment, and which drivers are in use.",
        "cmd": "about --no-ansi",
        "timeout": 60,
    },
    "migrate_status": {
        "label": "Migrations",
        "blurb": "Which database migrations have run, and which are still waiting.",
        "cmd": "migrate:status --no-ansi",
        "timeout": 120,
    },
    "route_list": {
        "label": "Routes",
        "blurb": "Every URL this application answers, and what handles it.",
        "cmd": "route:list --no-ansi",
        "timeout": 90,
    },
    "schedule_list": {
        "label": "Scheduled work",
        "blurb": "What the scheduler is meant to run, and when it next will.",
        "cmd": "schedule:list --no-ansi",
        "timeout": 60,
    },
    "queue_failed": {
        "label": "Failed jobs",
        "blurb": "Work the queue tried and could not finish.",
        "cmd": "queue:failed --no-ansi",
        "timeout": 60,
    },
    "env": {
        "label": "Environment",
        "blurb": "Which environment this application thinks it is running in.",
        "cmd": "env --no-ansi",
        "timeout": 30,
    },
}

#: Anything that would change the site. A read whose command contains one of these is a
#: write wearing a read's label, and the test that checks for them is what keeps this map
#: honest as it grows.
_MUTATING = (
    "migrate ", "migrate:fresh", "migrate:refresh", "migrate:reset", "migrate:rollback",
    "db:seed", "db:wipe", "cache:clear", "config:cache", "config:clear", "optimize",
    "route:cache", "route:clear", "view:cache", "view:clear", "event:cache",
    "queue:retry", "queue:flush", "queue:forget", "queue:restart", "queue:work",
    "schedule:run", "storage:link", "down", "up", "key:generate", "tinker",
    ">", ">>", "rm ", "mv ", "chmod", "chown",
)

#: Long output is trimmed rather than streamed. A site with 900 routes would otherwise put
#: a megabyte through the websocket to answer "what URLs does this have".
_MAX_OUTPUT = 60_000


def build_read_command(read: str, doc_root: str) -> str:
    """One named artisan command. The caller picks a key, never a command."""
    spec = READS.get(read)
    if spec is None:
        raise LaravelError(
            f"'{read}' is not something we can show. Choose one of: "
            + ", ".join(READS) + ".")
    return _prelude(doc_root) + f"_t {spec['timeout']} $ART {spec['cmd']}\n"


async def read_one(server: Server, doc_root: str, which: str) -> dict:
    """Run one read and hand back what artisan said.

    The output is passed through the secret redactor before it leaves the server. `about`
    prints a configuration summary, and on a site whose config has been customised that can
    include more than driver names — the browser is not the place to find that out.
    """
    from app.services.secret_redact import redact_secrets

    spec = READS.get(which)
    if spec is None:
        raise LaravelError(f"'{which}' is not something we can show.")
    try:
        stdout, stderr, code = await connection_manager.execute(
            server, build_read_command(which, doc_root))
    except Exception as exc:  # noqa: BLE001
        raise LaravelError(f"We could not reach the server: {exc}") from exc

    output = (stdout or "") + (("\n" + stderr) if stderr else "")
    for marker, message in _ERRORS.items():
        if marker in output:
            return {"ok": False, "label": spec["label"], "reason": message, "output": ""}

    text, hidden = redact_secrets(output.strip())
    trimmed = len(text) > _MAX_OUTPUT
    if trimmed:
        text = text[:_MAX_OUTPUT] + "\n… trimmed. Ask Ally if you need the rest."
    return {
        "ok": code == 0,
        "label": spec["label"],
        "output": text,
        "hidden": hidden,
        "trimmed": trimmed,
        # A non-zero exit is worth showing rather than hiding: `queue:failed` on a site with
        # no failed-jobs table fails, and the reason artisan gives is the useful part.
        "reason": None if code == 0 else "artisan could not complete this — see below.",
    }
