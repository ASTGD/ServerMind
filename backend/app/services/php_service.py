"""Which PHP versions a server has, and which one each website uses.

Ploi asks for the PHP version when the server is created and lets you change it per site.
We installed whatever the distro happened to ship, which is PHP 8.1 on Ubuntu 22.04 — and
that is not a cosmetic gap: current Laravel needs 8.3+, and the older Laravel that would run
on 8.1 has security advisories Composer refuses to install. So "which PHP" decides whether a
customer can host their application at all.

Three separate jobs, with very different risk:

* **Reading** what is installed and what each site uses — free and safe.
* **Installing** another version — additive. Nothing that already works changes, because a
  new FPM listens on its own socket and no vhost points at it yet.
* **Switching a site** — the dangerous one. An application written for PHP 7 can throw a
  fatal error on PHP 8 and the site goes white the moment the config reloads. So a switch
  proves the site still serves afterwards and puts the old version back if it does not.

The probe is a FIXED bundle authored here, sentinel-split, like the metrics, security, log
and site probes. It is never assembled from anything a user typed.
"""
from __future__ import annotations

import logging
import re
import shlex

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

_SENTINEL = "___SM_PHP___"
# Every probe is bounded: ssh_service reads with a 60s channel timeout, so an unbounded
# command on a busy box would surface as a mystery hang rather than a slow answer.
_T = 20


def _t(seconds: int, cmd: str) -> str:
    """Bound a command, but fail OPEN — a box without coreutils `timeout` still answers.

    Failing closed here would be worse than slow: an empty probe section reads as
    "nothing installed", which is a confident wrong answer.
    """
    return f'if command -v timeout >/dev/null 2>&1; then timeout {seconds} {cmd}; else {cmd}; fi'


def build_probe() -> str:
    """One read-only pass: installed versions, the CLI default, and each vhost's socket."""
    return (
        # Installed FPM versions, from the packages that actually exist.
        f'for u in $({_t(_T, "ls -1 /etc/php 2>/dev/null")}); do '
        f'  [ -d "/etc/php/$u/fpm" ] && echo "{_SENTINEL}|version|$u"; done 2>/dev/null; '
        f'for b in $({_t(_T, "ls -1 /usr/bin/php[0-9]* 2>/dev/null")}); do '
        f'  echo "{_SENTINEL}|version|$(basename "$b" | sed -E \'s/^php//\')"; done 2>/dev/null; '
        # Which FPM units exist and which are running.
        f'{_t(_T, "systemctl list-units --type=service --no-legend \'php*-fpm.service\' 2>/dev/null")} '
        f'| sed -E \'s/^[^p]*php([0-9.]+)-fpm\\.service +[^ ]+ +[^ ]+ +([^ ]+).*/{_SENTINEL}|fpm|\\1|\\2/\' '
        f'| grep "^{_SENTINEL}" 2>/dev/null; '
        # The CLI default — what cron jobs and deploy scripts get.
        f'echo "{_SENTINEL}|cli|$(php -r \'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;\' 2>/dev/null)"; '
        # Which socket each site's config points at. This is what a switch rewrites, so it
        # is read from the same files rather than guessed.
        f'for d in /etc/nginx/sites-available /etc/nginx/conf.d /etc/apache2/sites-available /etc/httpd/conf.d; do '
        f'  [ -d "$d" ] || continue; '
        f'  for f in "$d"/*; do [ -f "$f" ] || continue; '
        # Comment lines are stripped FIRST. nginx's own default vhost carries a
        # commented-out `fastcgi_pass ... php7.4-fpm.sock`, and reporting that as the site's
        # live PHP version showed 7.4 on a server where 7.4 is not even installed — a
        # confident wrong answer, and the state a switch would be judged against.
        f'    s="$(sed -E "s/#.*$//" "$f" 2>/dev/null '
        f'         | grep -hoE "php[0-9.]*-?fpm[^;\\" ]*\\.sock" | head -1)"; '
        # The folder this config serves. Matching a site to its config on the document
        # root is the only way that cannot aim a switch at the wrong site: a filename
        # convention holds for the vhosts we write and for nobody else's.
        f'    r="$(sed -E "s/#.*$//" "$f" 2>/dev/null '
        f'         | grep -oE "(root|DocumentRoot)[[:space:]]+[^;[:space:]]+" | head -1 '
        f'         | awk "{{print \\$2}}")"; '
        f'    [ -n "$s" ] && echo "{_SENTINEL}|site|$f|$s|$r"; '
        f'  done; done 2>/dev/null; '
        f'echo "{_SENTINEL}|done|"'
    )


def parse_probe(output: str) -> dict:
    """Turn the probe's lines into what the UI needs. Positional and defensive."""
    versions: set[str] = set()
    fpm: dict[str, str] = {}
    cli: str | None = None
    sites: dict[str, tuple[str, str]] = {}

    for line in (output or "").splitlines():
        line = line.strip()
        if not line.startswith(f"{_SENTINEL}|"):
            continue
        parts = line.split("|")
        kind = parts[1] if len(parts) > 1 else ""
        if kind == "version" and len(parts) > 2:
            v = parts[2].strip()
            # "8.1" — never a stray path fragment or an empty match.
            if re.fullmatch(r"\d+\.\d+", v):
                versions.add(v)
        elif kind == "fpm" and len(parts) > 3:
            v, state = parts[2].strip(), parts[3].strip()
            if re.fullmatch(r"\d+\.\d+", v):
                fpm[v] = state
                versions.add(v)
        elif kind == "cli" and len(parts) > 2:
            v = parts[2].strip()
            if re.fullmatch(r"\d+\.\d+", v):
                cli = v
        elif kind == "site" and len(parts) > 3:
            # The FULL path, so the switch endpoint's allowlist is over paths this server
            # itself reported. A basename would have to be re-resolved against a guessed
            # directory, which is a way to aim the rewrite at the wrong file.
            path, sock = parts[2].strip(), parts[3].strip()
            root = parts[4].strip() if len(parts) > 4 else ""
            if path.startswith("/etc/"):
                sites[path] = (sock, root)

    def version_of(sock: str) -> str | None:
        m = re.search(r"php(\d+\.\d+)-fpm", sock)
        return m.group(1) if m else None

    return {
        "versions": sorted(versions, key=lambda v: [int(x) for x in v.split(".")]),
        "running": [v for v, state in fpm.items() if state == "running"],
        "cli_default": cli,
        "sites": [
            {"config": path, "name": path.rsplit("/", 1)[-1],
             "socket": sock, "root": root or None, "version": version_of(sock)}
            for path, (sock, root) in sorted(sites.items())
        ],
    }


async def read(server: Server) -> dict:
    """What PHP this server has. Read-only; best-effort so a probe failure is not fatal."""
    try:
        out, _err, _code = await connection_manager.execute(server, build_probe())
    except Exception:  # noqa: BLE001 — a read must never take the page down
        logger.warning("PHP probe failed for server %s", server.id, exc_info=True)
        return {"versions": [], "running": [], "cli_default": None, "sites": [],
                "error": "Could not read PHP information from this server."}
    return parse_probe(out)


# ── switching one site ───────────────────────────────────────────────────────
def config_for_site(sites: list[dict], doc_root: str | None,
                    domain: str) -> dict | None:
    """Which of this server's configs serves this site — or nothing.

    Returning nothing is a real answer and the reason this is a function rather than a
    lookup. Switching the wrong site's PHP version takes down a site nobody was touching,
    and on a server with forty vhosts the odds of a near-miss are not small. So the match
    has to be something that decides the question, and when nothing does, the screen says
    it cannot tell rather than picking the closest.

    The document root decides it: a config that serves this folder IS this site's config.
    The filename is a fallback for a server whose configs we cannot read a root out of —
    it holds for the vhosts we write ourselves and for nobody else's, so it is second.
    """
    if not sites:
        return None

    want = (doc_root or "").rstrip("/")
    if want:
        exact = [s for s in sites if (s.get("root") or "").rstrip("/") == want]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            # Two configs serving one folder is a real thing (an http and an https vhost),
            # and picking one of them at random is how only half a site gets switched.
            return None

    named = [s for s in sites
             if s.get("name") in (domain, f"{domain}.conf") and not (s.get("root") or "")]
    return named[0] if len(named) == 1 else None


def valid_version(value: str) -> str:
    """A version reaches a filesystem path and a config file, so it is validated, not escaped."""
    v = (value or "").strip()
    if not re.fullmatch(r"\d+\.\d+", v):
        raise ValueError(
            f"“{value}” is not a PHP version. Use something like 8.3.")
    return v


def build_switch_command(config_path: str, version: str, domain: str) -> str:
    """Point one site's config at another PHP version, and undo it if the site breaks.

    The whole risk of this feature is here. An application written for an older PHP can
    throw a fatal error on a newer one, and the site goes white the instant the config
    reloads — so this keeps a copy, proves the site still serves real content afterwards,
    and puts the old file back if it does not. A status code is not enough: a broken PHP
    app very often returns 200 with a blank or error body.
    """
    v = valid_version(version)
    cfg = shlex.quote(config_path)
    dom = shlex.quote(domain)
    sock = f"/run/php/php{v}-fpm.sock"
    return (
        f'set -e; '
        f'CFG={cfg}; V={shlex.quote(v)}; DOM={dom}; SOCK={shlex.quote(sock)}; '
        # Refuse rather than guess if the target FPM is not actually there.
        f'if [ ! -S "$SOCK" ]; then '
        f'  echo "PHP $V is not running on this server, so nothing was changed."; exit 3; fi; '
        # Read from the config rather than passed in, so it is always the root this site is
        # actually served from. Comments stripped first, same reason as the probe.
        f'DOCROOT="$(sed -E "s/#.*$//" "$CFG" 2>/dev/null '
        f'  | grep -oE "(root|DocumentRoot)[[:space:]]+[^;[:space:]]+" | head -1 '
        f'  | awk "{{print \\$2}}")"; '
        f'BK="$CFG.serverally.$(date +%s).bak"; cp -p "$CFG" "$BK"; '
        # Only the socket path changes; everything else in the config is left alone.
        f'sed -i -E "s#unix:/run/php/php[0-9.]*-?fpm[^;\\"]*\\.sock#unix:$SOCK#g; '
        f's#proxy:unix:/run/php/php[0-9.]*-?fpm[^|]*\\.sock#proxy:unix:$SOCK#g" "$CFG"; '
        f'if ! (nginx -t 2>/dev/null || apachectl configtest 2>/dev/null); then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  echo "The web server rejected the change, so it was undone."; exit 4; fi; '
        f'systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null '
        f'  || systemctl reload httpd 2>/dev/null || true; '
        # Two things have to be true, and the first one is the whole point of the change.
        #
        # A homepage check alone proves nothing about PHP: most sites serve a static
        # index.html at "/", so nginx answers it happily even when the FPM socket it was
        # just pointed at is dead. Verified live — a switch "succeeded" while PHP was
        # untested. So a throwaway PHP file is written into the document root, requested,
        # and removed: it proves PHP executes through THIS site's config AND that it is the
        # version we asked for. The name is unique and it is deleted whatever happens.
        f'PROBE=".serverally-phpcheck-$$.php"; PP="$DOCROOT/$PROBE"; PHP_OK=skip; '
        f'if [ -n "$DOCROOT" ] && [ -d "$DOCROOT" ] && [ -w "$DOCROOT" ]; then '
        f'  printf "%s" "<?php echo \\"SMPHPOK:\\".PHP_MAJOR_VERSION.\\".\\".PHP_MINOR_VERSION;" > "$PP"; '
        f'  PHP_OK=no; '
        f'  for i in 1 2 3 4 5 6; do '
        f'    R="$(curl -s --max-time 5 -H "Host: $DOM" "http://127.0.0.1/$PROBE" 2>/dev/null || true)"; '
        f'    case "$R" in *"SMPHPOK:$V"*) PHP_OK=yes; break ;; esac; sleep 2; done; '
        f'  rm -f "$PP"; '
        f'fi; '
        # Retried: reload returns before the workers have swapped, so an immediate request
        # can still be answered by the old configuration.
        f'OK=no; for i in 1 2 3 4 5 6; do '
        f'  B="$(curl -s --max-time 5 -H "Host: $DOM" http://127.0.0.1/ 2>/dev/null | head -c 400 || true)"; '
        f'  C="$(curl -s -o /dev/null -w "%{{http_code}}" --max-time 5 -H "Host: $DOM" http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'  case "$C" in 2*|3*) [ -n "$B" ] && OK=yes && break ;; esac; sleep 2; done; '
        f'[ "$PHP_OK" = no ] && OK=no; '
        f'if [ "$OK" != yes ]; then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null || true; '
        # Two different causes needing two different next steps: PHP not running at all is
        # usually a missing extension or a pool that will not start, while the site failing
        # is usually the application itself not being ready for that version.
        f'  if [ "$PHP_OK" = no ]; then '
        f'    echo "PHP $V did not run for $DOM, so it was put back."; exit 6; '
        f'  fi; '
        f'  echo "$DOM stopped working on PHP $V, so it was put back on the version it had."; '
        f'  exit 5; fi; '
        f'rm -f "$BK"; echo "$DOM is now running on PHP $V."'
    )


_OUTCOMES: dict[int, str] = {
    3: "That PHP version is not running on this server, so nothing was changed.",
    4: ("The web server refused the new configuration, so it was undone. Your other "
        "websites are unaffected."),
    5: ("The site stopped working on that version, so it was put back on the version it "
        "had. Nothing is broken — the application is most likely not ready for it yet."),
    6: ("PHP did not run for that site on the new version, so it was put back. That usually "
        "means an extension the site needs is missing from it."),
}


def explain_switch(code: int, output: str) -> tuple[bool, str]:
    """Turn the script's exit code into something an owner can act on.

    The message for every failure is OURS, not the script's last line. Echoing the output
    back seems friendlier until the script prints its success line and then fails on the
    step after — at which point the owner is told "your site is now on PHP 8.3" about a
    change that did not happen. The exit code is the fact; the output is only detail.
    """
    lines = [l for l in (output or "").strip().splitlines() if l.strip()]
    last = lines[-1].strip() if lines else ""
    if code == 0:
        return True, last or "The site was switched."
    base = _OUTCOMES.get(code, "The change could not be made.")
    # Include the server's own words only when they add something our sentence does not.
    detail = f" The server said: {last}" if last and last not in base else ""
    return False, f"{base}{detail}"
