"""A username and password in front of a site — Ploi's "Authentication".

Named `site_auth_service` and not `auth_service` because that name is already the login and
JWT service for ServerAlly itself. They have nothing to do with each other.

What it is for: a site being built, a client preview, an admin path nobody outside the
office should reach. The browser asks for a name and password before anything is served.

**The password is hashed here and only the hash is ever sent to the server.** It never
appears in a command, so it cannot land in shell history, in `ps`, or in the stored output
of the run — the same reason database passwords go in through a file rather than on the
command line.

The other half is nginx's location precedence, which is where this feature goes quietly
wrong. A plain `location /wp-admin` does NOT protect `/wp-admin/index.php`, because the
regex `location ~ \\.php$` wins for anything ending in `.php` — so anyone who guessed a PHP
path would walk straight past the password. `^~` is what stops that, and the PHP handler
must be repeated inside the protected block or those pages stop executing and start being
offered as downloads.
"""
from __future__ import annotations

import base64
import re
import shlex

from passlib.hash import apr_md5_crypt

# One password file per site, outside every web root by construction: a password file a
# visitor can download is worse than no password at all.
AUTH_DIR = "/etc/nginx/serverally-auth"

BEGIN = "# --- ServerAlly authentication (managed) ---"
END = "# --- end ServerAlly authentication ---"

_NAME = re.compile(r"^[A-Za-z0-9._-]{1,32}$")


class AuthError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def clean_name(name: str) -> str:
    """A username, validated rather than escaped — it becomes a line in a password file."""
    value = (name or "").strip()
    if not value:
        raise AuthError("Give a username.")
    if not _NAME.match(value):
        raise AuthError(
            "A username can use letters, numbers, dots, dashes and underscores — nothing "
            "else, and up to 32 characters.")
    return value


def check_password(password: str) -> str:
    """Refuse a password too weak to be worth the trouble of adding one."""
    value = password or ""
    if len(value) < 8:
        raise AuthError("Use at least 8 characters — this is the only thing in the way.")
    if len(value) > 200:
        raise AuthError("That password is too long.")
    return value


def clean_path(path: str | None) -> str:
    """Which part of the site to protect. Empty means all of it, which is the common case.

    Refused rather than repaired when it is something else: this value decides what ends up
    protected, and quietly protecting a different path than the customer typed is the worst
    outcome the feature has.
    """
    value = (path or "").strip()
    if not value:
        return ""
    if not value.startswith("/"):
        value = "/" + value
    if ".." in value or " " in value or "\n" in value:
        raise AuthError("That path is not one we can protect. Use something like /wp-admin.")
    if not re.match(r"^/[A-Za-z0-9._~/-]*$", value):
        raise AuthError("A path can use letters, numbers, dots, dashes, underscores and /.")
    return value.rstrip("/")


def hash_password(password: str) -> str:
    """apr1, which nginx and Apache both understand everywhere.

    Deliberately not bcrypt: nginx only accepts it when the C library underneath happens to
    support it, so it would work on one distribution and silently reject every login on
    another — a failure indistinguishable from the customer typing the wrong password.
    """
    return apr_md5_crypt.hash(check_password(password))


def htpasswd_line(name: str, password: str) -> str:
    return f"{clean_name(name)}:{hash_password(password)}"


def parse_users(content: str) -> list[str]:
    """The usernames in a password file.

    **Hashes are never returned.** Nothing upstream has a use for one, and a hash on a
    screen is a hash in a screenshot.
    """
    out = []
    for line in (content or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name = line.split(":", 1)[0].strip()
        if _NAME.match(name):
            out.append(name)
    return out


def replace_user(content: str, name: str, line: str | None) -> list[str]:
    """Add, change or remove one user, leaving the others untouched.

    Rewriting the whole file from a list we hold would drop any user added by hand on the
    server — and this file is one an administrator may well have touched.
    """
    keep = []
    for existing in (content or "").splitlines():
        existing = existing.strip()
        if not existing or ":" not in existing:
            continue
        if existing.split(":", 1)[0].strip() == name:
            continue
        keep.append(existing)
    if line:
        keep.append(line)
    return keep


def build_read_command(domain: str) -> str:
    """Read this site's password file, if it has one. Base64, so no content is interpreted."""
    f = shlex.quote(f"{AUTH_DIR}/{domain}")
    return f'if [ -f {f} ]; then base64 < {f}; fi'


def _whole_site_block(auth_file: str) -> str:
    """Covers every location including the PHP one, so there is no precedence problem."""
    return (f"{BEGIN}\n"
            f'    auth_basic "Restricted";\n'
            f"    auth_basic_user_file {auth_file};\n"
            f"{END}\n")


def build_apply_command(config_path: str, domain: str, lines: list[str], path: str, *,
                        apache: bool) -> str:
    """Write the users and the guard, and undo all of it if anything objects.

    An empty user list removes the guard entirely — the same command adds the first user and
    removes the last, so there is no separate "turn it off" path to get wrong.
    """
    auth_file = f"{AUTH_DIR}/{domain}"
    body = ("\n".join(lines) + "\n") if lines else ""
    encoded = base64.b64encode(body.encode()).decode()
    cfg, dom, af = shlex.quote(config_path), shlex.quote(domain), shlex.quote(auth_file)
    anchor = "ServerName" if apache else "server_name"

    if not lines:
        render = 'printf "" > "$BLKF"; '
    elif apache:
        block = (f"{BEGIN}\n"
                 f"    <Location {path or '/'}>\n"
                 f"        AuthType Basic\n"
                 f'        AuthName "Restricted"\n'
                 f"        AuthUserFile {auth_file}\n"
                 f"        Require valid-user\n"
                 f"    </Location>\n"
                 f"{END}\n")
        render = f'printf %s {shlex.quote(block)} > "$BLKF"; '
    elif not path:
        render = f'printf %s {shlex.quote(_whole_site_block(auth_file))} > "$BLKF"; '
    else:
        # The PHP socket is read off the site's OWN configuration rather than guessed: a
        # server with several PHP versions has several sockets, and pointing the protected
        # path at the wrong one gives 502s that look like this feature broke the site.
        render = (
            f'SOCK="$(grep -m1 -oE "fastcgi_pass[ \\t]+[^;]+;" "$CFG" '
            f'  | sed -E "s/fastcgi_pass[ \\t]+//; s/;\\$//" || true)"; '
            f'{{ printf "%s\\n" {shlex.quote(BEGIN)}; '
            # `^~` is the whole point: a plain prefix location loses to the regex PHP
            # location, so /wp-admin/index.php would be served with no password at all.
            f'  printf "    location ^~ %s/ {{\\n" {shlex.quote(path)}; '
            f'  printf "        auth_basic \\"Restricted\\";\\n"; '
            f'  printf "        auth_basic_user_file %s;\\n" {af}; '
            f'  printf "        try_files \\$uri \\$uri/ /index.php?\\$query_string;\\n"; '
            # Repeated INSIDE on purpose. `^~` stops nginx considering the regex PHP
            # location, so without this the protected path stops executing PHP entirely.
            f'  if [ -n "$SOCK" ]; then '
            f'    printf "        location ~ \\\\.php\\$ {{\\n"; '
            f'    printf "            auth_basic \\"Restricted\\";\\n"; '
            f'    printf "            auth_basic_user_file %s;\\n" {af}; '
            f'    printf "            include fastcgi_params;\\n"; '
            f'    printf "            fastcgi_param SCRIPT_FILENAME \\$document_root\\$fastcgi_script_name;\\n"; '
            f'    printf "            fastcgi_pass %s;\\n" "$SOCK"; '
            f'    printf "        }}\\n"; fi; '
            f'  printf "    }}\\n"; '
            f'  printf "%s\\n" {shlex.quote(END)}; }} > "$BLKF"; '
        )

    awk = (
        'BEGIN { while ((getline l < B) > 0) blk[++n] = l } '
        '$0 == BEGINM { skip = 1 } '
        'skip { if ($0 == ENDM) skip = 0; next } '
        '{ print } '
        f'/^[ \\t]*({anchor})[ \\t]/ {{ for (i = 1; i <= n; i++) print blk[i] }}'
    )

    return (
        f'set -e; '
        f'CFG={cfg}; DOM={dom}; AF={af}; '
        f'[ -f "$CFG" ] || {{ echo "This site\'s configuration file is not there."; exit 3; }}; '
        f'mkdir -p {shlex.quote(AUTH_DIR)}; chmod 750 {shlex.quote(AUTH_DIR)}; '
        # The DIRECTORY has to be traversable by the web server too, not just the file.
        # Found against real nginx: with the folder left root:root, the correct password
        # returned 500 — nginx could not open the file it had been told to check, which
        # reads to the customer as the password feature simply being broken.
        f'chown root:www-data {shlex.quote(AUTH_DIR)} 2>/dev/null '
        f'  || chown root:nginx {shlex.quote(AUTH_DIR)} 2>/dev/null || true; '
        f'printf %s {shlex.quote(encoded)} | base64 -d > "$AF"; chmod 640 "$AF"; '
        f'chown root:www-data "$AF" 2>/dev/null || chown root:nginx "$AF" 2>/dev/null || true; '
        # No users left means no password file: an empty one would refuse every login while
        # the screen showed the site as open.
        f'[ -s "$AF" ] || rm -f "$AF"; '
        f'BK="$CFG.serverally.$(date +%s).bak"; cp -p "$CFG" "$BK"; '
        f'BLKF="$CFG.serverally.block.tmp"; NEW="$CFG.serverally.new.tmp"; '
        f'{render}'
        f'awk -v B="$BLKF" -v BEGINM={shlex.quote(BEGIN)} -v ENDM={shlex.quote(END)} '
        f'  {shlex.quote(awk)} "$CFG" > "$NEW"; '
        f'cat "$NEW" > "$CFG"; rm -f "$NEW" "$BLKF"; '
        f'if ! (nginx -t 2>/dev/null || apachectl configtest 2>/dev/null); then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  echo "The web server refused it."; exit 4; fi; '
        f'systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null '
        f'  || systemctl reload httpd 2>/dev/null || true; '
        # With a password in front, 401 is the CORRECT answer and the proof it works. What
        # would mean failure is the site not answering at all.
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
    4: ("The web server refused that, so it was undone. Your site and every other site on "
        "this server are unaffected."),
    5: ("The site stopped answering with that in place, so it was removed again. Nothing is "
        "left changed."),
}


def explain(code: int, output: str, *, users: int, path: str) -> tuple[bool, str]:
    if code == 0:
        if users == 0:
            return True, "Removed. The site is open to everyone again."
        where = f"{path}/" if path else "the whole site"
        return True, f"Saved. A browser now asks for a username and password before {where}."
    if code in _OUTCOMES:
        return False, _OUTCOMES[code]
    tail = (output or "").strip().splitlines()
    return False, (tail[-1] if tail else "That could not be saved.")
