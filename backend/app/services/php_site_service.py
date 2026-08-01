"""What PHP this site actually runs under.

The registry's third entry, and the smallest — deliberately. A plain PHP site has no
framework to administer, so most of what it needs is already covered by its own Files, Logs
and HTTPS sections. What is NOT covered anywhere else is the handful of limits that decide
whether the site works, because they are set **per pool**:

- ``upload_max_filesize`` and ``post_max_size`` — the real answer to "my upload fails"
- ``memory_limit`` — the real answer to "allowed memory size exhausted"
- ``max_execution_time`` — the real answer to "the page just stops halfway"

The server's PHP page reports the server's default. A site running under its own FPM pool
can have entirely different values, and the difference is exactly the case somebody is
looking at this screen to explain. So these are read for THIS site, from the pool that
serves it, rather than from the command line — ``php -i`` at a shell reports the CLI's
settings, which are almost always more generous than the web ones and would tell a
comforting lie.

Read-only throughout: there is no action here. Changing a pool limit edits a file shared by
every site on that pool, which belongs to the server's PHP screen, not to one site's page.
"""
from __future__ import annotations

import logging
import shlex

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

_S = "___SM_PHPSITE___"

#: The settings worth showing. Anything else is noise on a page a non-technical owner opens
#: because something is broken.
SETTINGS = (
    ("upload_max_filesize", "Largest file that can be uploaded"),
    ("post_max_size", "Largest form submission"),
    ("memory_limit", "Memory one page may use"),
    ("max_execution_time", "Longest a page may run"),
    ("max_input_vars", "Most form fields accepted"),
    ("display_errors", "Errors shown to visitors"),
)


def build_probe_command(doc_root: str) -> str:
    """One read-only round trip, run THROUGH the site rather than at a shell.

    A temporary PHP file in the site's own document root is executed by its own FPM pool, so
    the values it reports are the ones a visitor's request actually gets. It is written with
    a random name, fetched over the loopback, and removed in a ``trap`` so it goes away even
    if the fetch fails — a stray file in a customer's web root is not acceptable, and one
    that reports configuration would be a gift to anybody scanning.
    """
    root = shlex.quote(doc_root or "")
    return f"""
_t() {{ local n=$1; shift; if command -v timeout >/dev/null 2>&1; then timeout "$n" "$@"; else "$@"; fi; }}

ROOT={root}
if [ ! -d "$ROOT" ]; then echo "{_S}|error|noroot"; exit 0; fi

NAME=".serverally-php-$(head -c 8 /dev/urandom | od -An -tx1 | tr -d ' \\n').php"
PROBE="$ROOT/$NAME"
# Removed however this exits — a forgotten file that reports a server's PHP configuration is
# exactly what someone scanning for weaknesses is looking for.
trap 'rm -f "$PROBE"' EXIT INT TERM

cat > "$PROBE" <<'PHPEOF'
<?php
$keys = [{", ".join(f"'{k}'" for k, _ in SETTINGS)}];
$out = ['version' => PHP_VERSION, 'sapi' => PHP_SAPI, 'settings' => [], 'extensions' => []];
foreach ($keys as $k) {{ $out['settings'][$k] = (string) ini_get($k); }}
$out['extensions'] = get_loaded_extensions();
echo json_encode($out);
PHPEOF
chown --reference="$ROOT" "$PROBE" 2>/dev/null || true
chmod 644 "$PROBE"

# Over the loopback with the site's own Host header, so the right vhost — and therefore the
# right pool — answers, without depending on the domain's DNS resolving anywhere yet.
BODY=$(_t 15 curl -s --max-time 12 -H "Host: $SM_DOMAIN" "http://127.0.0.1/$NAME" 2>/dev/null)
echo "{_S}|web|$(printf '%s' "$BODY" | tr -d '\\n')"

# The command line's PHP as well, because when the two differ that is itself the answer to
# "it works when I run it by hand".
echo "{_S}|cli|$(_t 10 php -r 'echo PHP_VERSION;' 2>/dev/null)"
rm -f "$PROBE"
trap - EXIT
true
"""


def parse_probe(stdout: str) -> dict:
    """Turn probe output into what the screen shows. Pure."""
    import json

    fields: dict[str, str] = {}
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith(_S):
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            fields[parts[1]] = parts[2].strip()

    if "error" in fields:
        return {"ok": False,
                "reason": "This site's folder is not on the server, so its PHP settings "
                          "cannot be read."}

    raw = fields.get("web", "")
    data: dict = {}
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except ValueError:
            data = {}

    if not data.get("version"):
        # The site did not answer, so nothing here is known. Showing the command line's
        # values instead would be the comforting lie this module exists to avoid.
        return {"ok": False,
                "reason": "The site did not answer, so its PHP settings could not be read. "
                          "Check the site loads, then try again."}

    settings = data.get("settings") or {}
    return {
        "ok": True,
        "version": str(data.get("version", "")),
        "sapi": str(data.get("sapi", "")),
        "cli_version": fields.get("cli", ""),
        "settings": [
            {"name": key, "label": label, "value": str(settings.get(key, "") or "—")}
            for key, label in SETTINGS
        ],
        "extensions": sorted(str(e) for e in (data.get("extensions") or [])),
    }


async def read(server: Server, doc_root: str, domain: str) -> dict:
    """This site's effective PHP. Never raises."""
    command = f"SM_DOMAIN={shlex.quote(domain)}\n" + build_probe_command(doc_root)
    try:
        stdout, _stderr, _code = await connection_manager.execute(server, command)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PHP probe failed on %s: %s", server.host, exc)
        return {"ok": False, "reason": "We could not reach the server to look."}
    return parse_probe(stdout)
