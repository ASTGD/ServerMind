"""The database THIS site uses, and whether it can actually reach it.

The server already has a database screen. It answers "what is on this machine", which on a
box with forty databases is the wrong question — nobody can tell which of them belongs to
the website that is currently broken.

**How we know which one is the site's: we ask the site.** Its own configuration names the
database it connects to, and that is the only authority — a name that merely resembles the
domain is a guess, and the guess is wrong exactly on the servers where it matters, because
those are the ones somebody else set up.

Two rules make reading that configuration acceptable:

- **Only the name, the user and the host are ever extracted.** The password is in the same
  file and is never read into anything we keep, log, transmit or return. The site inventory
  follows the same rule about ``wp-config.php``.
- **The connection test happens ON THE SERVER.** The password is read into a shell variable
  there, passed to the client through ``MYSQL_PWD`` so it never reaches the process list,
  and what comes back is one word. It never crosses the network, never reaches a database
  of ours, and never reaches a browser.

That test is the point of the whole screen. "The site is down" is very often "the site
cannot reach its database" — a wrong password after a migration, a database that was
dropped, a MySQL that is not running — and there is otherwise no way to tell that apart
from an application bug without opening a terminal.
"""
from __future__ import annotations

import logging
import shlex

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

_S = "___SM_SITEDB___"


def build_probe_command(app_type: str, doc_root: str) -> str:
    """Read which database this site uses, then prove whether it can reach it.

    Read-only in both senses: it reads configuration and runs one SELECT. A test asserts
    no statement here can change anything.
    """
    root = shlex.quote(doc_root or "")
    app = (app_type or "").lower()
    return f"""
_t() {{ local n=$1; shift; if command -v timeout >/dev/null 2>&1; then timeout "$n" "$@"; else "$@"; fi; }}

# The application root, which for a framework serving from public/ is a level up.
APP=""
for d in {root} {root}/.. ; do
  if [ -f "$d/wp-config.php" ] || [ -f "$d/.env" ]; then APP=$(cd "$d" && pwd); break; fi
done
if [ -z "$APP" ]; then echo "{_S}|error|noconfig"; exit 0; fi

DB_NAME=""; DB_USER=""; DB_HOST=""; DB_PASS=""; KIND=""

# WordPress keeps them as PHP defines. Matched one constant at a time so nothing else in
# the file can be picked up by accident.
if [ -f "$APP/wp-config.php" ]; then
  KIND=wordpress
  _wpdef() {{ grep -oE "define\\(\\s*['\\\"]$1['\\\"]\\s*,\\s*['\\\"][^'\\\"]*['\\\"]" \\
    "$APP/wp-config.php" 2>/dev/null | head -1 | sed -E "s/.*,\\s*['\\\"]([^'\\\"]*)['\\\"].*/\\1/"; }}
  DB_NAME=$(_wpdef DB_NAME); DB_USER=$(_wpdef DB_USER)
  DB_HOST=$(_wpdef DB_HOST); DB_PASS=$(_wpdef DB_PASSWORD)
fi

# Laravel and most other frameworks use a .env. Values can carry a trailing comment, which
# is stripped — the same lesson a real .env taught the Laravel screen.
if [ -z "$DB_NAME" ] && [ -f "$APP/.env" ]; then
  KIND=env
  _envval() {{ grep -m1 "^$1=" "$APP/.env" 2>/dev/null | cut -d= -f2- \\
    | sed -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \\
    | tr -d '"'\\'''; }}
  DB_NAME=$(_envval DB_DATABASE); DB_USER=$(_envval DB_USERNAME)
  DB_HOST=$(_envval DB_HOST); DB_PASS=$(_envval DB_PASSWORD)
  ENGINE=$(_envval DB_CONNECTION)
fi

if [ -z "$DB_NAME" ]; then echo "{_S}|error|nodb"; exit 0; fi

# The name, the user and the host. The password is deliberately not among them and is used
# only in the connection attempt below.
echo "{_S}|name|$DB_NAME"
echo "{_S}|user|$DB_USER"
echo "{_S}|host|${{DB_HOST:-localhost}}"
echo "{_S}|kind|$KIND"

# MariaDB 11 renamed its client to `mariadb` and no longer always ships a `mysql`
# symlink, so looking only for the old name reported "could not test" on every modern
# MariaDB server. Found by running this against a real one.
CLIENT=""
for c in mysql mariadb; do
  if command -v "$c" >/dev/null 2>&1; then CLIENT="$c"; break; fi
done
if [ -z "$CLIENT" ]; then echo "{_S}|reach|noclient"; exit 0; fi

# --no-defaults is not optional. The client reads option files before anything we pass,
# and a server set up by a control panel has /root/.my.cnf with the ADMINISTRATOR's
# credentials in it — which silently replace the site's and get refused. The result was a
# red "this site cannot reach its database" on a site that was perfectly healthy, which is
# the worst thing this screen could do: a false alarm here teaches somebody to ignore the
# real one. Found on a real CyberPanel server.
#
# Through MYSQL_PWD, so the password is never in the process list — the same rule the
# backup service follows. Everything the client might print is discarded: one word comes
# back, and nothing that could carry a credential with it.
HOSTARG=""
case "${{DB_HOST:-localhost}}" in
  localhost|"") : ;;
  *:*) HOSTARG="-h ${{DB_HOST%%:*}} -P ${{DB_HOST##*:}}" ;;
  *) HOSTARG="-h ${{DB_HOST}}" ;;
esac
if MYSQL_PWD="$DB_PASS" _t 15 "$CLIENT" --no-defaults -u "$DB_USER" $HOSTARG \\
     -N -B -e "SELECT 1" "$DB_NAME" >/dev/null 2>&1; then
  echo "{_S}|reach|yes"
  # Asked with the SITE's own access rather than an administrator's, so this reports what
  # the application can actually see.
  SUM=$(MYSQL_PWD="$DB_PASS" _t 20 "$CLIENT" --no-defaults -u "$DB_USER" $HOSTARG -N -B -e \\
    "SELECT COUNT(*), COALESCE(ROUND(SUM(data_length+index_length)/1048576,1),0) \\
     FROM information_schema.tables WHERE table_schema='$DB_NAME'" 2>/dev/null)
  echo "{_S}|tables|$(printf '%s' "$SUM" | awk '{{print $1}}')"
  echo "{_S}|size_mb|$(printf '%s' "$SUM" | awk '{{print $2}}')"
else
  echo "{_S}|reach|no"
fi
true
"""


_ERRORS = {
    "noconfig": "This site has no application configuration we recognise, so we cannot "
                "tell which database it uses.",
    "nodb": "This site's configuration does not name a database — it most likely does not "
            "use one.",
}


def parse_probe(stdout: str) -> dict:
    """Turn probe output into what the screen shows. Pure, and never carries a password —
    there is nothing in the probe's output that could contain one."""
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
                                                   "We could not read this site's database "
                                                   "settings.")}

    reach = fields.get("reach", "")
    def _num(key):
        try:
            return float(fields[key]) if key in fields and fields[key] else None
        except ValueError:
            return None

    return {
        "ok": True,
        "name": fields.get("name", ""),
        "user": fields.get("user", ""),
        "host": fields.get("host", "localhost"),
        # yes / no / noclient — three genuinely different states, and only the first is
        # good news. "noclient" means we could not test, which is not the same as failing.
        "reachable": reach == "yes",
        "tested": reach in ("yes", "no"),
        "tables": int(_num("tables")) if _num("tables") is not None else None,
        "size_mb": _num("size_mb"),
    }


async def read(server: Server, app_type: str, doc_root: str) -> dict:
    """This site's database. Never raises."""
    try:
        stdout, _stderr, _code = await connection_manager.execute(
            server, build_probe_command(app_type, doc_root))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Site database probe failed on %s: %s", server.host, exc)
        return {"ok": False, "reason": "We could not reach the server to look."}
    return parse_probe(stdout)
