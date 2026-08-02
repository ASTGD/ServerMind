"""Redirects for one website — send an old address to a new one.

A copy of Ploi's Redirects screen, deliberately: two fields and a type, where the type's
stored values are nginx's own rewrite flags (``redirect`` = 302, ``permanent`` = 301),
because that is what they are on the way to being.

**The whole risk of this feature is that two free-text fields end up inside a live
web-server configuration.** A pattern is genuinely free-form — Ploi's own example is
``/(?!\\.well-known/)(.*)`` — so it cannot be validated down to a safe alphabet the way a
domain or a PHP version can. Three layers instead, in order:

1. the values reach the server as **base64**, so nothing in them is ever seen by a shell;
2. they are written **inside double quotes** in the config, so a ``;`` or a ``{`` is a
   character rather than the end of our directive — and the few characters quoting cannot
   survive (a newline, a double quote, a trailing backslash) are REFUSED at the door;
3. the file is **tested before the reload and restored if the test fails** — the same shape
   `php_service` uses, for the same reason: a configuration that does not parse takes down
   every site on the machine, not just this one.
"""
from __future__ import annotations

import base64
import re
import shlex

#: The two kinds, keyed by the nginx rewrite flag they become. Ploi's own select uses these
#: exact values, which is a good sign they mean the same thing on the way down.
TYPES: dict[str, str] = {
    "redirect": "Temporary",
    "permanent": "Permanent",
}

#: Everything between these lines belongs to us. Anything a person put in the file by hand
#: is outside them and is never touched — the block is rewritten wholesale on every change,
#: which is what makes adding and removing the same operation.
BEGIN = "# BEGIN ServerAlly redirects"
END = "# END ServerAlly redirects"

_MAX_LEN = 500


class RedirectError(Exception):
    """Something the owner can read and fix."""


def _reject_unquotable(value: str, field: str) -> None:
    """The three characters that survive being inside double quotes in a config file.

    A newline ends the directive and starts a new one; a double quote closes ours; a
    trailing backslash escapes the closing quote so the rest of the file becomes the value.
    Everything else — ``;`` ``{`` ``}`` ``#`` ``$`` — is safe *because* it is quoted, and
    all of those appear in legitimate patterns, so refusing them would break the feature to
    solve a problem quoting already solved.
    """
    if "\n" in value or "\r" in value:
        raise RedirectError(f"The {field} cannot contain a line break.")
    if '"' in value:
        raise RedirectError(f'The {field} cannot contain a double quote (").')
    if re.search(r"(?<!\\)\\$", value) or value.endswith("\\"):
        raise RedirectError(f"The {field} cannot end with a backslash.")
    if any(ord(c) < 32 for c in value):
        raise RedirectError(f"The {field} contains a character that is not allowed.")


def valid_from(value: str) -> str:
    """The path or pattern being redirected away from."""
    v = (value or "").strip()
    if not v:
        raise RedirectError("Enter the path to redirect from, for example /old-page.")
    if len(v) > _MAX_LEN:
        raise RedirectError("That redirect is too long.")
    _reject_unquotable(v, "path to redirect from")
    # A rewrite pattern is matched against the request path, which always begins with a
    # slash. "^/old" is the same rule written as an anchored regex, so both are allowed.
    if not (v.startswith("/") or v.startswith("^/")):
        raise RedirectError(
            f"“{v}” has to start with / — a redirect matches a path on this site, "
            f"like /old-page.")
    return v


def valid_to(value: str) -> str:
    """Where the visitor is sent."""
    v = (value or "").strip()
    if not v:
        raise RedirectError("Enter where visitors should be sent, for example "
                            "https://example.com/new-page.")
    if len(v) > _MAX_LEN:
        raise RedirectError("That address is too long.")
    _reject_unquotable(v, "destination")
    if not (v.startswith("/") or re.match(r"^https?://", v, re.I)):
        raise RedirectError(
            f"“{v}” has to be a full address starting with http:// or https://, "
            f"or a path on this site starting with /.")
    return v


def valid_type(value: str) -> str:
    v = (value or "").strip().lower()
    if v not in TYPES:
        raise RedirectError("Choose either Temporary (302) or Permanent (301).")
    return v


def label_for(kind: str) -> str:
    return TYPES.get(kind, kind)


# ── What goes in the config ──────────────────────────────────────────────────

def render_block(rules: list[dict], *, apache: bool) -> str:
    """The managed block, for whichever web server this site is served by.

    Both are written from the same list, so the two can never mean different things — and
    an empty list renders to nothing at all, which is how removing the last redirect
    leaves the config exactly as it was before the first one was added.
    """
    if not rules:
        return ""
    lines = [BEGIN]
    if apache:
        lines.append("RewriteEngine On")
        for r in rules:
            code = "301" if r["type"] == "permanent" else "302"
            lines.append(f'RewriteRule "{r["from"]}" "{r["to"]}" [R={code},L]')
    else:
        for r in rules:
            lines.append(f'rewrite "{r["from"]}" "{r["to"]}" {r["type"]};')
    lines.append(END)
    return "\n".join(lines)


def build_apply_command(config_path: str, domain: str, rules: list[dict], *,
                        apache: bool) -> str:
    """Write this site's redirects into its config, and undo it if the server refuses.

    The block is inserted after every ``server_name`` / ``ServerName`` line, so a site with
    separate http and https blocks gets the rules on both — a redirect that only worked on
    one scheme would look broken in exactly the confusing way.

    The block arrives base64-encoded: the values are free-form patterns, and this is the one
    encoding that cannot be argued with by a shell.
    """
    block = render_block(rules, apache=apache)
    # Always produced, even when empty: removing the last redirect runs exactly the same
    # command as adding the first, so there is no separate delete path to get wrong.
    encoded = base64.b64encode(block.encode()).decode()
    cfg = shlex.quote(config_path)
    dom = shlex.quote(domain)

    # One awk pass does both halves — drop our old block, then re-insert the new one after
    # every server_name / ServerName line. Deliberately not two `sed -i` calls: the in-place
    # flag and the `r` command both differ between sed implementations, and two passes can
    # disagree about what "our block" is if the first one is interrupted.
    awk = (
        'BEGIN { while ((getline l < B) > 0) blk[++n] = l } '
        '$0 == BEGINM { skip = 1 } '
        'skip { if ($0 == ENDM) skip = 0; next } '
        '{ print } '
        '/^[ \\t]*(server_name|ServerName)[ \\t]/ { for (i = 1; i <= n; i++) print blk[i] }'
    )

    return (
        f'set -e; '
        f'CFG={cfg}; DOM={dom}; '
        f'[ -f "$CFG" ] || {{ echo "This site\'s configuration file is not there."; exit 3; }}; '
        f'BK="$CFG.serverally.$(date +%s).bak"; cp -p "$CFG" "$BK"; '
        # Beside the config on purpose: same filesystem, and the suffixes are ones no web
        # server globs, so a half-written file can never be loaded as configuration.
        f'BLK="$CFG.serverally.block.tmp"; NEW="$CFG.serverally.new.tmp"; '
        f'printf %s {shlex.quote(encoded)} | base64 -d > "$BLK"; '
        f'awk -v B="$BLK" -v BEGINM={shlex.quote(BEGIN)} -v ENDM={shlex.quote(END)} '
        f'  {shlex.quote(awk)} "$CFG" > "$NEW"; '
        # Copied back rather than moved, so the file keeps its own owner and permissions.
        f'cat "$NEW" > "$CFG"; rm -f "$NEW" "$BLK"; '
        f'if ! (nginx -t 2>/dev/null || apachectl configtest 2>/dev/null); then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  echo "The web server refused it."; exit 4; fi; '
        f'systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null '
        f'  || systemctl reload httpd 2>/dev/null || true; '
        # A config that parses can still take the site down, so the site is asked whether it
        # still answers — the same content-not-status rule the rest of the product follows.
        # A redirect legitimately answers 301/302, so those count as working.
        f'OK=no; for i in 1 2 3 4; do '
        f'  C="$(curl -s -o /dev/null -w "%{{http_code}}" --max-time 5 '
        f'      -H "Host: $DOM" http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'  case "$C" in 2*|3*|401|403|404) OK=yes; break ;; esac; sleep 2; done; '
        f'if [ "$OK" != yes ]; then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null || true; '
        f'  echo "The site stopped answering."; exit 5; fi; '
        f'rm -f "$BK"; echo "applied"'
    )


_OUTCOMES: dict[int, str] = {
    3: "This site's configuration file could not be found on the server, so nothing changed.",
    4: ("The web server refused the redirect, so it was undone. Your site and every other "
        "site on this server are unaffected."),
    5: ("The site stopped answering with that redirect in place, so it was removed again. "
        "Check the path and the destination."),
}


def explain(code: int, output: str) -> tuple[bool, str]:
    """Our sentence for every failure, not the script's last line.

    A script that prints a success line and then fails on the step after would otherwise
    tell the owner the redirect is live when it is not. The exit code is the fact.
    """
    if code == 0:
        return True, "Saved."
    base = _OUTCOMES.get(code, "The redirect could not be saved.")
    last = next((l.strip() for l in reversed((output or "").splitlines()) if l.strip()), "")
    detail = f" The server said: {last}" if last and last not in base else ""
    return False, f"{base}{detail}"
