"""The long-running program behind a domain — Node, Next.js, Python, Go.

Ploi's equivalent is called "NodeJS" and reports five facts. Ours covers whatever our own
Web-application installer builds, which is runtime-agnostic by design: it writes a systemd
unit and points a reverse proxy at a port. So the section is called **Application** and the
probe NAMES the runtime it finds rather than assuming one.

**The point of this screen is that "the service is running" is not the same as "the site
works", and the three ways they come apart are invisible from anywhere else:**

* the unit is active but nothing is listening on the port — the program is up and its
  listener died, or it bound to the wrong interface. systemd is perfectly happy;
* the proxy forwards to a different port than the one the program was told to use. Every
  visitor gets 502 and both halves look fine on their own;
* the unit is "active" because systemd keeps restarting a program that keeps crashing.
  `Restart=always` turns a crash loop into something that reads as healthy between
  restarts, which is why the restart COUNT is reported rather than just the state.

Read-only. Starting and stopping are separate, named actions.
"""
from __future__ import annotations

import logging
import re
import shlex

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

_S = "___SM_WEBAPP___"

#: What the Web-application installer names the unit it writes. Kept here as the one place
#: that knows, so a change to the installer has exactly one other place to update — and a
#: test asserts the two still agree.
UNIT_PREFIX = "app-"

_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")

#: How a start command betrays its runtime. Ordered, because `npx next` is Node and
#: `gunicorn` is Python, and the first match wins.
_RUNTIMES: tuple[tuple[str, str], ...] = (
    (r"\bnode\b|\bnpm\b|\bpnpm\b|\byarn\b|\bnext\b|\bbun\b|\bdeno\b", "Node.js"),
    (r"\bpython3?\b|\bgunicorn\b|\buvicorn\b|\bhypercorn\b|\bflask\b", "Python"),
    (r"\bruby\b|\bpuma\b|\brails\b", "Ruby"),
    (r"\bjava\b|\.jar\b", "Java"),
    (r"\bdotnet\b", ".NET"),
)


class WebAppError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def unit_for(domain: str) -> str:
    """The unit this site's program runs in.

    The domain becomes a `systemctl` argument, so it is validated rather than escaped — the
    same rule the site guards follow, for the same reason.
    """
    d = (domain or "").strip().lower().rstrip(".")
    if not _DOMAIN.match(d) or ".." in d or len(d) > 200:
        raise WebAppError(f"'{domain}' is not a domain we can build a service name from.")
    return f"{UNIT_PREFIX}{d}"


def runtime_of(command: str) -> str:
    """What kind of program this is, read off the command it starts with."""
    cmd = command or ""
    for pattern, label in _RUNTIMES:
        if re.search(pattern, cmd, re.I):
            return label
    return "Program"


def build_probe_command(domain: str) -> str:
    """One read-only round trip. Nothing here starts, stops or writes anything."""
    unit = shlex.quote(unit_for(domain))
    dom = shlex.quote(domain)
    return f"""
U={unit}; D={dom}
if ! systemctl cat "$U" >/dev/null 2>&1; then echo "{_S}|error|nounit"; exit 0; fi
echo "{_S}|unit|$U"
echo "{_S}|active|$(systemctl is-active "$U" 2>/dev/null)"
echo "{_S}|enabled|$(systemctl is-enabled "$U" 2>/dev/null)"
for _p in NRestarts MainPID MemoryCurrent ActiveEnterTimestamp SubState Result; do
  echo "{_S}|$_p|$(systemctl show -p "$_p" --value "$U" 2>/dev/null)"
done
# What the unit was TOLD to do, read from the unit rather than guessed.
echo "{_S}|cmd|$(systemctl show -p ExecStart --value "$U" 2>/dev/null \
  | sed -E 's/.*path=([^ ]+).*argv\\[\\]=([^;]*).*/\\2/' | head -c 300)"
echo "{_S}|user|$(systemctl show -p User --value "$U" 2>/dev/null)"
echo "{_S}|dir|$(systemctl show -p WorkingDirectory --value "$U" 2>/dev/null)"
PORT="$(systemctl show -p Environment --value "$U" 2>/dev/null \
  | tr ' ' '\\n' | sed -n 's/^PORT=//p' | head -1)"
echo "{_S}|port|$PORT"
# Is anything actually LISTENING there? An active unit whose listener has died looks
# perfectly healthy to systemd and returns 502 to every visitor.
if [ -n "$PORT" ]; then
  if (ss -lntH 2>/dev/null || netstat -lnt 2>/dev/null) | grep -qE "[:.]$PORT[[:space:]]"; then
    echo "{_S}|listening|yes"; else echo "{_S}|listening|no"; fi
fi
# Where the web server actually forwards. If this disagrees with PORT above, both halves
# look fine on their own and the site is down.
echo "{_S}|proxy|$(grep -rhoE 'proxy_pass +https?://127.0.0.1:[0-9]+|ProxyPass +/ +https?://127.0.0.1:[0-9]+' \
  /etc/nginx /etc/apache2 /etc/httpd 2>/dev/null \
  | grep -F "$D" -m1 2>/dev/null || \
  grep -rhoE '127.0.0.1:[0-9]+' /etc/nginx/sites-available/"$D" \
    /etc/nginx/conf.d/"$D".conf /etc/apache2/sites-available/"$D".conf \
    /etc/httpd/conf.d/"$D".conf 2>/dev/null | head -1)"
# The last words of a program that will not stay up. Only fetched when it is not running,
# because on a healthy service this is noise.
if [ "$(systemctl is-active "$U" 2>/dev/null)" != active ]; then
  echo "{_S}|log|$(journalctl -u "$U" -n 12 --no-pager -o cat 2>/dev/null | tr '\\n' '~' | head -c 1200)"
fi
"""


def parse_probe(stdout: str) -> dict:
    """Turn the probe into the answer the screen shows."""
    fields: dict[str, str] = {}
    for line in (stdout or "").splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[0] == _S:
            fields[parts[1]] = parts[2]

    if fields.get("error") == "nounit":
        return {
            "ok": False,
            "reason": ("There is no ServerAlly-managed program for this site. It was either "
                       "not created here, or it is a plain website rather than an "
                       "application."),
        }

    port = (fields.get("port") or "").strip()
    proxy_raw = fields.get("proxy") or ""
    proxy_port = ""
    m = re.search(r"127\.0\.0\.1:(\d+)", proxy_raw)
    if m:
        proxy_port = m.group(1)

    active = fields.get("active", "") == "active"
    listening = fields.get("listening")
    cmd = (fields.get("cmd") or "").strip().strip("'\" ")
    try:
        restarts = int(fields.get("NRestarts") or 0)
    except ValueError:
        restarts = 0
    try:
        memory = int(fields.get("MemoryCurrent") or 0)
    except ValueError:
        memory = 0

    return {
        "ok": True,
        "unit": fields.get("unit", ""),
        "runtime": runtime_of(cmd),
        "command": cmd,
        "user": fields.get("user", ""),
        "directory": fields.get("dir", ""),
        "active": active,
        "state": fields.get("SubState") or fields.get("active", "unknown"),
        "enabled": (fields.get("enabled") or "").startswith("enabled"),
        "since": fields.get("ActiveEnterTimestamp", ""),
        "restarts": restarts,
        "memory_mb": round(memory / 1_048_576, 1) if memory > 0 else None,
        "pid": fields.get("MainPID", ""),
        "port": port,
        "listening": None if listening is None else listening == "yes",
        "proxy_port": proxy_port,
        "log": (fields.get("log") or "").replace("~", "\n").strip(),
        "problems": problems(active, port, listening, proxy_port, restarts,
                             (fields.get("enabled") or "").startswith("enabled"),
                             fields.get("SubState", "")),
    }


def problems(active: bool, port: str, listening: str | None, proxy_port: str,
             restarts: int, enabled: bool, sub_state: str = "") -> list[dict]:
    """What is actually wrong, in the order it matters.

    Pure, so every rule below is directly testable — and each one is a way a program can be
    "running" while the site is down, which is the whole reason this screen exists.
    """
    # Normalised rather than compared raw. The probe reports this as the STRING "yes"/"no",
    # and an earlier version tested `listening is False` — which a string is never equal to,
    # so the single most valuable rule here silently did nothing. Caught by its own test.
    listening_ok = (None if listening is None
                    else str(listening).strip().lower() in ("yes", "true", "1"))

    out: list[dict] = []
    if not active:
        out.append({
            "level": "critical",
            "text": "The program is not running, so the site cannot answer at all.",
        })
    # A crash loop reads as healthy between restarts. The count is the only thing that
    # gives it away without watching.
    # `auto-restart` is systemd saying, right now, "this died and I am starting it again".
    # It is checked alongside the count because the COUNT LAGS: caught against real systemd,
    # where a unit sitting in auto-restart still reported NRestarts=0, so a crash loop in
    # progress would have been reported as merely "not running".
    looping = sub_state == "auto-restart"
    if restarts >= 3 or looping:
        how_often = (f"It has restarted {restarts} times. " if restarts >= 3
                     else "It is being restarted right now. ")
        out.append({
            "level": "critical" if (not active or looping) else "warning",
            "text": (f"{how_often}That is a program crashing and being started again, not a "
                     f"program running — the log below is where the real error is."),
        })
    if active and listening_ok is False and port:
        out.append({
            "level": "critical",
            "text": (f"The program is running but nothing is listening on port {port}. "
                     f"Visitors get a 502. Either it never started its server, or it is "
                     f"listening on a different port than it was told to use."),
        })
    if port and proxy_port and port != proxy_port:
        out.append({
            "level": "critical",
            "text": (f"The web server forwards to port {proxy_port}, but the program was "
                     f"told to use port {port}. Both look correct on their own and every "
                     f"visitor gets a 502."),
        })
    if active and not enabled:
        out.append({
            "level": "warning",
            "text": "It is running now but will not start again after a reboot.",
        })
    return out


async def read(server: Server, domain: str) -> dict:
    """Everything the Application section shows. Never raises."""
    try:
        stdout, _stderr, _code = await connection_manager.execute(
            server, build_probe_command(domain))
    except WebAppError as exc:
        return {"ok": False, "reason": str(exc)}
    except Exception:  # noqa: BLE001 — a read must never take the page down
        logger.warning("web app probe failed on %s", server.host, exc_info=True)
        return {"ok": False, "reason": "We could not reach the server to look."}
    return parse_probe(stdout)


#: Deliberately only these three. Anything that edits the unit belongs to the daemons
#: screen, which already owns writing them and has the guards for it.
ACTIONS = ("start", "stop", "restart")


def build_action_command(action: str, domain: str) -> str:
    if action not in ACTIONS:
        raise WebAppError(f"'{action}' is not something we can do to this program.")
    unit = shlex.quote(unit_for(domain))
    # Verified afterwards rather than trusted: `systemctl start` returns before the program
    # has had time to fail, so an immediate exit code says nothing about whether it stayed.
    return (
        f'set -e; U={unit}; '
        f'systemctl {action} "$U" || true; '
        f'sleep 3; '
        f'echo "state=$(systemctl is-active "$U" 2>/dev/null)"; '
        f'echo "restarts=$(systemctl show -p NRestarts --value "$U" 2>/dev/null)"; '
        f'if [ "$(systemctl is-active "$U" 2>/dev/null)" != active ]; then '
        f'  journalctl -u "$U" -n 10 --no-pager -o cat 2>/dev/null | tail -6; fi'
    )


def explain_action(action: str, output: str) -> tuple[bool, str]:
    """What happened, judged by the state afterwards rather than by an exit code."""
    text = output or ""
    state = ""
    for line in text.splitlines():
        if line.startswith("state="):
            state = line[6:].strip()
    if action == "stop":
        if state and state != "active":
            return True, "Stopped. The site will not answer until it is started again."
        return False, "It is still running — the stop did not take effect."
    if state == "active":
        return True, ("Running. It was still up three seconds later, so it did not crash "
                      "on start.")
    tail = [ln for ln in text.splitlines()
            if ln and not ln.startswith(("state=", "restarts="))]
    detail = (" The last thing it said: " + tail[-1][:200]) if tail else ""
    return False, (f"It did not stay running.{detail}")


async def act(server: Server, domain: str, action: str) -> dict:
    """Start, stop or restart the program, and report what actually happened.

    The verdict comes from the state THREE SECONDS LATER, not from the exit code.
    `systemctl start` returns as soon as it has forked, so a program that dies on startup
    — a missing dependency, a port already taken, a syntax error — exits 0 here and would
    otherwise be reported as started. That is the failure this screen exists to catch, so
    it must not be the failure this screen creates.
    """
    try:
        stdout, stderr, _code = await connection_manager.execute(
            server, build_action_command(action, domain))
    except WebAppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise WebAppError(f"We could not reach the server: {exc}") from exc

    ok, message = explain_action(action, (stdout or "") + (stderr or ""))
    if not ok:
        raise WebAppError(message)
    return {"output": message}
