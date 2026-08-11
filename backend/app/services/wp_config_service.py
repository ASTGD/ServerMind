"""Editing `wp-config.php` — Ploi's WordPress → Configuration.

The file every WordPress owner is told to edit and never does, because getting it wrong takes
the site down completely: it is PHP, it is loaded before anything else, and a missing
semicolon produces a blank white page with no message anywhere a customer would look.

So the discipline is the same one the `.env` editor already proved, with one addition that
matters more here.

**The content never touches a command line.** wp-config.php holds the database password and
the authentication salts in clear text. An argument is visible in `ps` while the command runs
and is kept in the stored output of the run, so the bytes travel over SFTP and the shell only
handles what carries no value: the backup, the ownership, the rename and the check.

**It must still be valid PHP, and that is checked before it goes live.** `php -l` on the new
file catches the missing semicolon and the unclosed quote — the two ways this actually breaks
— before the real file is replaced at all, rather than after a visitor finds out.

**A constant written after the "stop editing" line is ignored.** WordPress `require`s
wp-settings.php there and never reads the rest, so an edit below it looks perfectly correct
in the file and does nothing. That is the single most confusing failure this screen can
produce, so it is warned about rather than silently allowed.
"""
from __future__ import annotations

import logging
import re
import shlex

logger = logging.getLogger(__name__)

#: Written beside the real file, never into a temp directory: a rename across filesystems is
#: a copy, and a copy can be half-done when the disk fills.
TMP_NAME = "wp-config.serverally.new"

#: WordPress stops reading the file here.
_STOP = re.compile(r"^\s*/\*\s*That's all, stop editing", re.M | re.I)
_REQUIRE = re.compile(r"^\s*require(_once)?[\s(].*wp-settings\.php", re.M)

#: Values nobody should be shown back on a screen, and nobody should have to scroll past.
_SECRET_LINE = re.compile(
    r"define\(\s*['\"](DB_PASSWORD|AUTH_KEY|SECURE_AUTH_KEY|LOGGED_IN_KEY|NONCE_KEY|"
    r"AUTH_SALT|SECURE_AUTH_SALT|LOGGED_IN_SALT|NONCE_SALT)['\"]", re.I)

MAX_BYTES = 200_000


class WpConfigError(Exception):
    """Something the customer can read and act on."""


def config_path(doc_root: str) -> str:
    """wp-config.php sits at the root of the WordPress install.

    WordPress also supports it ONE level above the install — a documented way to keep it out
    of the served folder — but this only ever edits the one the probe actually found, which
    is passed in rather than guessed at.
    """
    return f"{(doc_root or '').rstrip('/')}/wp-config.php"


def check_content(text: str) -> bytes:
    """Everything decidable without the server. Raises rather than saving something broken."""
    if text is None:
        raise WpConfigError("There is nothing to save.")
    data = text.encode("utf-8", "surrogatepass")
    if len(data) > MAX_BYTES:
        raise WpConfigError("That file is too large to be a wp-config.php.")
    if not data.strip():
        raise WpConfigError("An empty wp-config.php would take the site down completely.")
    if "<?php" not in text[:200]:
        raise WpConfigError("A wp-config.php has to start with <?php.")
    # The two constants WordPress cannot start without. Losing one is the classic
    # copy-paste-over-the-top accident, and it produces the same blank page as a syntax error.
    for needed in ("DB_NAME", "DB_USER"):
        if needed not in text:
            raise WpConfigError(
                f"{needed} is missing. Without it WordPress cannot reach its database and "
                f"the site shows a blank page.")
    if not data.endswith(b"\n"):
        data += b"\n"
    return data


def warnings(text: str) -> list[str]:
    """Things worth saying before saving, none of which are worth refusing over."""
    out: list[str] = []
    stop = _STOP.search(text or "")
    req = _REQUIRE.search(text or "")
    edge = stop or req
    if edge:
        tail = text[edge.start():]
        # A `define` below that line is read by nothing. It is the most confusing outcome
        # this screen can produce: the file plainly says the right thing and WordPress
        # behaves as though it does not.
        if re.search(r"^\s*define\s*\(", tail, re.M):
            out.append(
                "There is a define() below the “stop editing” line. WordPress "
                "loads the rest of itself there and never reads what comes after, so that "
                "setting will have no effect — move it above that line.")
    else:
        out.append("This file does not load wp-settings.php. WordPress will not start "
                   "without that line.")
    if "WP_DEBUG_DISPLAY" not in (text or "") and re.search(
            r"define\(\s*['\"]WP_DEBUG['\"]\s*,\s*true", text or "", re.I):
        out.append(
            "Debug mode is on without WP_DEBUG_DISPLAY set to false, which prints PHP "
            "errors into the page for every visitor.")
    return out


def redact(text: str) -> tuple[str, int]:
    """Mask the password and the salts for display.

    The browser is where somebody EDITS this file, so the real values have to be sent — a
    masked value saved back would write the mask into the file. This is used for the preview
    and the summary, never for the editable content, and the split is deliberate.
    """
    hidden = 0
    out = []
    for line in (text or "").splitlines():
        if _SECRET_LINE.search(line):
            hidden += 1
            out.append(re.sub(r"(,\s*)(['\"]).*?\2", r"\1'••••••'",
                              line, count=1))
        else:
            out.append(line)
    return "\n".join(out), hidden


def build_apply_command(doc_root: str, domain: str, *, php_bin: str = "") -> str:
    """Put the uploaded file in place, prove PHP can parse it, and undo it if the site stops.

    The new content is already on the server, written over SFTP beside the real file, so this
    command never carries a credential.

    The order is the safety: parse the NEW file first, and only then replace the real one.
    Replacing first and checking after leaves a window in which every visitor to the site
    gets a blank page.
    """
    root = (doc_root or "").rstrip("/")
    p = shlex.quote(config_path(root))
    t = shlex.quote(f"{root}/{TMP_NAME}")
    d = shlex.quote(domain)
    php = shlex.quote(php_bin or "php")

    return (
        f'set -e; P={p}; T={t}; D={d}; PHP={php}; '
        f'[ -f "$T" ] || {{ echo "arrived=no"; exit 3; }}; '
        # A PHP that cannot parse is not a reason to refuse the edit — it is a reason to say
        # we could not check it. `php -l` missing entirely is different from it failing.
        f'if command -v "$PHP" >/dev/null 2>&1; then '
        f'  if ! "$PHP" -l "$T" >/tmp/.sa_wpl.$$ 2>&1; then '
        f'    echo "lint=bad"; sed -n "1,5p" /tmp/.sa_wpl.$$; rm -f /tmp/.sa_wpl.$$ "$T"; '
        f'    exit 6; fi; '
        f'  rm -f /tmp/.sa_wpl.$$; '
        f'else echo "lint=skipped"; fi; '
        # What the site was doing BEFORE. A site already down must not have its outage
        # blamed on this edit and a good change reverted.
        f'WAS="$(curl -s -o /dev/null -w "%{{http_code}}" --max-time 8 -H "Host: $D" '
        f'      http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'BK=""; OWNER=""; MODE="640"; '
        f'if [ -f "$P" ]; then '
        f'  BK="$P.serverally.$(date +%s).bak"; cp -p "$P" "$BK"; '
        f'  OWNER="$(stat -c %U:%G "$P" 2>/dev/null || true)"; '
        f'  MODE="$(stat -c %a "$P" 2>/dev/null || echo 640)"; '
        f'fi; '
        # Ownership and mode before the rename, so the file is never briefly in place with
        # the wrong owner — a window in which every visitor gets a 500.
        f'[ -n "$OWNER" ] && chown "$OWNER" "$T" 2>/dev/null || true; '
        f'chmod "$MODE" "$T" 2>/dev/null || chmod 640 "$T"; '
        f'mv -f "$T" "$P"; '
        # Content, not a status code: a broken wp-config produces a 200 with an empty body
        # as often as it produces a 500.
        f'OK=no; B=/tmp/.sa_wp.$$; '
        f'for i in 1 2 3; do '
        f'  C="$(curl -s -o "$B" -w "%{{http_code}}" --max-time 8 -H "Host: $D" '
        f'      http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'  case "$C" in 3*) OK=yes ;; 2*) [ -s "$B" ] && OK=yes ;; esac; '
        f'  [ "$OK" = yes ] && break; sleep 2; done; rm -f "$B"; '
        f'if [ "$OK" != yes ]; then '
        f'  case "$WAS" in 000|5*) echo "saved=broken"; rm -f "$BK"; exit 0 ;; esac; '
        f'  if [ -n "$BK" ]; then cp -p "$BK" "$P"; rm -f "$BK"; fi; '
        f'  echo "reverted=site"; exit 5; fi; '
        f'rm -f "$BK" 2>/dev/null || true; echo "saved"'
    )


def build_discard_command(doc_root: str) -> str:
    """Remove a temporary upload that never got applied. Only ever our own file — it sits
    next to the real one and holds the same credentials."""
    root = (doc_root or "").rstrip("/")
    t = shlex.quote(f"{root}/{TMP_NAME}")
    return f'case {t} in */{TMP_NAME}) rm -f {t} ;; *) exit 4 ;; esac; echo removed'


def explain(code: int, output: str) -> tuple[bool, str]:
    """What the customer reads. Ours, keyed off the markers — never the script's last line."""
    text = output or ""
    if code == 0 and "saved=broken" in text:
        return True, ("Saved. The site was already not loading before this ran, so that is a "
                      "separate problem — the change was kept, because putting the old "
                      "file back would not have fixed it.")
    if code == 0:
        return True, "Saved. The site was checked afterwards and is still serving."
    if code == 6:
        detail = ""
        for line in text.splitlines():
            if "error" in line.lower() and "wp-config" in line.lower():
                # PHP's own message names the line number, which is the useful part.
                detail = " " + line.split("in /")[0].strip()
                break
        return False, (f"That is not valid PHP, so nothing was changed.{detail}")
    if code == 5:
        return False, ("The site stopped loading with those settings, so the previous "
                       "wp-config.php was put back.")
    if code == 3:
        return False, "The new file never reached the server, so nothing was changed."
    if code == 4:
        return False, "That path is not one we will touch."
    return False, "The file could not be saved, and nothing was changed."
