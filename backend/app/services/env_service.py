"""Read and write a Laravel site's `.env` — the file that holds every credential it has.

For a Laravel site this is the most-edited file in its life: the database password, the
mail password, the app key, every API token. Today it can only be reached through the File
Manager, which is not where anyone looks, and getting `rcmaa` live this morning needed
exactly these edits with nowhere to do them.

**The content never touches a command line.** Everything else in this codebase passes file
content through the shell as a base64 argument, and for a vhost or a redirect that is fine
because none of it is secret. This is different: an argument is visible in `ps` while the
command runs and it lands in the stored output of the run. So the bytes travel over SFTP
(`file_service`) and the shell only ever handles the things that carry no content — the
backup, the ownership, the rename, the cache rebuild, the check that the site still works.

**Four things can go wrong, and each has an answer:**

* the file becomes readable over the web, which publishes every password the app owns. We
  CHECK for that and say so loudly rather than assuming the layout is right;
* a bad edit takes the site down. The old file is kept and put back automatically;
* the file is written as root, so the application — running as the web-server user — can no
  longer read it and every page becomes a 500. Ownership and mode are read off the existing
  file and restored onto the new one;
* **nothing happens at all.** Laravel caches its configuration, and when it does, `.env` is
  not read again — the customer edits, saves, sees no change and reasonably concludes we
  are broken. So the cache is rebuilt whenever it was in use.
"""
from __future__ import annotations

import re
import shlex

#: An `.env` is a short text file. Anything larger is not one, and refusing early keeps a
#: mistaken upload from ever reaching the site.
MAX_BYTES = 64 * 1024

#: Written next to the real file and renamed over it, so a half-finished upload is never
#: the file the application reads.
TMP_NAME = ".env.serverally.new"

#: Keys whose values are shown masked until the customer asks to see them. Deliberately
#: matched on the NAME rather than on the value's shape — a password that happens to look
#: like a word is still a password.
_SECRET_KEY = re.compile(
    r"(PASS|PASSWORD|SECRET|KEY|TOKEN|CREDENTIAL|SALT|CIPHER|DSN|PRIVATE)", re.I)

#: `APP_KEY` matches the rule above but is worth naming: losing it makes every encrypted
#: value and every signed link in the database unreadable, which is not obvious from the
#: name alone.
CRITICAL_KEYS = frozenset({"APP_KEY"})


class EnvError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def env_path(app_root: str) -> str:
    """Where the file lives. The app root comes from the Laravel probe, which finds it by
    locating `artisan` — never from the caller, and never guessed from the document root."""
    root = (app_root or "").rstrip("/")
    if not root.startswith("/") or ".." in root.split("/"):
        raise EnvError("We do not know where this application lives, so its settings file "
                       "cannot be opened.")
    return f"{root}/.env"


def check_content(text: str) -> bytes:
    """Refuse what should never be written, before anything is touched."""
    if text is None:
        raise EnvError("There is nothing to save.")
    data = text.encode("utf-8")
    if len(data) > MAX_BYTES:
        raise EnvError(
            f"That is {len(data) // 1024} KB. A settings file is a few hundred lines at "
            f"most, so this is refused rather than written.")
    if b"\x00" in data:
        raise EnvError("That is not a text file, so it will not be saved.")
    return data


def summarise(text: str) -> list[dict]:
    """One row per setting, for a reader who wants to scan rather than edit.

    Comments and blank lines are skipped, and a value is reported as `secret` by its KEY —
    so a screen can hide it without this function ever having to decide what a password
    looks like. The value itself is returned so the editor can show it on request; nothing
    here is a security boundary, it is a display hint.
    """
    rows: list[dict] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if not key:
            continue
        rows.append({
            "key": key,
            "value": value.strip().strip('"').strip("'"),
            "secret": bool(_SECRET_KEY.search(key)),
            "critical": key in CRITICAL_KEYS,
        })
    return rows


def build_facts_command(app_root: str, domain: str) -> str:
    """What we need to know before showing or changing the file. Read-only.

    The web-exposure check is the one that matters most and is the reason this runs at all:
    a Laravel app served from its own folder rather than from `public/` puts `.env` at a
    guessable address, and every password in it is then public. That is not a warning to
    add later — it is the first thing the screen should say.
    """
    p = shlex.quote(env_path(app_root))
    d = shlex.quote(domain)
    root = shlex.quote((app_root or "").rstrip("/"))
    return (
        f'P={p}; D={d}; '
        f'if [ -f "$P" ]; then echo "exists=yes"; else echo "exists=no"; fi; '
        f'echo "owner=$(stat -c %U:%G "$P" 2>/dev/null || echo unknown)"; '
        f'echo "mode=$(stat -c %a "$P" 2>/dev/null || echo unknown)"; '
        f'echo "bytes=$(stat -c %s "$P" 2>/dev/null || echo 0)"; '
        # Is the file reachable from the internet? Asked of the web server rather than
        # reasoned about from the layout, because the layout is exactly what can be wrong.
        f'echo "web=$(curl -s -o /dev/null -w "%{{http_code}}" --max-time 6 '
        f'  -H "Host: $D" http://127.0.0.1/.env 2>/dev/null || echo 000)"; '
        # If the configuration is cached, editing this file changes nothing until the cache
        # is rebuilt — the single most confusing failure this feature has.
        f'if [ -f {root}/bootstrap/cache/config.php ]; then echo "cached=yes"; '
        f'else echo "cached=no"; fi'
    )


def parse_facts(output: str) -> dict:
    fields: dict[str, str] = {}
    for line in (output or "").splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            fields[k.strip()] = v.strip()
    code = fields.get("web", "000")
    return {
        "exists": fields.get("exists") == "yes",
        "owner": fields.get("owner", "unknown"),
        "mode": fields.get("mode", "unknown"),
        "bytes": int(fields.get("bytes") or 0),
        "config_cached": fields.get("cached") == "yes",
        # Anything that is not a refusal means the file came back to a visitor.
        "web_readable": code.startswith("2"),
        "web_status": code,
    }


def exposure_warning(facts: dict) -> str | None:
    """The sentence somebody needs to read before anything else."""
    if not facts.get("web_readable"):
        return None
    return (
        "This file is downloadable from the internet right now — anyone requesting "
        "/.env on this site gets your database password, mail password and app key. "
        "The site is being served from the application's own folder instead of its "
        "public folder. Fix that before changing anything here, and treat every "
        "credential in this file as already leaked."
    )


def build_apply_command(app_root: str, domain: str, *, php_bin: str,
                        rebuild_cache: bool) -> str:
    """Put the uploaded file into place, and undo it if the site stops working.

    The new content is already on the server, written over SFTP to a temporary name beside
    the real file — so this command never carries a single credential. What it does is the
    part that has to be atomic and reversible.

    ``php_bin`` is resolved by the Laravel probe rather than looked up here, because the
    default `php` on a panel server is frequently NOT the one the site runs: on a real
    CyberPanel box it is 8.3 while the app needs 8.4, and Composer's platform check then
    fails the cache rebuild — which this function would read as "those settings are bad"
    and revert a perfectly good edit.
    """
    root = (app_root or "").rstrip("/")
    p, t = shlex.quote(env_path(root)), shlex.quote(f"{root}/{TMP_NAME}")
    r, d, php = shlex.quote(root), shlex.quote(domain), shlex.quote(php_bin or "php")

    # Run as the account that owns the file. A cache written by root is a cache the
    # application cannot read, which is the same delayed breakage as a root-owned .env.
    cache_cmd = (
        f'su -s /bin/bash "$OWNER_U" -c "cd {r} && {php} artisan config:cache --no-ansi" '
        f'  >/dev/null 2>&1'
    )
    rebuild = f'{cache_cmd} || FAILED=cache; ' if rebuild_cache else ''
    restore_cache = f'{cache_cmd} || true; ' if rebuild_cache else ''

    return (
        f'set -e; P={p}; T={t}; D={d}; FAILED=""; '
        f'[ -f "$T" ] || {{ echo "The new settings never arrived on the server."; exit 3; }}; '
        f'BK=""; OWNER=""; OWNER_U="root"; MODE="600"; '
        f'if [ -f "$P" ]; then '
        f'  BK="$P.serverally.$(date +%s).bak"; cp -p "$P" "$BK"; '
        f'  OWNER="$(stat -c %U:%G "$P" 2>/dev/null || true)"; '
        f'  OWNER_U="$(stat -c %U "$P" 2>/dev/null || echo root)"; '
        f'  MODE="$(stat -c %a "$P" 2>/dev/null || echo 600)"; '
        f'fi; '
        # Ownership and mode FIRST, then the rename — so the file is never briefly in place
        # with the wrong owner, a window in which every visitor gets a 500.
        f'[ -n "$OWNER" ] && chown "$OWNER" "$T" 2>/dev/null || true; '
        f'chmod "$MODE" "$T" 2>/dev/null || chmod 600 "$T"; '
        f'mv -f "$T" "$P"; '
        f'{rebuild}'
        # Content, not a status code. A Laravel app that cannot read its settings answers
        # 500 with a page; one whose database credentials are wrong answers 500 too.
        f'if [ -z "$FAILED" ]; then '
        f'  OK=no; B=/tmp/.sa_env.$$; '
        f'  for i in 1 2 3 4; do '
        f'    C="$(curl -s -o "$B" -w "%{{http_code}}" --max-time 8 -H "Host: $D" '
        f'        http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'    case "$C" in '
        f'      3*) OK=yes ;; '
        f'      2*) [ -s "$B" ] && OK=yes ;; '
        f'    esac; '
        f'    [ "$OK" = yes ] && break; sleep 2; done; rm -f "$B"; '
        f'  [ "$OK" = yes ] || FAILED=site; '
        f'fi; '
        f'if [ -n "$FAILED" ]; then '
        f'  if [ -n "$BK" ]; then cp -p "$BK" "$P"; rm -f "$BK"; fi; '
        f'  {restore_cache}'
        f'  echo "reverted=$FAILED"; exit 5; fi; '
        f'rm -f "$BK" 2>/dev/null || true; echo "saved"'
    )


def build_discard_command(app_root: str) -> str:
    """Remove a temporary upload that never got applied. Only ever our own file."""
    root = (app_root or "").rstrip("/")
    t = shlex.quote(f"{root}/{TMP_NAME}")
    return f'case {t} in */{TMP_NAME}) rm -f {t} ;; *) exit 4 ;; esac; echo removed'


_OUTCOMES: dict[int, str] = {
    3: "The new settings never reached the server, so nothing was changed.",
    4: "That path is not one we will touch.",
}


def explain(code: int, output: str) -> tuple[bool, str]:
    if code == 0:
        return True, ("Saved. The site was checked afterwards and is still serving.")
    if code == 5:
        why = "cache" if "reverted=cache" in (output or "") else "site"
        if why == "cache":
            return False, ("Laravel could not read those settings — it failed to rebuild "
                           "its configuration, so the previous file was put back and "
                           "nothing changed. The error is usually a missing quote or a "
                           "value with a space in it.")
        return False, ("The site stopped serving with those settings, so the previous "
                       "file was put back. Nothing is left changed.")
    if code in _OUTCOMES:
        return False, _OUTCOMES[code]
    tail = (output or "").strip().splitlines()
    return False, (tail[-1] if tail else "Those settings could not be saved.")
