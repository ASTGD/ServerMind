"""Keep a site out of search engines — Ploi's "Block robots".

The case for it is one I hit on this project's own work: a demo site put on a temporary
address gets crawled, ranked, and then when the real domain arrives it inherits duplicate
content and the throwaway URL keeps showing up in results. The same is true of every
staging copy an agency makes.

**Done with a header, not a robots.txt file, and that difference is the whole point.**
`robots.txt` asks a crawler not to *fetch* a page; it does not stop a page being *indexed* —
Google will happily list a URL it was told not to fetch, using links from elsewhere, showing
"no information is available for this page". `X-Robots-Tag: noindex` is the instruction that
actually removes it. A file also lives inside the site, so a deploy or a clone overwrites it
and nobody notices; the header lives in the web-server config, above the application.

It is still only a request — a crawler chooses whether to honour it — so the wording says
so rather than promising privacy this cannot give. Anything that must not be seen needs a
password, which is a different switch on the same screen.
"""
from __future__ import annotations

import shlex

BEGIN = "# --- ServerAlly block robots (managed) ---"
END = "# --- end ServerAlly block robots ---"

#: `noindex` removes it from results; `nofollow` stops the crawler walking on into the rest
#: of the site from there. Both, because a staging copy links to itself everywhere.
VALUE = "noindex, nofollow, noarchive"


class RobotsError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def render_block(*, apache: bool) -> str:
    if apache:
        return (f"{BEGIN}\n"
                f'    Header always set X-Robots-Tag "{VALUE}"\n'
                f"{END}\n")
    # `always` matters: without it nginx only adds the header on 2xx and 3xx, so an error
    # page — exactly the sort of half-built page a staging site serves — would be indexable.
    return (f"{BEGIN}\n"
            f'    add_header X-Robots-Tag "{VALUE}" always;\n'
            f"{END}\n")


def build_command(config_path: str, domain: str, *, block: bool, apache: bool) -> str:
    """Add or remove the header, and undo it if the web server or the site objects.

    Same discipline as every other config edit here, for the same reason: a config that does
    not parse takes down every site on the machine, not just this one.
    """
    cfg, dom = shlex.quote(config_path), shlex.quote(domain)
    rule = render_block(apache=apache) if block else ""
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
        # Was it working before? Without this, a change made to a site that is already down
        # rolls back and blames itself — the same lesson the WordPress switches learned.
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
        f'systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null '
        f'  || systemctl reload httpd 2>/dev/null '
        f'  || nginx -s reload 2>/dev/null || apachectl graceful 2>/dev/null || true; '
        f'OK=no; B=/tmp/.sa_robots.$$; '
        f'for i in 1 2 3 4; do '
        f'  C="$(curl -s -o "$B" -w "%{{http_code}}" --max-time 6 -H "Host: $DOM" '
        f'      http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'  case "$C" in 3*) OK=yes ;; 2*) [ -s "$B" ] && OK=yes ;; esac; '
        f'  [ "$OK" = yes ] && break; sleep 2; done; rm -f "$B"; '
        f'if [ "$OK" != yes ] && [ "$WAS" = yes ]; then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  systemctl reload nginx 2>/dev/null || nginx -s reload 2>/dev/null || true; '
        f'  echo "The site stopped serving."; exit 5; fi; '
        f'rm -f "$BK"; '
        # Read the header back off a real request rather than trusting the write. This is
        # the only thing that proves the instruction actually reaches a crawler.
        f'HDR="$(curl -sI --max-time 6 -H "Host: $DOM" http://127.0.0.1/ 2>/dev/null '
        f'  | grep -i "^x-robots-tag:" | head -1 | tr -d "\\r")"; '
        f'echo "header=$HDR"; echo "applied"'
    )


def parse_result(output: str) -> bool:
    """Whether a crawler would actually see the instruction."""
    for line in (output or "").splitlines():
        if line.lower().startswith("header=x-robots-tag:"):
            return "noindex" in line.lower()
    return False


_OUTCOMES: dict[int, str] = {
    3: "This site's configuration file could not be found, so nothing changed.",
    4: ("The web server refused it, so it was undone. Your site and every other site on "
        "this server are unaffected."),
    5: "The site stopped serving with that in place, so it was removed again.",
}


def explain(code: int, output: str, *, block: bool) -> tuple[bool, str]:
    if code == 0:
        if not block:
            return True, "Search engines are allowed to index this site again."
        if parse_result(output):
            return True, ("Search engines are asked not to index this site — confirmed on a "
                          "real request. It is a request, not a lock: crawlers choose "
                          "whether to honour it, so anything that must not be seen needs a "
                          "password instead.")
        # The write succeeded and the header is not on the response. Saying "done" here is
        # how a staging site quietly gets indexed anyway.
        return False, ("The setting was saved, but the header did not appear on a real "
                       "request — so search engines would still index this site. Something "
                       "else in this site's configuration is likely removing it.")
    if code in _OUTCOMES:
        return False, _OUTCOMES[code]
    tail = (output or "").strip().splitlines()
    return False, (tail[-1] if tail else "That could not be changed.")
