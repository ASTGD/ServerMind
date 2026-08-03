"""Extra domains that answer for the same site.

The second-smallest thing on the Manage screen and the one with the sharpest edge: an alias
is written into `server_name`, and `server_name` is how the web server decides which site a
visitor gets. Point it at a domain that already belongs to a neighbour and their traffic
silently arrives here instead — which is why the checks below refuse rather than warn.

Everything follows the rule the redirects and the vhost editor already proved on real
servers: keep a copy, write, make the web server ACCEPT it before reloading, confirm the
site still answers, and put the old file back on any failure. A configuration that does not
parse does not break one site, it stops the reload for every site on the machine.
"""
from __future__ import annotations

import base64
import re
import shlex

# A hostname, not a URL. Deliberately strict: this value ends up deciding whose visitors
# land where, so anything ambiguous is refused instead of normalised into something the
# customer did not type.
_DOMAIN = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")


class AliasError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def clean(alias: str) -> str:
    """Validate an alias, or refuse it with the reason.

    Validated rather than escaped, like every other name in this product: the value lands in
    a web-server directive, and the set of legitimate hostnames is small and well defined.
    """
    value = (alias or "").strip().lower().rstrip(".")
    if not value:
        raise AliasError("Give a domain name to add.")
    # People paste what they have. Say what is wrong rather than quietly repairing it, so
    # the thing they end up with is the thing they meant.
    if "://" in value or "/" in value:
        raise AliasError("Give just the domain — no https:// and no path.")
    if value.startswith("*."):
        raise AliasError(
            "A wildcard cannot be added here. It would catch every subdomain, including "
            "ones you later want to point somewhere else.")
    if len(value) > 253 or not _DOMAIN.match(value):
        raise AliasError(f"“{alias}” is not a domain name.")
    return value


def check_new(alias: str, *, domain: str, existing: list[str],
              taken: dict[str, str] | None = None) -> str:
    """Refuse an alias that would take traffic from something else.

    ``taken`` maps a domain to the site that already answers for it on this server. The
    check exists because the failure is silent: the web server simply hands that name to
    whichever block claims it, so a neighbour's visitors would arrive here with nothing on
    either screen saying why.
    """
    value = clean(alias)
    if value == (domain or "").strip().lower():
        raise AliasError("That is already this site's own domain.")
    if value in {a.strip().lower() for a in existing}:
        raise AliasError("That domain is already an alias of this site.")
    owner = (taken or {}).get(value)
    if owner:
        raise AliasError(
            f"“{value}” already belongs to {owner} on this server. Adding it here would "
            f"quietly take that site's visitors.")
    return value


def server_names(domain: str, aliases: list[str]) -> str:
    """The full list the web server should answer for, the site's own name first."""
    seen, out = set(), []
    for name in [domain, *aliases]:
        value = (name or "").strip().lower()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return " ".join(out)


def build_apply_command(config_path: str, domain: str, aliases: list[str], *,
                        apache: bool) -> str:
    """Rewrite this site's names into its configuration, and undo it if anything objects.

    EVERY `server_name` line in the file is rewritten, not just the first. A site with
    separate http and https blocks has two, and updating one would leave the alias working
    on one scheme and 404ing on the other — which reads to the customer as "it half works",
    the most expensive kind of bug to report.
    """
    names = server_names(domain, aliases)
    cfg = shlex.quote(config_path)
    dom = shlex.quote(domain)

    if apache:
        # Apache splits it: ServerName is the one canonical name, ServerAlias is the rest.
        extra = " ".join(n for n in names.split() if n != domain.strip().lower())
        line = f"    ServerAlias {extra}" if extra else ""
        awk = (
            '/^[ \\t]*ServerAlias[ \\t]/ { next } '
            '{ print } '
            '/^[ \\t]*ServerName[ \\t]/ { if (L != "") print L }'
        )
        awk_args = f'-v L={shlex.quote(line)} '
    else:
        # nginx keeps every name on the one directive, so the line is replaced outright.
        awk = (
            '/^[ \\t]*server_name[ \\t]/ '
            '{ match($0, /^[ \\t]*/); print substr($0, 1, RLENGTH) "server_name " N ";"; next } '
            '{ print }'
        )
        awk_args = f'-v N={shlex.quote(names)} '

    return (
        f'set -e; '
        f'CFG={cfg}; DOM={dom}; '
        f'[ -f "$CFG" ] || {{ echo "This site\'s configuration file is not there."; exit 3; }}; '
        f'BK="$CFG.serverally.$(date +%s).bak"; cp -p "$CFG" "$BK"; '
        # Beside the config on purpose: same filesystem, and a suffix no web server globs,
        # so a half-written file can never be picked up as configuration.
        f'NEW="$CFG.serverally.new.tmp"; '
        f'awk {awk_args}{shlex.quote(awk)} "$CFG" > "$NEW"; '
        # Copied back rather than moved, so the file keeps its own owner and permissions.
        f'cat "$NEW" > "$CFG"; rm -f "$NEW"; '
        f'if ! (nginx -t 2>/dev/null || apachectl configtest 2>/dev/null); then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  echo "The web server refused it."; exit 4; fi; '
        f'systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null '
        f'  || systemctl reload httpd 2>/dev/null || true; '
        # Parsing is not serving. The site is asked whether it still answers under its OWN
        # name — the same content-not-status rule the rest of the product follows.
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
    4: ("The web server refused that domain, so it was undone. Your site and every other "
        "site on this server are unaffected."),
    5: ("The site stopped answering once that domain was added, so it was removed again. "
        "Nothing is left changed."),
}


def explain(code: int, output: str) -> tuple[bool, str]:
    """Turn an exit code into the sentence the customer reads."""
    if code == 0:
        return True, ("Added. The web server accepted it and the site still answers — but "
                      "point that domain's DNS here before anyone can use it, and HTTPS "
                      "will not cover it until a certificate is issued for it too.")
    if code in _OUTCOMES:
        return False, _OUTCOMES[code]
    tail = (output or "").strip().splitlines()
    return False, (tail[-1] if tail else "That domain could not be added.")
