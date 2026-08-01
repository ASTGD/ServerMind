"""Operating a WordPress site: what it runs, what is out of date, who can sign in.

The first entry in ``app_registry``. Everything here goes through **wp-cli**, which is the
tool WordPress itself is administered with — reimplementing any of it by editing the database
or unpacking zips would be a second, worse copy of wp-cli that breaks on the next release.

Two things carry this module.

**Who runs the command decides whether the site survives it.** wp-cli run as root writes
root-owned files into ``wp-content``; WordPress then runs as the web-server user and can no
longer write there, so uploads stop working and the next update fails from inside the admin.
The damage arrives later than the command, which is what makes it easy to ship. So every
call runs as the OWNER of the WordPress folder, read off the server rather than assumed, and
``--allow-root`` is the last resort for a site genuinely owned by root.

**Reading is one bounded round trip and changes nothing.** The probe follows the same shape
as the metrics, security, threat and log probes: a fixed bundle authored here, never built
from customer input, sentinel-split, each call bounded, and asserted read-only by a test.
Actions are separate, explicit, and each one is a single named operation.
"""
from __future__ import annotations

import json
import logging
import shlex

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

_S = "___SM_WP___"

#: wp-cli talks to wordpress.org for update checks, so a slow network must not hang a page.
_T = 25
_T_NET = 20


class WordPressError(Exception):
    """Something the customer can read and act on."""


def _wp_prelude(doc_root: str) -> str:
    """Shell that locates the WordPress install and decides who wp-cli runs as.

    The ownership choice is the whole point. Getting it wrong does not fail — it succeeds
    and leaves the site unable to write to its own uploads folder, days later.
    """
    root = shlex.quote(doc_root or "")
    return f"""
_t() {{ local n=$1; shift; if command -v timeout >/dev/null 2>&1; then timeout "$n" "$@"; else "$@"; fi; }}

# The document root usually IS the WordPress root, but a site served from public/ keeps
# wp-load.php a level up. Look, rather than assume.
WP_PATH=""
for d in {root} {root}/.. ; do
  if [ -f "$d/wp-load.php" ]; then WP_PATH=$(cd "$d" && pwd); break; fi
done
if [ -z "$WP_PATH" ]; then echo "{_S}|error|nowp"; exit 0; fi
echo "{_S}|path|$WP_PATH"

# Resolved to an ABSOLUTE path, because the command below may run through sudo — and sudo
# replaces PATH with its own secure_path. Looking wp up as ourselves and then running it as
# somebody else is how a check passes and the command that follows it fails.
WP_BIN=$(command -v wp 2>/dev/null || true)
if [ -z "$WP_BIN" ]; then echo "{_S}|error|nocli"; exit 0; fi

# Run as whoever owns the files. wp-cli run as root writes root-owned files into
# wp-content, and WordPress — running as the web-server user — can then no longer write
# there: uploads stop working and the next update fails from inside the admin. The damage
# shows up days after the command that caused it.
ME=$(id -un)
OWNER=$(stat -c%U "$WP_PATH" 2>/dev/null || echo "")
[ -z "$OWNER" ] && OWNER="$ME"
echo "{_S}|owner|$OWNER"

RUNAS=""
if [ "$OWNER" != "$ME" ]; then
  # -n so a server without passwordless sudo fails immediately rather than waiting for a
  # password nobody is there to type.
  if ! sudo -n -u "$OWNER" true 2>/dev/null; then echo "{_S}|error|nosudo"; exit 0; fi
  RUNAS="sudo -n -u $OWNER --"
fi
# wp-cli REFUSES to run as root without this, so a root-owned site needs it — and only a
# root-owned site, since the flag is exactly the thing that makes the damage above possible.
ROOTFLAG=""
[ "$OWNER" = root ] && ROOTFLAG="--allow-root"
# --path is not optional. wp-cli finds an install by walking UP from the working directory,
# and the working directory here is the SSH login's home — so without it every command
# answers "This does not seem to be a WordPress installation", which the redirect below then
# turns into silence and the screen renders as a site with no plugins and no version.
WP="$RUNAS $WP_BIN --path=$WP_PATH $ROOTFLAG"
"""


def build_probe_command(doc_root: str) -> str:
    """One read-only round trip: version, updates, plugins, themes, administrators.

    ``--skip-plugins --skip-themes`` is not a shortcut — a single fatal error in one plugin
    takes wp-cli down with it, and then a site with one broken plugin reports nothing at all
    rather than reporting the broken plugin.
    """
    common = "--skip-plugins --skip-themes"
    return _wp_prelude(doc_root) + f"""
echo "{_S}|cli|$(_t 10 $WP --version {common} 2>/dev/null | head -1)"
echo "{_S}|core|$(_t {_T} $WP core version {common} 2>/dev/null)"
echo "{_S}|title|$(_t {_T} $WP option get blogname {common} 2>/dev/null)"
echo "{_S}|siteurl|$(_t {_T} $WP option get siteurl {common} 2>/dev/null)"

# Local reads: WordPress's own stored update information, so no network is involved.
echo "{_S}|plugins|$(_t {_T} $WP plugin list --format=json \\
  --fields=name,title,status,version,update,update_version {common} 2>/dev/null | tr -d '\\n')"
echo "{_S}|themes|$(_t {_T} $WP theme list --format=json \\
  --fields=name,status,version,update,update_version {common} 2>/dev/null | tr -d '\\n')"
echo "{_S}|admins|$(_t {_T} $WP user list --role=administrator --format=json \\
  --fields=ID,user_login,user_email,display_name {common} 2>/dev/null | tr -d '\\n')"

# This one DOES reach wordpress.org, so it is bounded harder and its absence simply means
# we do not claim an update exists.
echo "{_S}|coreupdate|$(_t {_T_NET} $WP core check-update --format=json {common} 2>/dev/null | tr -d '\\n')"

[ -f "$WP_PATH/.maintenance" ] && echo "{_S}|maintenance|yes" || echo "{_S}|maintenance|no"
echo "{_S}|debug|$(_t 10 $WP config get WP_DEBUG {common} 2>/dev/null)"
true
"""


_ERRORS = {
    "nowp": "This site does not look like a WordPress install — no wp-load.php in its folder.",
    "nocli": "wp-cli is not installed on this server, so WordPress cannot be managed from "
             "here. Ask Ally to install it.",
    "nosudo": "We could not run commands as the account that owns this site's files. "
               "Running them as root instead would leave files WordPress itself cannot "
               "write to, so nothing was run.",
}


def _rows(raw: str) -> list[dict]:
    """wp-cli JSON, or an empty list. Never raises — a broken site must still render."""
    raw = (raw or "").strip()
    if not raw or not raw.startswith("["):
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    return [r for r in data if isinstance(r, dict)]


def parse_probe(stdout: str) -> dict:
    """Turn probe output into what the screen shows. Pure, so every shape is testable."""
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
                                                   "WordPress could not be read here.")}

    # Every wp-cli call has its stderr redirected so an error message cannot corrupt the JSON
    # it is capturing. That makes a failure SILENT, and silence renders identically to a real
    # site with nothing on it — no version, no plugins, no administrators. So the version is
    # treated as the proof that wp-cli could actually read this install: without it, say so.
    if not fields.get("core"):
        return {"ok": False,
                "reason": "WordPress is here, but its own tooling could not read it. The "
                          "files may belong to a different account, or the install may be "
                          "damaged."}

    plugins = [{
        "name": p.get("name", ""),
        "title": p.get("title") or p.get("name", ""),
        "status": p.get("status", ""),
        "version": p.get("version", ""),
        # wp-cli reports the string "available"; anything else means up to date.
        "update_available": p.get("update") == "available",
        "update_version": p.get("update_version") or "",
    } for p in _rows(fields.get("plugins", ""))]

    themes = [{
        "name": t.get("name", ""),
        "status": t.get("status", ""),
        "version": t.get("version", ""),
        "update_available": t.get("update") == "available",
        "update_version": t.get("update_version") or "",
    } for t in _rows(fields.get("themes", ""))]

    admins = [{
        "id": str(u.get("ID", "")),
        "login": u.get("user_login", ""),
        "email": u.get("user_email", ""),
        "name": u.get("display_name", ""),
    } for u in _rows(fields.get("admins", ""))]

    # `core check-update` prints an empty list when up to date, and says nothing at all when
    # it could not reach wordpress.org. Those are different, and only the first one is news.
    core_updates = _rows(fields.get("coreupdate", ""))
    checked = fields.get("coreupdate", "").strip().startswith("[")

    return {
        "ok": True,
        "path": fields.get("path", ""),
        "runs_as": fields.get("owner", ""),
        "cli": fields.get("cli", ""),
        "core_version": fields.get("core", ""),
        "core_update": (core_updates[0].get("version") or "") if core_updates else "",
        "core_update_known": checked,
        "title": fields.get("title", ""),
        "site_url": fields.get("siteurl", ""),
        "plugins": plugins,
        "themes": themes,
        "admins": admins,
        "maintenance": fields.get("maintenance") == "yes",
        # wp-cli prints the literal `1`/`true` for an enabled constant.
        "debug": fields.get("debug", "").lower() in ("1", "true"),
        "updates_waiting": sum(1 for p in plugins if p["update_available"])
                           + sum(1 for t in themes if t["update_available"])
                           + (1 if core_updates else 0),
    }


async def read(server: Server, doc_root: str) -> dict:
    """Everything the WordPress section shows. Never raises."""
    try:
        stdout, _stderr, _code = await connection_manager.execute(
            server, build_probe_command(doc_root))
    except Exception as exc:  # noqa: BLE001
        logger.warning("WordPress probe failed on %s: %s", server.host, exc)
        return {"ok": False, "reason": "We could not reach the server to look."}
    return parse_probe(stdout)


# --- Actions ------------------------------------------------------------------------------
#
# Each is ONE named operation, never a command the caller composes. The name of a plugin or
# theme reaches the shell, so it is validated against what wp-cli itself allows rather than
# escaped — a slug is a small, well-defined shape and refusing anything else is simpler to be
# sure of than quoting.

#: WordPress slugs are lowercase letters, digits and hyphens. Nothing else is a valid
#: plugin or theme directory name, so nothing else needs to reach a command line.
def valid_slug(name: str) -> bool:
    value = (name or "").strip()
    if not value or len(value) > 100:
        return False
    return all(c.islower() or c.isdigit() or c in "-_." for c in value) and ".." not in value


ACTIONS = {
    "update_plugin": "update {target}",
    "update_theme": "update {target}",
    "activate_plugin": "activate {target}",
    "deactivate_plugin": "deactivate {target}",
    "update_core": "update core",
    "maintenance_on": "maintenance on",
    "maintenance_off": "maintenance off",
    "flush_cache": "flush the cache",
}


def build_action_command(action: str, doc_root: str, target: str = "") -> str:
    """The shell for one named action. Raises rather than composing something unexpected."""
    if action not in ACTIONS:
        raise WordPressError(f"'{action}' is not something we can do to a WordPress site.")
    if action in ("update_plugin", "update_theme", "activate_plugin", "deactivate_plugin"):
        if not valid_slug(target):
            raise WordPressError(
                f"'{target}' is not a valid WordPress plugin or theme name.")

    common = "--skip-plugins --skip-themes"
    body = {
        "update_plugin": f'_t 180 $WP plugin update {target} {common}',
        "update_theme": f'_t 180 $WP theme update {target} {common}',
        "activate_plugin": f'_t 60 $WP plugin activate {target} {common}',
        "deactivate_plugin": f'_t 60 $WP plugin deactivate {target} {common}',
        "update_core": f'_t 300 $WP core update {common} && _t 120 $WP core update-db {common}',
        # Written directly rather than through wp-cli: `wp maintenance-mode` needs the
        # plugins loaded, which is exactly what is broken when someone reaches for it.
        "maintenance_on": 'printf \'<?php $upgrading = time(); ?>\' > "$WP_PATH/.maintenance"'
                          ' && chown "$OWNER" "$WP_PATH/.maintenance" 2>/dev/null; '
                          'echo "Maintenance mode is on."',
        "maintenance_off": 'rm -f "$WP_PATH/.maintenance" && echo "Maintenance mode is off."',
        "flush_cache": f'_t 60 $WP cache flush {common}',
    }[action]
    return _wp_prelude(doc_root) + body + "\n"


async def act(server: Server, doc_root: str, action: str, target: str = "") -> dict:
    """Run one action and report honestly what happened.

    A non-zero exit is reported with wp-cli's own message: it names the actual problem — a
    plugin that does not exist, a failed download, no write permission — far better than
    anything written here could.
    """
    command = build_action_command(action, doc_root, target)
    try:
        stdout, stderr, code = await connection_manager.execute(server, command)
    except Exception as exc:  # noqa: BLE001
        raise WordPressError(f"We could not reach the server: {exc}") from exc

    output = (stdout or "") + (("\n" + stderr) if stderr else "")
    for marker, message in _ERRORS.items():
        if f"{_S}|error|{marker}" in output:
            raise WordPressError(message)
    if code != 0:
        tail = "\n".join(l for l in output.splitlines() if not l.startswith(_S))[-600:]
        raise WordPressError(tail.strip() or "WordPress reported a failure.")
    return {"output": "\n".join(
        l for l in output.splitlines() if not l.startswith(_S)).strip()}
