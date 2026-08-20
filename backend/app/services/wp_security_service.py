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
import re
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
for _c in WP_DEBUG WP_DEBUG_LOG WP_DEBUG_DISPLAY DISABLE_WP_CRON; do
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
        "xmlrpc_blocked": xmlrpc_is_blocked(config_block or ""),
        # True means WordPress has STOPPED running its scheduled work during visits, so
        # something else must be doing it. The screen pairs this with whether a real cron
        # job exists, because that combination is the only one that matters.
        "timer_disabled": (fields.get("DISABLE_WP_CRON") or "").strip().lower() == "true",
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



#: A deny of `/xmlrpc.php`, written by anyone. Our own WordPress installer writes one as a
#: single line outside these markers, so a check for the markers alone reported "not
#: blocked" on a site that WAS blocked — and then tried to add a second block, which nginx
#: refuses outright as a duplicate location. The question this screen asks is whether
#: xmlrpc is reachable, not whether we were the one who closed it.
_XMLRPC_DENIED = re.compile(
    r"location\s*=\s*/xmlrpc\.php\s*\{[^}]*\bdeny\s+all\b|"
    r"<Files\s+\"?xmlrpc\.php\"?>[^<]*(Require\s+all\s+denied|Deny\s+from\s+all)",
    re.IGNORECASE | re.DOTALL)


def xmlrpc_is_blocked(config: str) -> bool:
    """True when this site's configuration already refuses `xmlrpc.php`."""
    text = config or ""
    return BEGIN in text or bool(_XMLRPC_DENIED.search(text))


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


# --- WordPress's own timer ------------------------------------------------------------
#
# By default WordPress runs its scheduled work during a visitor's page load. On a quiet site
# that means scheduled posts publish late or not at all; on a busy one every visitor pays for
# it. The fix is a real system cron plus `DISABLE_WP_CRON`, and the cron half already exists
# on the site's Scheduled jobs screen — this is the constant that makes it worth having.
#
# **The ordering is the safety, and it runs both ways.** Turning WordPress's own timer off
# while no real cron is running stops scheduled work COMPLETELY and silently: no posts
# publish, no backups run, and nobody finds out until they notice something that never
# happened. That is strictly worse than the default we started from. So the constant is only
# ever set once a real job is in place, and on the way back the built-in timer is restored
# BEFORE the job is removed. There is no moment when neither is running.

#: What Ploi offers, in minutes. One minute is the default because WordPress schedules work
#: to the minute; the slower ones exist for a small box where every run costs something.
CRON_FREQUENCIES = (1, 2, 5, 10, 15)


def cron_schedule(minutes: int) -> str:
    """A crontab schedule for one of the offered frequencies."""
    if minutes not in CRON_FREQUENCIES:
        raise WpSecurityError(
            f"{minutes} minutes is not one of the choices. Pick "
            + ", ".join(f"{m}" for m in CRON_FREQUENCIES) + ".")
    return "* * * * *" if minutes == 1 else f"*/{minutes} * * * *"


def check_can_disable_timer(*, has_real_cron: bool) -> None:
    """Refuse to switch off WordPress's timer when nothing else is doing the work.

    Refused rather than warned about. A warning is something somebody clicks through once,
    and the cost here is silent: the site keeps serving perfectly while everything scheduled
    quietly stops.
    """
    if not has_real_cron:
        raise WpSecurityError(
            "Nothing else is running this site's scheduled work yet, so switching off "
            "WordPress's own timer would stop it completely — scheduled posts would not "
            "publish and nothing would say so. Add the scheduled job first, on this site's "
            "Scheduled jobs screen, then switch the timer off."
        )


def build_timer_command(doc_root: str, *, disable: bool) -> str:
    """Set or clear `DISABLE_WP_CRON`, with the same protection the other switches use."""
    value = "true" if disable else "false"
    body = f"""
$WP config set DISABLE_WP_CRON {value} --raw --type=constant >/dev/null 2>&1 || FAILED=1
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
BK="$CFG.serverally.$(date +%s).bak"
cp -p "$CFG" "$BK"
FAILED=""
{body}
if [ -n "$FAILED" ]; then cp -p "$BK" "$CFG"; rm -f "$BK"; echo "{_S}|error|writefailed"; exit 0; fi
if ! $RUNAS php -l "$CFG" >/dev/null 2>&1; then
  cp -p "$BK" "$CFG"; rm -f "$BK"; echo "{_S}|error|broken"; exit 0
fi
rm -f "$BK"
echo "{_S}|ok|{'off' if disable else 'on'}"
"""


def explain_timer(stdout: str, *, disable: bool) -> tuple[bool, str]:
    """What happened, in terms of what the customer actually gets."""
    text = stdout or ""
    for marker, message in (
        ("|error|nocli", "WP-CLI is not installed on this server, so this could not be "
                         "changed. Ask Ally to install it."),
        ("|error|noconfig", "This site's wp-config.php could not be found."),
        ("|error|writefailed", "The change could not be written, so nothing was altered."),
        ("|error|broken", "The change would have stopped WordPress loading, so it was put "
                          "back exactly as it was."),
    ):
        if marker in text:
            return False, message
    if f"{_S}|ok|" not in text:
        return False, "We could not tell whether that worked, so treat it as unchanged."
    if disable:
        return True, ("WordPress no longer runs its scheduled work during visits — your "
                      "scheduled job does it instead. Pages are quicker, and anything "
                      "scheduled now happens on time rather than when somebody happens "
                      "to visit.")
    return True, ("WordPress is running its own scheduled work again, during visits. You "
                  "can remove the scheduled job if you no longer want it.")


# --- Search and replace ---------------------------------------------------------------
#
# What you need when a site changes domain: every post, option and widget that mentions the
# old address has to mention the new one. It is also the most dangerous thing on this screen,
# because it rewrites the database in bulk and there is no undo.
#
# Three rules, and none of them is optional.
#
# **It goes through wp-cli, never SQL.** WordPress stores PHP-serialized arrays in the
# database with byte-LENGTH prefixes, so a plain `UPDATE ... REPLACE()` leaves every
# serialized value with a length that no longer matches its content. WordPress then silently
# discards those options — widgets vanish, theme settings reset — and nothing reports an
# error. wp-cli unserializes, replaces, and re-serializes.
#
# **`guid` is never touched.** It looks like a URL and is not one: it is a permanent
# identifier, and rewriting it makes every feed reader treat every existing post as brand
# new. Subscribers get the whole archive again.
#
# **Nothing runs until a dry run has been seen.** The customer is shown, per table, how many
# rows WOULD change — because "412,000 rows" and "3 rows" mean very different things and only
# they can tell which one is right.

#: Only tables belonging to this WordPress install. `--all-tables` would reach anything else
#: sharing the database, which on shared hosting is somebody else's site.
#: The colour flag is `--no-color`, NOT `--no-ansi` — that is artisan's flag, and wp-cli
#: refuses an unknown flag outright, so the command failed on every site until this was run
#: against a real wp-cli. The other three were checked against `wp help search-replace` at
#: the same time rather than one at a time.
_SR_FLAGS = "--skip-columns=guid --report-changed-only --precise --no-color"


def check_terms(search: str, replace: str) -> tuple[str, str]:
    """The two strings, or a refusal in words worth showing.

    Deliberately does NOT refuse a short search term. A dry run reports how many rows it
    would touch, and that number is a better guard than any rule about length: it is exact,
    and it is the customer who knows whether 400,000 rows is right.
    """
    s = (search or "").strip()
    r = (replace or "").strip()
    if not s:
        raise WpSecurityError(
            "Type what to search for. An empty search would match everywhere.")
    if s == r:
        raise WpSecurityError(
            "The two are the same, so this would change nothing. Check for a typo.")
    if "\n" in s or "\n" in r:
        raise WpSecurityError("A search or replacement cannot contain a line break.")
    return s, r


def build_search_replace_command(doc_root: str, search: str, replace: str, *,
                                 dry_run: bool) -> str:
    """Replace one string with another across this site's own tables.

    The two strings are user text that ends up in a command line, so they are quoted rather
    than trusted — and they are quoted as single ARGUMENTS, so a value containing `;` or `&&`
    is a value, never a second command.
    """
    s, r = check_terms(search, replace)
    dry = " --dry-run" if dry_run else ""
    return app_registry.owner_prelude(doc_root, marker="wp-load.php", sentinel=_S) + f"""
WP_BIN=$(command -v wp 2>/dev/null || true)
if [ -z "$WP_BIN" ]; then echo "{_S}|error|nocli"; exit 0; fi
ROOTFLAG=""
[ "$OWNER" = root ] && ROOTFLAG="--allow-root"
$RUNAS "$WP_BIN" --path="$APP_PATH" $ROOTFLAG search-replace \\
  {shlex.quote(s)} {shlex.quote(r)} {_SR_FLAGS}{dry} 2>&1
echo "{_S}|done|$?"
"""


def parse_search_replace(stdout: str) -> dict:
    """How much would change, and where.

    **The total comes from wp-cli's own summary line, not from my table parsing.** wp-cli
    only draws its ASCII table when it is talking to a terminal; over SSH there is none, so
    the rows arrive TAB-separated. My first version only understood pipes and therefore
    reported ZERO for a search that really matched seven things — which the screen would have
    shown as "nothing matched, probably a typo". Confidently wrong, and only running it
    against a real wp-cli showed it.

    So the number the customer decides on comes from the sentence wp-cli writes itself, and
    the per-table breakdown is best-effort on top. Both delimiters are handled, because a
    future wp-cli attached to a TTY would use pipes again.
    """
    text = stdout or ""
    if f"{_S}|error|nocli" in text:
        return {"ok": False, "reason": "WP-CLI is not installed on this server, so this "
                                       "cannot be run. Ask Ally to install it."}

    rows: list[dict] = []
    for line in text.splitlines():
        raw = line.strip().strip("|")
        parts = [c.strip() for c in (raw.split("\t") if "\t" in raw else raw.split("|"))]
        if len(parts) >= 3 and parts[0] and parts[0].lower() != "table":
            try:
                count = int(parts[2])
            except ValueError:
                continue
            if count:
                rows.append({"table": parts[0], "column": parts[1], "rows": count})

    # The two runs word it DIFFERENTLY, which only running both showed:
    #   dry  — "Success: 7 replacements to be made."
    #   real — "Success: Made 7 replacements."
    # A pattern that only fits the dry run silently falls back to summing the table, so the
    # number would come from the fragile path exactly when it matters most.
    summary = re.search(r"Success:.*?(\d+)\s+replacement", text)
    if summary:
        total = int(summary.group(1))
    elif rows:
        total = sum(r["rows"] for r in rows)
    else:
        # No summary and no rows. Saying "nothing matched" here would be a guess, and the
        # dangerous direction: it invites somebody to retype and run again.
        if "Success" not in text and text.strip():
            return {"ok": False, "reason": "We could not tell what that would change, so "
                                           "nothing was run for real. " + text.strip()[-200:]}
        total = 0
    return {"ok": True, "changes": rows, "total": total}


def explain_search_replace(result: dict, *, dry_run: bool) -> str:
    """What the numbers mean, before somebody commits to them."""
    if not result.get("ok"):
        return result.get("reason", "That could not be run.")
    total = result.get("total", 0)
    where = len(result.get("changes", []))
    if total == 0:
        return ("Nothing matched, so there is nothing to change. Check the spelling — a "
                "search that matches nothing is usually a typo rather than a site that is "
                "already correct.")
    if dry_run:
        return (f"This would change {total:,} value{'' if total == 1 else 's'} across "
                f"{where} place{'' if where == 1 else 's'}. Nothing has been changed yet. "
                f"Take a backup before running it for real — there is no undo.")
    return (f"Changed {total:,} value{'' if total == 1 else 's'} across {where} "
            f"place{'' if where == 1 else 's'}.")
