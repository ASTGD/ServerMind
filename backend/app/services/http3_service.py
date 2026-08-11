"""HTTP/3 for one site — Ploi's SSL → HTTP/3 (opens 443 UDP in the firewall).

HTTP/3 runs over QUIC, which is UDP. Three things follow from that, and each is a way this
goes wrong quietly rather than loudly.

**Most servers cannot do it at all.** nginx only speaks HTTP/3 when it was BUILT with
`--with-http_v3_module`, which arrived in 1.25 — and Ubuntu 24.04, the distribution our own
setup installs, ships 1.24. So the first thing this does is ask the binary, and a server that
cannot is told plainly rather than given a switch that writes a configuration nginx will then
refuse. A switch that breaks the web server is worse than a missing feature.

**`reuseport` may appear only ONCE per address and port in the whole configuration.** It is
required on one listener so the kernel can distribute UDP packets, and a second one anywhere
makes nginx refuse to start — which takes down every site on the machine, not this one. So
whether to write it is decided by looking at what is already there.

**The browser has to be told.** A visitor arrives over HTTP/2 and only tries HTTP/3 if the
response carries `Alt-Svc`. Without that header the listener is there, the port is open, and
not one visitor ever uses it — the feature looks enabled and does nothing.
"""
from __future__ import annotations

import logging
import re
import shlex

logger = logging.getLogger(__name__)

MARK_START = "# ServerAlly HTTP/3 start"
MARK_END = "# ServerAlly HTTP/3 end"


class Http3Error(Exception):
    """Something the customer can read and act on."""


def build_probe_command(config_path: str) -> str:
    """Can this server do HTTP/3 at all, and is `reuseport` already claimed?

    Read-only. Everything it reports is a fact about the machine rather than a belief we
    keep, because nginx can be replaced under us by an unattended upgrade.
    """
    cfg = shlex.quote(config_path)
    return f"""
set -u
if ! command -v nginx >/dev/null 2>&1; then echo "nginx=no"; exit 0; fi
echo "nginx=yes"
echo "version=$(nginx -v 2>&1 | sed -n 's/.*nginx\\///p')"
# The BUILD flags, not the version number: a distribution can ship 1.26 without the module,
# and the version alone would promise something the binary cannot do.
if nginx -V 2>&1 | grep -q -- '--with-http_v3_module'; then echo "quic=yes"; else echo "quic=no"; fi
# Anywhere in the configuration, not just this site: `reuseport` is once per address:port
# for the whole server, and a second one stops nginx starting.
if grep -rqs -- 'reuseport' /etc/nginx 2>/dev/null; then echo "reuseport=taken"; else echo "reuseport=free"; fi
if [ -f {cfg} ]; then
  grep -q -- '{MARK_START}' {cfg} && echo "on=yes" || echo "on=no"
  # HTTP/3 needs a certificate; QUIC has no unencrypted mode at all.
  grep -qE '^[[:space:]]*ssl_certificate[[:space:]]' {cfg} && echo "https=yes" || echo "https=no"
else
  echo "on=unknown"; echo "https=unknown"
fi
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q 'Status: active'; then
  ufw status 2>/dev/null | grep -q '443/udp' && echo "udp=open" || echo "udp=shut"
else
  echo "udp=unknown"
fi
""".strip()


def parse_probe(output: str) -> dict:
    """What the probe found, with nothing invented for what it could not see."""
    facts = {}
    for line in (output or "").splitlines():
        if "=" in line:
            key, _, value = line.strip().partition("=")
            facts[key] = value

    supported = facts.get("quic") == "yes"
    return {
        "supported": supported,
        "nginx": facts.get("nginx") == "yes",
        "version": facts.get("version") or None,
        "enabled": facts.get("on") == "yes",
        "https": facts.get("https") == "yes",
        # Only OUR site may claim reuseport if nothing else already has. If this site is the
        # one holding it, that does not count as taken.
        "reuseport_free": facts.get("reuseport") != "taken" or facts.get("on") == "yes",
        "udp_open": facts.get("udp") == "open",
        "why": _why(facts, supported),
    }


def _why(facts: dict, supported: bool) -> str | None:
    """Why it cannot be turned on, in words, or None when it can."""
    if facts.get("nginx") != "yes":
        return ("HTTP/3 is an nginx feature and nginx is not running here.")
    if not supported:
        version = facts.get("version") or "the version installed"
        return (f"This server's nginx ({version}) was not built with HTTP/3 support. It "
                f"arrived in nginx 1.25, and Ubuntu 24.04 still ships 1.24 — so this needs a "
                f"newer nginx from nginx.org's own repository before it can be switched on.")
    if facts.get("https") == "no":
        return ("HTTP/3 only exists over HTTPS — there is no unencrypted version of it. Turn "
                "HTTPS on for this site first.")
    return None


def build_apply_command(config_path: str, domain: str, *, on: bool,
                        with_reuseport: bool) -> str:
    """Add or remove the HTTP/3 listener, then prove the site still works.

    Same discipline as every other configuration write here: keep a copy, make nginx ACCEPT
    the new file before reloading, confirm the site still answers with real content, and put
    the copy back on any failure.
    """
    cfg = shlex.quote(config_path)
    host = shlex.quote(domain)
    reuse = " reuseport" if with_reuseport else ""

    block = (
        f"{MARK_START}\n"
        f"    listen 443 quic{reuse};\n"
        f"    listen [::]:443 quic{reuse};\n"
        f"    http3 on;\n"
        # Without this the listener exists and no browser ever tries it: a visitor arrives
        # over HTTP/2 and only upgrades when the response advertises it.
        f"    add_header Alt-Svc 'h3=\":443\"; ma=86400' always;\n"
        f"{MARK_END}"
    )
    import base64

    edit = _EDIT_ON if on else _EDIT_OFF
    arg = (f"{shlex.quote(base64.b64encode(block.encode()).decode())} "
           f"{shlex.quote(MARK_START)}") if on else ""

    return f"""
set -u
CFG={cfg}
BAK="$CFG.serverally-h3-$(date +%s)"
cp -p "$CFG" "$BAK" || {{ echo ">>> ERROR: could not back up the configuration"; exit 1; }}

WAS=$(curl -sk -o /dev/null -w '%{{http_code}}' --max-time 8 "https://{host}/" \\
      --resolve "{domain}:443:127.0.0.1" 2>/dev/null || echo 000)

python3 - "$CFG" {arg} <<'PYEOF' || {{ cp -p "$BAK" "$CFG"; rm -f "$BAK"; \\
  echo ">>> ERROR: the configuration could not be updated"; exit 1; }}
{edit}
PYEOF

if ! nginx -t >/tmp/sa_h3.log 2>&1; then
  cp -p "$BAK" "$CFG"; rm -f "$BAK"
  echo ">>> ERROR: nginx refused the new configuration; nothing was changed"
  sed -n '1,12p' /tmp/sa_h3.log
  exit 1
fi

{"# UDP, not TCP. Opening 443/tcp again would do nothing for QUIC." if on else ""}
{'if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then ufw allow 443/udp >/dev/null 2>&1 || true; fi' if on else ''}

(systemctl reload nginx 2>/dev/null || nginx -s reload) >/dev/null 2>&1 || true
sleep 1

BODY=$(curl -sk --max-time 12 --resolve "{domain}:443:127.0.0.1" "https://{host}/" | head -c 2000)
CODE=$(curl -sko /dev/null -w '%{{http_code}}' --max-time 12 --resolve "{domain}:443:127.0.0.1" "https://{host}/")
if [ -z "$BODY" ] || [ "$CODE" = "000" ] || [ "${{CODE#5}}" != "$CODE" ]; then
  case "$WAS" in 000|5*) rm -f "$BAK"; echo ">>> OK-BROKEN: $CODE"; exit 0 ;; esac
  cp -p "$BAK" "$CFG"; rm -f "$BAK"
  (systemctl reload nginx 2>/dev/null || nginx -s reload) >/dev/null 2>&1 || true
  echo ">>> ERROR: the site stopped serving after the change (HTTP $CODE), so it was put back"
  exit 1
fi

rm -f "$BAK"
echo ">>> OK: $CODE"
""".strip()


#: Written as plain scripts rather than f-strings: doubling every brace in a regex to smuggle
#: it through `.format()` is how the certificate installer acquired a bug I could not see by
#: reading it.
_EDIT_OFF = f'''
import re, sys

path = sys.argv[1]
text = open(path).read()
new = re.sub(r"[ \\t]*{re.escape(MARK_START)}.*?{re.escape(MARK_END)}\\n?", "", text,
             flags=re.S)
open(path, "w").write(new)
'''

_EDIT_ON = '''
import base64, re, sys

# The block arrives base64-encoded as an argument: it is multi-line and full of quotes, and
# building it into this script would mean escaping through two layers.
path, block, start = sys.argv[1], base64.b64decode(sys.argv[2]).decode(), sys.argv[3]
text = open(path).read()
if start in text:
    print("already on")
    raise SystemExit(0)

# Into the block that already serves HTTPS, not a new one: HTTP/3 is the same site over a
# different transport, and a second server block would need the root, the index and the PHP
# handler duplicated — with one of them eventually wrong.
out, depth, block_at, added_here, added = [], 0, None, False, 0
for line in text.splitlines():
    out.append(line)
    if block_at is None and re.match(r"^\\s*server\\s*\\{", line):
        block_at, added_here = depth, False
    if block_at is not None and not added_here:
        m = re.match(r"^([ \\t]*)listen\\s+(?:\\[::\\]:)?443\\b[^;]*ssl[^;]*;", line)
        if m:
            out.append(block)
            added_here, added = True, added + 1
    depth += line.count("{") - line.count("}")
    if block_at is not None and depth <= block_at:
        block_at = None

if not added:
    print("no https listener")
    raise SystemExit(1)
open(path, "w").write("\\n".join(out) + "\\n")
'''


def explain(code: int, output: str, *, on: bool) -> tuple[bool, str]:
    """What the customer reads. Ours, keyed off the markers."""
    text = output or ""
    verb = "on" if on else "off"
    if code == 0 and ">>> OK-BROKEN" in text:
        return True, (f"HTTP/3 is {verb}. The site itself was already not loading before "
                      f"this ran, so that is a separate problem to fix.")
    if code == 0:
        if on:
            return True, ("HTTP/3 is on. Browsers that support it will switch to it by "
                          "themselves on their second visit.")
        return True, "HTTP/3 is off. The site is unaffected."
    if "no https listener" in text:
        return False, ("This site's configuration has no HTTPS listener to add HTTP/3 to. "
                       "Turn HTTPS on first.")
    if "refused the new configuration" in text:
        return False, ("nginx refused the new configuration, so nothing was changed. The "
                       "most likely cause is another site already using `reuseport` on this "
                       "port.")
    if "stopped serving" in text:
        return False, ("The site stopped answering after the change, so the previous "
                       "configuration was put back.")
    return False, "That could not be changed, and nothing was altered."
