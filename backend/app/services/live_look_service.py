"""Ally Live Look (Ally Context C1).

Before Ally plans an answer to a PROBLEM report, it takes a fast, read-only snapshot of
the server's state RIGHT NOW — services, disk, memory, load, top processes, a curl to
the site, and the last web-error-log lines. This turns "probably X, let's check" into
"I looked — PHP is stopped and the disk is 98% full. Here's the fix."

Safety & discipline:
- The probes are a FIXED whitelist string — never AI-chosen commands — and are strictly
  read-only (like the metrics/installed probes, they don't go through safety_service).
- SSH Linux servers only; WinRM/hosting are skipped.
- One SSH round trip, hard-timeout bounded; cached ~60s per server so repeat questions
  don't re-probe.
- Best-effort: any failure or timeout → no snapshot, chat continues normally.
- Injected as DATA ("LIVE SNAPSHOT"), never as instructions (framing lives in ai_service).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, str]] = {}  # server_id -> (monotonic_ts, snapshot)
_TTL = 60.0
_TIMEOUT = 12.0
_MAX_CHARS = 2800

# Problem-report signal. A matched diagnostic skill already forces a look (covering any
# language); this keyword net catches problem reports that didn't match a skill.
_PROBLEM_WORDS = re.compile(
    r"\b(down|slow|broken|not ?working|isn.?t working|won.?t|can.?t|cannot|crash|"
    r"crashed|error|errors|fail|failed|failing|stuck|frozen|hang|hung|500|502|503|"
    r"504|white ?screen|blank page|no response|unreachable|offline|not load|"
    r"timeout|timed out|problem|issue|wrong|help)\b",
    re.I,
)

# One combined, defensive, read-only bundle. Every probe is guarded so a missing tool or
# permission never fails the whole thing; the web probe is time-bounded.
_PROBE = r"""
echo '### SERVICES (relevant, active)'
systemctl list-units --type=service --state=active --no-legend --no-pager 2>/dev/null \
  | grep -Eio '[a-z0-9@._-]+\.service' | grep -Ei 'nginx|apache|httpd|lsws|lscpd|mysql|mariadb|postgres|php.*fpm|docker|redis' | head -12
echo '### SERVICES (failed)'
systemctl list-units --type=service --state=failed --no-legend --no-pager 2>/dev/null | grep -Eio '[a-z0-9@._-]+\.service' | head -8
echo '### DISK'
df -hP 2>/dev/null | awk 'NR>1 {print $6": "$5" used, "$4" free"}' | head -8
echo '### MEMORY'
free -m 2>/dev/null | awk '/^Mem:/{printf "RAM %s/%s MB used (%.0f%%)\n",$3,$2,($3/$2)*100} /^Swap:/{if($2+0>0)printf "Swap %s/%s MB used\n",$3,$2}'
echo '### LOAD / UPTIME'
uptime 2>/dev/null
echo '### TOP CPU'
ps -eo pcpu,pmem,comm --sort=-pcpu 2>/dev/null | head -4
echo '### WEB (from the server itself)'
curl -s -o /dev/null -w 'localhost -> HTTP %{http_code} in %{time_total}s\n' --max-time 5 http://127.0.0.1/ 2>/dev/null || echo 'localhost -> no local HTTP response'
echo '### RECENT WEB ERRORS'
for f in /var/log/nginx/error.log /var/log/apache2/error.log /var/log/httpd/error_log; do
  if [ -f "$f" ]; then echo "-- $f"; tail -4 "$f" 2>/dev/null; break; fi
done
""".strip()


def should_look(user_input: str, skill_matched: bool) -> bool:
    """True when a fresh look is worthwhile: a diagnostic skill matched, or the message
    reads like a problem report."""
    if skill_matched:
        return True
    return bool(_PROBLEM_WORDS.search(user_input or ""))


async def snapshot(server: Server) -> str | None:
    """A read-only 'what's happening right now' snapshot, or None. SSH Linux only;
    cached ~60s; best-effort (never raises)."""
    if server.connection_type != "ssh":
        return None
    now = time.monotonic()
    cached = _CACHE.get(str(server.id))
    if cached and now - cached[0] < _TTL:
        return cached[1]
    try:
        out, _err, _code = await asyncio.wait_for(
            connection_manager.execute(server, _PROBE), timeout=_TIMEOUT
        )
    except Exception as exc:  # noqa: BLE001 — Live Look must never break the chat
        logger.info("live look skipped for %s: %s", server.id, exc)
        return None
    text = (out or "").strip()
    if not text:
        return None
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n…(truncated)"
    _CACHE[str(server.id)] = (now, text)
    return text
