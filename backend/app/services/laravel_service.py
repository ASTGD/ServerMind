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
PHP_BIN=$(command -v php 2>/dev/null || true)
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
echo "{_S}|version|$(_t {_T} $ART --version 2>/dev/null | head -1)"

# `about` answers from the BOOTED application, which is the only authority once the config
# has been cached: after `artisan config:cache`, Laravel stops reading .env entirely, so a
# .env saying APP_DEBUG=false can sit above a live site that is running with debug ON.
# Reading the file would report the reassuring value and be wrong exactly when it matters.
echo "{_S}|about|$(_t {_T} $ART about --json --no-ansi 2>/dev/null | tr -d '\\n')"

# Fallback for Laravel 8 and older, which has no `about`. Only these two lines are read out
# of .env, never the file — it also holds the database password, and this screen has no
# business carrying one (the same rule the discovery probe follows about wp-config.php).
echo "{_S}|env|$(grep -m1 '^APP_ENV=' "$APP_PATH/.env" 2>/dev/null | cut -d= -f2- | tr -d '\\"'\\''' )"
echo "{_S}|debug|$(grep -m1 '^APP_DEBUG=' "$APP_PATH/.env" 2>/dev/null | cut -d= -f2- | tr -d '\\"'\\''' )"

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
pgrep -f "artisan queue:(work|listen)" >/dev/null 2>&1 \\
  && echo "{_S}|queue|yes" || echo "{_S}|queue|no"
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

    ``about`` groups these under a "cache" section whose values are ``CACHED`` /
    ``NOT CACHED`` — note that the flattened lookup would collide with other keys, so the
    section is read directly.
    """
    section = about.get("__section__cache")
    if isinstance(section, dict) and what in {str(k).lower() for k in section}:
        value = next(v for k, v in section.items() if str(k).lower() == what)
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

ACTIONS: dict[str, str] = {
    "optimize": "cache the configuration, routes and views",
    "clear": "clear every cache",
    "migrate": "run the database migrations that are waiting",
    "down": "put the site into maintenance mode",
    "up": "take the site out of maintenance mode",
    "storage_link": "link the uploads folder so uploaded files can be served",
    "queue_restart": "restart the queue workers so they pick up the new code",
}

#: `migrate` is the only one here that can lose data — a migration may drop a column. It is
#: offered, because a deploy is not finished without it, but it is named as what it is and
#: the screen only offers it when something is actually waiting.
DESTRUCTIVE = {"migrate"}


def build_action_command(action: str, doc_root: str) -> str:
    if action not in ACTIONS:
        raise LaravelError(f"'{action}' is not something we can do to a Laravel site.")
    body = {
        # --force because artisan refuses to run migrations unattended in production
        # otherwise, and there is nobody at a terminal to confirm.
        "migrate": f"_t 300 $ART migrate --force --no-ansi",
        "optimize": f"_t 120 $ART optimize --no-ansi",
        "clear": f"_t 120 $ART optimize:clear --no-ansi",
        "down": f"_t 60 $ART down --no-ansi",
        "up": f"_t 60 $ART up --no-ansi",
        "storage_link": f"_t 60 $ART storage:link --no-ansi",
        "queue_restart": f"_t 60 $ART queue:restart --no-ansi",
    }[action]
    return _prelude(doc_root) + body + "\n"


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
