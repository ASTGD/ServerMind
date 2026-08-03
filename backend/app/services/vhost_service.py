"""The web-server configuration for one website, edited by hand.

Ploi calls it "NGINX configuration". It is the escape hatch: everything else on the Manage
screen writes a specific line for you, and this is for the case nobody anticipated.

**It is also the single most dangerous edit in the product.** A vhost that does not parse
does not take one website down — the reload fails and EVERY site on that machine keeps
serving the old config, or worse, a partial reload leaves the box inconsistent. So the same
discipline `redirect_service` proved is not optional here, it is the whole feature:

1. keep a copy before touching anything;
2. **test the configuration before reloading**, and put the copy back if it fails;
3. after the reload, check the site still answers — a file can parse and still be wrong;
4. every failure message is OURS, keyed off an exit code, never the script's last line.

The content arrives base64-encoded. A configuration file is arbitrary text with quotes,
backslashes, dollar signs and newlines in it by nature, so there is no quoting scheme worth
arguing about — encode it and let no shell see it.
"""
from __future__ import annotations

import base64
import shlex

MAX_BYTES = 256 * 1024


class VhostError(Exception):
    """Something the owner can read and act on."""


def check_content(content: str) -> str:
    """Refuse what cannot be a web-server configuration before it reaches the machine."""
    if content is None:
        raise VhostError("There is nothing to save.")
    if not content.strip():
        raise VhostError(
            "The configuration is empty. Saving that would take the site off this server — "
            "if that is what you want, remove the site instead.")
    if len(content.encode()) > MAX_BYTES:
        raise VhostError("That configuration is too large to save from here.")
    if "\x00" in content:
        raise VhostError("That does not look like a configuration file.")
    return content


def build_read_command(config_path: str) -> str:
    """Read one config file, base64 so no byte of it can be mangled on the way back."""
    return (f'set -e; CFG={shlex.quote(config_path)}; '
            f'[ -f "$CFG" ] || {{ echo "MISSING"; exit 3; }}; '
            f'base64 < "$CFG" | tr -d "\\n"')


def build_save_command(config_path: str, domain: str, content: str) -> str:
    """Write it, prove the web server accepts it, and undo it if anything goes wrong."""
    encoded = base64.b64encode(check_content(content).encode()).decode()
    cfg = shlex.quote(config_path)
    dom = shlex.quote(domain)
    return (
        f'set -e; '
        f'CFG={cfg}; DOM={dom}; '
        f'[ -f "$CFG" ] || {{ echo "This site\'s configuration file is not there."; exit 3; }}; '
        f'BK="$CFG.serverally.$(date +%s).bak"; cp -p "$CFG" "$BK"; '
        # Written through a temp file beside it, then copied back, so the live file is never
        # half-written even for the instant it takes — and it keeps its owner and mode.
        f'TMP="$CFG.serverally.new.tmp"; '
        f'printf %s {shlex.quote(encoded)} | base64 -d > "$TMP"; '
        f'cat "$TMP" > "$CFG"; rm -f "$TMP"; '
        f'if ! (nginx -t 2>/dev/null || apachectl configtest 2>/dev/null); then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  echo "The web server rejected it."; exit 4; fi; '
        f'systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null '
        f'  || systemctl reload httpd 2>/dev/null || true; '
        # Parsing is not serving. A config can be valid and still point the site at a folder
        # that is not there, so the site is asked whether it still answers at all.
        f'OK=no; for i in 1 2 3 4; do '
        f'  C="$(curl -s -o /dev/null -w "%{{http_code}}" --max-time 5 '
        f'      -H "Host: $DOM" http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'  case "$C" in 2*|3*|401|403|404) OK=yes; break ;; esac; sleep 2; done; '
        f'if [ "$OK" != yes ]; then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  systemctl reload nginx 2>/dev/null || systemctl reload apache2 2>/dev/null || true; '
        f'  echo "The site stopped answering."; exit 5; fi; '
        f'rm -f "$BK"; echo "saved"'
    )


_OUTCOMES: dict[int, str] = {
    3: "This site's configuration file could not be found on the server, so nothing changed.",
    4: ("The web server refused that configuration, so your old one was put back. Every "
        "site on this server is still running — check the syntax and try again."),
    5: ("The configuration was accepted but the site stopped answering, so your old one "
        "was put back. Check the paths in it — a folder or socket it points at may not "
        "exist."),
}


def explain(code: int, output: str) -> tuple[bool, str]:
    """Our sentence for every failure, keyed off the exit code rather than the last line.

    A script that prints its success line and then fails on the step after would otherwise
    tell the owner their configuration is live when it was rolled back.
    """
    if code == 0:
        return True, "Saved. The web server accepted it and the site still answers."
    base = _OUTCOMES.get(code, "The configuration could not be saved.")
    last = next((l.strip() for l in reversed((output or "").splitlines()) if l.strip()), "")
    detail = f" The server said: {last}" if last and last not in base else ""
    return False, f"{base}{detail}"
