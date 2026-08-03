"""Take a site offline on purpose, with a page explaining why — Ploi's "Suspend site".

Their pitch for it is blunt and correct: *"useful when your customer is late on paying the
bills."* An agency needs a lever that is not "delete their website".

**The response code is the whole design.** Ploi offers 200 as a choice; we default to 503
and warn about the rest, because the code is not cosmetic — it is what search engines are
told:

* **503** — "temporarily unavailable, come back". Rankings are held. This is the only
  correct answer for a billing dispute that will be settled in a week.
* **200** — "this IS the page now". A client's pages get replaced in the index by a
  suspension notice, and that damage outlives the dispute by months.
* **410** — "gone for good", which is worse than 404 and is a deliberate request to be
  forgotten.

The page itself is written as a file and served with that status, so nothing about the
site's own application has to run — a suspended site should not need PHP, a database, or
anything else that might itself be broken.
"""
from __future__ import annotations

import base64
import html
import json as _json
import re
import shlex

SUSPEND_DIR = "/var/www/serverally-suspended"

BEGIN = "# --- ServerAlly suspended (managed) ---"
END = "# --- end ServerAlly suspended ---"

# Ploi's list. 200 is kept because refusing to offer it would be paternalistic — an agency
# may have a reason — but it is not the default and it says what it costs.
CODES: tuple[dict, ...] = (
    {"value": 503, "label": "503 — Temporarily unavailable",
     "note": "Recommended. Search engines hold the site's rankings and come back later."},
    {"value": 403, "label": "403 — Forbidden", "note": "Access refused, no explanation."},
    {"value": 404, "label": "404 — Not found",
     "note": "Search engines will start dropping the pages."},
    {"value": 410, "label": "410 — Gone",
     "note": "Tells search engines to forget the pages permanently. Hard to undo."},
    {"value": 451, "label": "451 — Unavailable for legal reasons", "note": "For takedowns."},
    {"value": 200, "label": "200 — OK",
     "note": "Not recommended: search engines replace the real pages with this notice."},
)
DEFAULT_CODE = 503


class SuspendError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def check_code(code: int) -> int:
    if code not in {c["value"] for c in CODES}:
        raise SuspendError("That is not a response code we can send.")
    return code


def render_markdown(text: str) -> str:
    """The small part of Markdown Ploi's field actually gets used for.

    Deliberately not a Markdown library. This text is written by one customer and shown to
    another customer's visitors, so the safe move is to escape EVERYTHING first and then
    re-introduce four constructs by hand — rather than trust a parser not to let an
    `<img onerror=...>` through onto a page an agency puts its own name on.
    """
    safe = html.escape((text or "").strip())
    if not safe:
        return ""
    out = []
    for para in re.split(r"\n\s*\n", safe):
        lines = [ln.strip() for ln in para.splitlines() if ln.strip()]
        if lines and all(ln.startswith(("- ", "* ")) for ln in lines):
            items = "".join(f"<li>{_inline(ln[2:])}</li>" for ln in lines)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append("<p>" + _inline("<br>".join(lines)) + "</p>")
    return "\n".join(out)


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", text)
    # Only http(s). A `javascript:` link on somebody else's visitors is not ours to allow.
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                  r'<a href="\2" rel="noopener noreferrer">\1</a>', text)
    return text


def render_page(domain: str, message: str, reason: str) -> str:
    """The page a visitor sees. Self-contained: no fonts, no scripts, nothing to fetch."""
    title = html.escape((message or "").strip() or "Website is suspended")
    body = render_markdown(reason)
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title>
<style>
  body {{ margin:0; min-height:100vh; display:flex; align-items:center;
         justify-content:center; background:#f6f7f9; color:#1f2430;
         font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  main {{ max-width:34rem; padding:2.5rem; background:#fff; border-radius:14px;
          box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  h1 {{ margin:0 0 .75rem; font-size:1.35rem; }}
  p, li {{ color:#4a5262; }}
  .who {{ margin-top:1.5rem; font-size:.85rem; color:#8a91a0; }}
</style>
</head><body><main>
<h1>{title}</h1>
{body}
<p class="who">{html.escape(domain)}</p>
</main></body></html>
"""


def build_state_command(domain: str) -> str:
    """Read back what this site was suspended WITH, so the form can be edited rather than
    retyped. A sidecar file rather than a database column: the truth about a suspension
    already lives on the server, and one place is better than two that can disagree."""
    f = shlex.quote(f"{SUSPEND_DIR}/{domain}.json")
    return f'if [ -f {f} ]; then base64 < {f}; fi'


def build_apply_command(config_path: str, domain: str, *, suspended: bool,
                        message: str = "", reason: str = "", code: int = DEFAULT_CODE,
                        apache: bool) -> str:
    """Suspend or restore, and undo it if the web server or the site objects.

    Restoring runs the same command with an empty block, so there is no separate "unsuspend"
    path that could get out of step with the one that suspends.
    """
    page = render_page(domain, message, reason) if suspended else ""
    encoded = base64.b64encode(page.encode()).decode()
    cfg, dom = shlex.quote(config_path), shlex.quote(domain)
    page_file = f"{SUSPEND_DIR}/{domain}.html"
    state_file = f"{SUSPEND_DIR}/{domain}.json"
    state = (_json.dumps({"message": message, "reason": reason, "code": code})
             if suspended else "")
    state_b64 = base64.b64encode(state.encode()).decode()
    anchor = "ServerName" if apache else "server_name"

    if not suspended:
        block = ""
    elif apache:
        block = (f"{BEGIN}\n"
                 f"    ErrorDocument {code} /__serverally_suspended.html\n"
                 f'    Alias /__serverally_suspended.html "{page_file}"\n'
                 f"    <Location />\n"
                 f"        Redirect {code} /\n"
                 f"    </Location>\n"
                 f"{END}\n")
    else:
        # A regex location matching everything, placed BEFORE the site's own regex
        # locations — nginx tries regex locations in the order they appear, so this one
        # wins for every request including .php.
        #
        # The page itself is an EXACT location, which outranks every regex, so the internal
        # redirect to it cannot come back round to the suspend rule and loop.
        block = (
            f"{BEGIN}\n"
            # `error_page X = /page` (with the `=`) takes the status of the page it serves,
            # which is how 200 is done — `return 200` would send an empty body and no
            # notice, and `alias` is not allowed in a regex location at all.
            f"    error_page 418 = /__serverally_suspended.html;\n"
            if code == 200 else
            f"{BEGIN}\n"
            f"    error_page {code} /__serverally_suspended.html;\n"
        ) + (
            # An EXACT location, so `alias` is legal and so the internal redirect outranks
            # the catch-all below and cannot loop back into it.
            f"    location = /__serverally_suspended.html {{\n"
            f"        internal;\n"
            # `alias`, never `root`. A second `root` in this file makes it ambiguous which
            # folder the config serves — and the resolver that finds a site's config reads
            # exactly that. Adding one meant a suspended site could no longer be FOUND, so
            # it could not be un-suspended: a one-way door on the one feature whose promise
            # is that putting it back is one click. Found by pressing the button.
            f"        alias {SUSPEND_DIR}/{domain}.html;\n"
            f"        default_type text/html;\n"
            f"        add_header Cache-Control \"no-store\" always;\n"
            f"    }}\n"
            # A regex matching everything, placed BEFORE the site's own regex locations —
            # nginx tries them in order, so this wins for every request including .php.
            f"    location ~ ^/ {{\n"
            f"        return {418 if code == 200 else code};\n"
            f"    }}\n"
            f"{END}\n"
        )

    awk = (
        'BEGIN { while ((getline l < B) > 0) blk[++n] = l } '
        '$0 == BEGINM { skip = 1 } '
        'skip { if ($0 == ENDM) skip = 0; next } '
        '{ print } '
        f'/^[ \\t]*({anchor})[ \\t]/ {{ for (i = 1; i <= n; i++) print blk[i] }}'
    )

    # A suspended site answers with the code that was CHOSEN, so the usual "is it 2xx"
    # check would call a working suspension a failure. What is checked instead is that it
    # answers at all — a suspension that takes the server down is still a broken server.
    return (
        f'set -e; '
        f'CFG={cfg}; DOM={dom}; '
        f'[ -f "$CFG" ] || {{ echo "This site\'s configuration file is not there."; exit 3; }}; '
        f'mkdir -p {shlex.quote(SUSPEND_DIR)}; '
        f'printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(page_file)}; '
        f'[ -s {shlex.quote(page_file)} ] || rm -f {shlex.quote(page_file)}; '
        f'printf %s {shlex.quote(state_b64)} | base64 -d > {shlex.quote(state_file)}; '
        f'[ -s {shlex.quote(state_file)} ] || rm -f {shlex.quote(state_file)}; '
        f'BK="$CFG.serverally.$(date +%s).bak"; cp -p "$CFG" "$BK"; '
        f'BLKF="$CFG.serverally.block.tmp"; NEW="$CFG.serverally.new.tmp"; '
        f'printf %s {shlex.quote(base64.b64encode(block.encode()).decode())} '
        f'  | base64 -d > "$BLKF"; '
        f'awk -v B="$BLKF" -v BEGINM={shlex.quote(BEGIN)} -v ENDM={shlex.quote(END)} '
        f'  {shlex.quote(awk)} "$CFG" > "$NEW"; '
        f'cat "$NEW" > "$CFG"; rm -f "$NEW" "$BLKF"; '
        f'if ! (nginx -t 2>/dev/null || apachectl configtest 2>/dev/null); then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  echo "The web server refused it."; exit 4; fi; '
        f'systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null '
        f'  || systemctl reload httpd 2>/dev/null || true; '
        f'OK=no; for i in 1 2 3 4; do '
        f'  C="$(curl -s -o /dev/null -w "%{{http_code}}" --max-time 5 '
        f'      -H "Host: $DOM" http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'  [ "$C" != 000 ] && {{ OK=yes; break; }}; sleep 2; done; '
        f'if [ "$OK" != yes ]; then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null || true; '
        f'  echo "The site stopped answering at all."; exit 5; fi; '
        f'rm -f "$BK"; echo "applied"'
    )


_OUTCOMES: dict[int, str] = {
    3: "This site's configuration file could not be found on the server, so nothing changed.",
    4: ("The web server refused it, so it was undone. Your site and every other site on "
        "this server are unaffected."),
    5: ("The site stopped answering altogether, so it was put back the way it was. Nothing "
        "is left changed."),
}


def explain(code: int, output: str, *, suspended: bool, status: int) -> tuple[bool, str]:
    if code == 0:
        if not suspended:
            return True, "The site is live again."
        extra = ("" if status == 503 else
                 " Note that this code is not the one search engines handle best — 503 is.")
        return True, (f"Suspended. Visitors now see your notice, and the site answers with "
                      f"{status}.{extra}")
    if code in _OUTCOMES:
        return False, _OUTCOMES[code]
    tail = (output or "").strip().splitlines()
    return False, (tail[-1] if tail else "That could not be changed.")
