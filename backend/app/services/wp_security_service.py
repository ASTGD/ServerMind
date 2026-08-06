"""Two WordPress security switches — debug logging, and blocking XML-RPC.

Both are things a WordPress owner is told to do and almost never does, because both mean
editing a file they are frightened of.

**The debug switch has a trap that Ploi's own description does not mention.** Setting
`WP_DEBUG` to true is not enough and is actively dangerous on its own: with `WP_DEBUG_DISPLAY`
left at its default, PHP errors are printed INTO THE PAGE — file paths, plugin internals,
sometimes fragments of queries — for every visitor, on a live site. So turning debugging on
here always sets three constants together, and the one that stops the leak is not optional.

**And the log itself must not be downloadable.** WordPress's default is
`wp-content/debug.log`, which sits inside the folder the web server serves and has a name
every scanner already knows. This writes it outside the web root instead, and **refuses to
turn debugging on at all if it cannot find a safe place** — a debug log that anyone can
fetch is worse than no debug log, and the promise on the screen would be a lie.

XML-RPC is blocked at the WEB SERVER rather than inside WordPress, because the attack it is
blocking — thousands of login attempts amplified through `system.multicall`, and pingback
floods — is one you want stopped before PHP starts, not after. Blocking it inside WordPress
still boots the whole application for every request.
"""
from __future__ import annotations

import posixpath
import shlex

from app.services import app_registry

_S = "___SM_WPSEC___"

#: Where the debug log goes, beside the site rather than inside it.
LOG_DIR_NAME = "serverally-logs"
LOG_FILE_NAME = "wp-debug.log"

#: A parent folder shallower than this, or in this set, is shared with other sites or with
#: the operating system — the same rule the permissions repair follows, for the same reason.
_MIN_DEPTH = 3
_FORBIDDEN = {
    "/", "/etc", "/usr", "/var", "/var/www", "/var/lib", "/srv", "/opt", "/home", "/root",
    "/bin", "/sbin", "/boot", "/tmp",
}

BEGIN = "# --- ServerAlly XML-RPC block (managed) ---"
END = "# --- end ServerAlly XML-RPC block ---"

#: What blocking XML-RPC actually costs. Said on the screen, because these are real tools
#: people use and finding out by breaking one is a bad way to learn.
XMLRPC_BREAKS = (
    "the WordPress mobile app", "Jetpack", "pingbacks and trackbacks",
    "some remote publishing tools",
)


class WpSecurityError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def log_dir_for(wp_path: str) -> str:
    """Where this site's debug log can safely live, or a refusal.

    Beside the WordPress folder, never inside it. Refused rather than resolved when the
    parent turns out to be shared — on a server whose site is at `/var/www/html`, the parent
    is `/var/www`, and a debug log there would sit next to every other site on the machine.
    """
    raw = (wp_path or "").strip()
    # Checked BEFORE the trailing slash is stripped. "/" would otherwise become an empty
    # string and be refused as "we do not know where this site lives", which is not what is
    # wrong with it — the most dangerous input deserves the most accurate refusal. Exactly
    # the same trap the permissions repair hit.
    if raw == "/":
        raise WpSecurityError(
            "This site is at “/”, the whole server. There is nowhere beside it that is not "
            "shared with other sites, so debugging is not turned on.")
    root = raw.rstrip("/")
    if not root.startswith("/"):
        raise WpSecurityError("We do not know where this WordPress site lives.")
    parent = posixpath.dirname(root)
    parts = [p for p in parent.split("/") if p]
    if parent in _FORBIDDEN or len(parts) < _MIN_DEPTH - 1:
        raise WpSecurityError(
            f"This site is at {root}, so the only folder beside it is {parent} — which is "
            f"shared with other sites on this server. There is nowhere safe to keep a debug "
            f"log out of the web root, so debugging is not turned on. Moving the site into "
            f"its own folder fixes it."
        )
    return f"{parent}/{LOG_DIR_NAME}"


def log_path_for(wp_path: str) -> str:
    return f"{log_dir_for(wp_path)}/{LOG_FILE_NAME}"


def build_state_command(doc_root: str) -> str:
    """What the two switches are set to right now. Read-only."""
    return app_registry.owner_prelude(doc_root, marker="wp-load.php", sentinel=_S) + f"""
CFG="$APP_PATH/wp-config.php"
[ -f "$CFG" ] || {{ echo "{_S}|error|noconfig"; exit 0; }}
echo "{_S}|path|$APP_PATH"
# Read from the file rather than by booting WordPress: this has to work on a site that is
# too broken to load, which is exactly when somebody wants to turn debugging on.
for _c in WP_DEBUG WP_DEBUG_LOG WP_DEBUG_DISPLAY; do
  echo "{_S}|$_c|$(grep -m1 -E "^[[:space:]]*define\\([[:space:]]*['\\"]$_c['\\"]" "$CFG" 2>/dev/null \\
    | sed -E "s/.*,[[:space:]]*//; s/[[:space:]]*\\)[[:space:]]*;.*//; s/^['\\"]//; s/['\\"]$//")"
done
"""


def parse_state(stdout: str, config_block: str = "") -> dict:
    """The two switches, as the screen shows them."""
    fields: dict[str, str] = {}
    for line in (stdout or "").splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[0] == _S:
            fields[parts[1]] = parts[2]

    if fields.get("error"):
        reason = {
            "noapp": "This site does not look like a WordPress install.",
            "noconfig": "This site has no wp-config.php, so there is nothing to switch.",
            "nosudo": "We could not read this site's files as the account that owns them.",
        }.get(fields["error"], "We could not read this site's configuration.")
        return {"ok": False, "reason": reason}

    debug_on = (fields.get("WP_DEBUG") or "").strip().lower() == "true"
    display = (fields.get("WP_DEBUG_DISPLAY") or "").strip().lower()
    log_value = (fields.get("WP_DEBUG_LOG") or "").strip()

    return {
        "ok": True,
        "path": fields.get("path", ""),
        "debug": debug_on,
        "debug_log": log_value,
        # The dangerous combination, called out on its own because it is invisible from the
        # site itself until a visitor happens to trigger an error.
        "leaking_errors": debug_on and display != "false",
        # WordPress's own default lives under the web root and has a name every scanner
        # already knows.
        "log_in_web_root": bool(log_value) and log_value.lower() not in ("false", "true")
                           and LOG_DIR_NAME not in log_value,
        "xmlrpc_blocked": BEGIN in (config_block or ""),
    }


def build_debug_command(wp_path: str, doc_root: str, *, enable: bool) -> str:
    """Turn debug logging on or off, safely.

    Three constants move together on the way on, and the second one is the whole point:
    without it PHP errors are printed into the page for visitors. `wp config set` is used
    rather than editing the file by hand — wp-cli knows where a constant belongs in
    wp-config.php, and a hand-rolled edit that lands after the "stop editing" line is
    ignored while looking perfectly correct.
    """
    if enable:
        log = log_path_for(wp_path)          # raises before anything is touched
        d = shlex.quote(log_dir_for(wp_path))
        body = f"""
mkdir -p {d}
chown "$OWNER":"$OWNER" {d} 2>/dev/null || true
chmod 750 {d}
$WP config set WP_DEBUG true --raw --type=constant >/dev/null 2>&1 || FAILED=1
# NOT optional. Without it, WP_DEBUG=true prints PHP errors into the page — file paths,
# plugin internals, sometimes query fragments — for every visitor on a live site.
$WP config set WP_DEBUG_DISPLAY false --raw --type=constant >/dev/null 2>&1 || FAILED=1
$WP config set WP_DEBUG_LOG {shlex.quote(log)} --type=constant >/dev/null 2>&1 || FAILED=1
"""
    else:
        body = """
$WP config set WP_DEBUG false --raw --type=constant >/dev/null 2>&1 || FAILED=1
$WP config set WP_DEBUG_LOG false --raw --type=constant >/dev/null 2>&1 || FAILED=1
"""
    return app_registry.owner_prelude(doc_root, marker="wp-load.php", sentinel=_S) + f"""
WP_PATH="$APP_PATH"
WP_BIN=$(command -v wp 2>/dev/null || true)
if [ -z "$WP_BIN" ]; then echo "{_S}|error|nocli"; exit 0; fi
ROOTFLAG=""
[ "$OWNER" = root ] && ROOTFLAG="--allow-root"
WP="$RUNAS $WP_BIN --path=$WP_PATH $ROOTFLAG"
CFG="$WP_PATH/wp-config.php"
[ -f "$CFG" ] || {{ echo "{_S}|error|noconfig"; exit 0; }}
# Kept before anything is written. wp-config.php holds the database password, so it is
# never read out to us — but it is very much worth being able to put back.
BK="$CFG.serverally.$(date +%s).bak"
cp -p "$CFG" "$BK"
FAILED=""
{body}
if [ -n "$FAILED" ]; then cp -p "$BK" "$CFG"; rm -f "$BK"; echo "{_S}|error|writefailed"; exit 0; fi
# A wp-config.php that no longer parses takes the site down completely, so it is proved to
# still load before the backup is thrown away.
if ! $RUNAS php -l "$CFG" >/dev/null 2>&1; then
  cp -p "$BK" "$CFG"; rm -f "$BK"; echo "{_S}|error|broken"; exit 0
fi
rm -f "$BK"
echo "{_S}|ok|{'on' if enable else 'off'}"
"""


def build_xmlrpc_command(config_path: str, domain: str, *, block: bool,
                         apache: bool) -> str:
    """Block or unblock `xmlrpc.php` at the web server, and undo it if the site objects.

    Same discipline every config edit here follows, because the failure is the same: a
    config that does not parse takes down every site on the machine, not just this one.
    """
    cfg, dom = shlex.quote(config_path), shlex.quote(domain)
    if not block:
        rule = ""
    elif apache:
        rule = (f"{BEGIN}\n"
                f'    <Files "xmlrpc.php">\n'
                f"        Require all denied\n"
                f"    </Files>\n"
                f"{END}\n")
    else:
        # `location =` is an EXACT match, which outranks the regex `\.php$` location that
        # would otherwise hand the request to PHP. A prefix location would lose that race
        # and the block would do nothing while looking correct.
        rule = (f"{BEGIN}\n"
                f"    location = /xmlrpc.php {{\n"
                f"        deny all;\n"
                f"        access_log off;\n"
                f"        log_not_found off;\n"
                f"    }}\n"
                f"{END}\n")

    anchor = "ServerName" if apache else "server_name"
    awk = (
        'BEGIN { while ((getline l < B) > 0) blk[++n] = l } '
        '$0 == BEGINM { skip = 1 } '
        'skip { if ($0 == ENDM) skip = 0; next } '
        '{ print } '
        f'/^[ \\t]*({anchor})[ \\t]/ {{ for (i = 1; i <= n; i++) print blk[i] }}'
    )
    return (
        f'set -e; CFG={cfg}; DOM={dom}; '
        f'[ -f "$CFG" ] || {{ echo "This site\'s configuration file is not there."; exit 3; }}; '
        # Was the site working BEFORE we touched it? Without this, applying a change to a
        # site that is already down rolls straight back and tells the customer our edit
        # broke it — which is both wrong and leaves them unable to use these switches at
        # exactly the moment they are trying to fix something. Found when a test harness
        # had no PHP running and the feature dutifully blamed itself.
        f'WAS=no; if curl -s -o /dev/null --max-time 6 -H "Host: $DOM" '
        f'  -w "%{{http_code}}" http://127.0.0.1/ 2>/dev/null | grep -qE "^[23]"; '
        f'  then WAS=yes; fi; '
        f'BK="$CFG.serverally.$(date +%s).bak"; cp -p "$CFG" "$BK"; '
        f'BLKF="$CFG.serverally.block.tmp"; NEW="$CFG.serverally.new.tmp"; '
        f'printf %s {shlex.quote(rule)} > "$BLKF"; '
        f'awk -v B="$BLKF" -v BEGINM={shlex.quote(BEGIN)} -v ENDM={shlex.quote(END)} '
        f'  {shlex.quote(awk)} "$CFG" > "$NEW"; '
        f'cat "$NEW" > "$CFG"; rm -f "$NEW" "$BLKF"; '
        f'if ! (nginx -t 2>/dev/null || apachectl configtest 2>/dev/null); then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  echo "The web server refused it."; exit 4; fi; '
        # Falls back to the web server's OWN reload when systemd is not there.
        # Without it the change is written, never loaded, and reported as applied —
        # because the verify request then passes against the OLD config. Caught in a
        # container with no systemd, and equally true of a minimal install.
        f'systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null '
        f'  || systemctl reload httpd 2>/dev/null '
        f'  || nginx -s reload 2>/dev/null || apachectl graceful 2>/dev/null || true; '
        f'OK=no; B=/tmp/.sa_wpsec.$$; '
        f'for i in 1 2 3 4; do '
        f'  C="$(curl -s -o "$B" -w "%{{http_code}}" --max-time 6 -H "Host: $DOM" '
        f'      http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'  case "$C" in 3*) OK=yes ;; 2*) [ -s "$B" ] && OK=yes ;; esac; '
        f'  [ "$OK" = yes ] && break; sleep 2; done; rm -f "$B"; '
        # Only a site that WAS working can be said to have stopped. One that was
        # already down keeps the change — it is very likely part of fixing it — and
        # says so, rather than blaming this edit for an outage it did not cause.
        f'if [ "$OK" != yes ] && [ "$WAS" = yes ]; then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null '
        f'  || nginx -s reload 2>/dev/null || true; '
        f'  echo "The site stopped serving."; exit 5; fi; '
        f'if [ "$OK" != yes ]; then rm -f "$BK"; echo "applied-was-down"; exit 0; fi; '
        f'rm -f "$BK"; echo "applied"'
    )


_DEBUG_ERRORS = {
    "noapp": "This site does not look like a WordPress install.",
    "nocli": "wp-cli is not installed on this server, so WordPress settings cannot be "
             "changed from here.",
    "noconfig": "This site has no wp-config.php, so there is nothing to switch.",
    "nosudo": "We could not run commands as the account that owns this site's files.",
    "writefailed": "WordPress refused the change, so the previous settings were put back.",
    "broken": ("Those settings left wp-config.php unable to load, so the previous file was "
               "put back. Nothing is changed."),
}


def explain_debug(stdout: str, *, enable: bool) -> tuple[bool, str]:
    for line in (stdout or "").splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[0] == _S and parts[1] == "error":
            return False, _DEBUG_ERRORS.get(parts[2], "That could not be changed.")
    if f"{_S}|ok|" not in (stdout or ""):
        return False, "We could not tell whether that worked, so treat it as unchanged."
    if enable:
        return True, ("Debug logging is on. Errors go to a file beside the site, not into "
                      "the page — visitors will never see them, and the log cannot be "
                      "downloaded. Turn it off again once you have what you need.")
    return True, "Debug logging is off."


_XMLRPC_OUTCOMES = {
    3: "This site's configuration file could not be found, so nothing changed.",
    4: ("The web server refused it, so it was undone. Your site and every other site on "
        "this server are unaffected."),
    5: "The site stopped serving with that in place, so it was removed again.",
}


def explain_xmlrpc(code: int, output: str, *, block: bool) -> tuple[bool, str]:
    if code == 0 and "applied-was-down" in (output or ""):
        what = "blocked" if block else "allowed again"
        return True, (f"XML-RPC is {what}. Note that this site was already not serving "
                      f"before the change, so that is not something this did — but it also "
                      f"means we could not confirm the site still works.")
    if code == 0:
        if block:
            return True, ("XML-RPC is blocked. Requests are refused by the web server "
                          "before WordPress starts, so the load never reaches PHP.")
        return True, "XML-RPC is allowed again."
    if code in _XMLRPC_OUTCOMES:
        return False, _XMLRPC_OUTCOMES[code]
    tail = (output or "").strip().splitlines()
    return False, (tail[-1] if tail else "That could not be changed.")
