"""Ally pre-mission Scout (proactivity Track B).

Before Ally offers a mission or asks the user about a FILE it needs to touch, it takes a
fast, read-only look at the servers involved — does the mentioned path exist? which
candidates match? what's a sensible destination folder? — so the FIRST thing Ally says
back is "I found /home/blog.serverally.org/public_html/index.php (12 KB). Where should it
go?" instead of a chain of "what's the full path?" questions the servers could answer.

This is the answer to "Ally should read both servers' File Managers": it surveys the
file layout of the servers named in the request, server-side, no matter what page the
user is on.

Safety & discipline (mirrors live_look_service):
- The probe is a FIXED read-only structure — never AI-chosen commands. Paths extracted
  from the user's message are shell-quoted before they touch the command. Strictly
  read-only (stat / ls / find -maxdepth), so — like the metrics / Live Look probes — it
  does not go through safety_service.
- SSH Linux servers only; WinRM/hosting are skipped.
- One SSH round trip per server, hard-timeout bounded; cached ~60s per (server, probe).
- Best-effort: any failure/timeout → that server contributes nothing, chat continues.
- Injected as DATA ("WHAT ALLY FOUND"), never as instructions (framing lives in ai_service).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import shlex
import time

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, str]] = {}  # cache-key -> (monotonic_ts, findings)
_TTL = 60.0
_TIMEOUT = 12.0
_MAX_CHARS = 2500
_MAX_SERVERS = 3          # current + up to this many named others
_MAX_PATHS = 4            # explicit absolute paths we stat per server
_MAX_NAMES = 3            # bare filenames we search for per server

# A request worth scouting: it involves FILES or FOLDERS, or moving data between servers.
# Deliberately narrow (per the product call) — cheap, and aimed squarely at the file /
# cross-server pain. Problem reports are Live Look's job, not the scout's.
_FILE_WORDS = re.compile(
    r"\b(file|files|folder|directory|move|moving|copy|copying|transfer|migrate|migrating|"
    r"backup|restore|upload|download|sync|index\.\w+|wp-config|\.env|\.sql|public_html|"
    r"/var/www|/home/|path)\b",
    re.I,
)

# An absolute POSIX path mentioned in the message (e.g. /home/site/public_html/index.php).
_ABS_PATH = re.compile(r"/[A-Za-z0-9._][A-Za-z0-9._/-]{2,}")
# Interesting bare filenames to hunt for in the common web roots when no full path was given.
_BARE_NAME = re.compile(r"\b([\w-]+\.(?:php|html?|sql|env|conf|ya?ml|json|zip|tar|gz|sql\.gz))\b", re.I)

# Common places sites/files live — surveyed so Ally can suggest a real destination folder.
_WEB_ROOTS_PROBE = (
    "echo '### WEB ROOTS'; "
    "ls -d /var/www/*/ /var/www/html /home/*/public_html /usr/local/lsws/*/html 2>/dev/null | head -20"
)


def should_scout(user_input: str, has_other_servers: bool) -> bool:
    """True when a read-only file look is worthwhile: the message is about files/folders,
    or it's a job that spans servers (which is always about moving data)."""
    text = user_input or ""
    if has_other_servers and _ABS_PATH.search(text):
        return True
    return bool(_FILE_WORDS.search(text))


def _extract_paths(user_input: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for m in _ABS_PATH.finditer(user_input or ""):
        p = m.group(0).rstrip(".,;:)")
        if p not in seen:
            seen.add(p)
            out.append(p)
        if len(out) >= _MAX_PATHS:
            break
    return out


def _extract_names(user_input: str, paths: list[str]) -> list[str]:
    """Bare filenames worth hunting for — but skip ones already covered by an explicit
    path (no point searching for index.php when /a/b/index.php was given)."""
    covered = " ".join(paths).lower()
    seen: set[str] = set()
    out: list[str] = []
    for m in _BARE_NAME.finditer(user_input or ""):
        name = m.group(1)
        low = name.lower()
        if low in covered or low in seen:
            continue
        seen.add(low)
        out.append(name)
        if len(out) >= _MAX_NAMES:
            break
    return out


def _build_probe(paths: list[str], names: list[str]) -> str:
    """A FIXED read-only probe. User-derived paths/names are shlex-quoted so they can
    only ever be arguments, never new commands."""
    parts: list[str] = []
    if paths:
        parts.append("echo '### PATHS YOU MENTIONED'")
        for p in paths:
            q = shlex.quote(p)
            # Report existence + size/type; if it's a directory, list a few entries.
            parts.append(
                f"if [ -e {q} ]; then "
                f"stat -c '%n — %s bytes, %F, modified %y' {q} 2>/dev/null; "
                f"[ -d {q} ] && ls -lah --time-style=+%Y-%m-%d {q} 2>/dev/null | head -12; "
                f"else echo {q}' — NOT FOUND'; fi"
            )
    if names:
        parts.append("echo '### MATCHES IN WEB ROOTS'")
        globs = "/var/www /home"
        for n in names:
            q = shlex.quote(n)
            parts.append(
                f"echo '-- '{q}; find {globs} -maxdepth 4 -name {q} "
                f"-printf '%p — %s bytes\\n' 2>/dev/null | head -8"
            )
    parts.append(_WEB_ROOTS_PROBE)
    return "\n".join(parts)


async def _look(server: Server, probe: str) -> str | None:
    """Run one read-only probe on one server; cached; best-effort (never raises)."""
    if server.connection_type != "ssh":
        return None
    key = f"{server.id}:{hashlib.sha1(probe.encode()).hexdigest()[:12]}"
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and now - cached[0] < _TTL:
        return cached[1]
    try:
        out, _err, _code = await asyncio.wait_for(
            connection_manager.execute(server, probe), timeout=_TIMEOUT
        )
    except Exception as exc:  # noqa: BLE001 — the scout must never break the chat
        logger.info("scout skipped for %s: %s", server.id, exc)
        return None
    text = (out or "").strip()
    if not text:
        return None
    _CACHE[key] = (now, text)
    return text


async def scout(server: Server, user_input: str, other_servers: list[Server] | None = None) -> str | None:
    """Read-only recon of the servers a file job touches: the current server plus any
    OTHER servers named in the message. Returns a data-framed findings block (server →
    what exists there), or None. SSH Linux only; best-effort; bounded.

    The probe surveys the same layout for every scouted server, so a cross-server move
    sees both the source file AND the destination's web roots in one pass — which is what
    lets Ally ask ONE good question instead of a chain."""
    paths = _extract_paths(user_input)
    names = _extract_names(user_input, paths)
    probe = _build_probe(paths, names)

    # The current server always; then any OTHER server the message names by exact name.
    targets: list[Server] = [server]
    lower = (user_input or "").lower()
    for s in other_servers or []:
        if str(s.id) == str(server.id):
            continue
        if s.name and s.name.lower() in lower:
            targets.append(s)
        if len(targets) >= _MAX_SERVERS:
            break

    blocks: list[str] = []
    for s in targets:
        found = await _look(s, probe)
        if found:
            blocks.append(f"On {s.name}:\n{found}")
    if not blocks:
        return None
    text = "\n\n".join(blocks)
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n…(truncated)"
    return text
