"""Server log viewer — find the logs, read the tail, search them.

Two jobs, and the first is the valuable one:

1. **Discovery.** A non-technical owner does not know that nginx errors live in
   ``/var/log/nginx/error.log`` and PHP's in ``/var/log/php8.2-fpm.log``. We probe a
   fixed catalogue of well-known locations (plus per-site logs under the web roots) and
   return only the ones that actually exist, labelled in plain language.
2. **Reading.** ``tail``/``grep`` over the existing SSH channel, capped.

**Every command here is read-only by construction** — a FIXED catalogue for discovery
(never a user-supplied glob), and only ``tail``/``grep``/``wc`` for reading, with the path
shell-quoted. Like the metrics, security and threat probes, this bundle is authored here
rather than chosen by the AI.
"""
from __future__ import annotations

import logging
import re
import shlex

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

MAX_LINES = 2000
DEFAULT_LINES = 200
_OUTPUT_CAP = 400_000  # ~400 KB of text is plenty for a tail; protects the browser too

# Known log locations, in plain language. `glob` is expanded on the server by `ls`.
# Order matters — the most useful logs first, because that is what we show by default.
_CATALOGUE: list[tuple[str, str, str]] = [
    # (glob, label, category)
    ("/var/log/nginx/error.log", "Nginx errors", "web"),
    ("/var/log/nginx/access.log", "Nginx access", "web"),
    ("/var/log/apache2/error.log", "Apache errors", "web"),
    ("/var/log/apache2/access.log", "Apache access", "web"),
    ("/var/log/httpd/error_log", "Apache errors", "web"),
    ("/var/log/httpd/access_log", "Apache access", "web"),
    ("/usr/local/lsws/logs/error.log", "OpenLiteSpeed errors", "web"),
    ("/usr/local/lsws/logs/access.log", "OpenLiteSpeed access", "web"),
    ("/var/log/php*-fpm.log", "PHP-FPM", "app"),
    ("/var/log/php-fpm/*.log", "PHP-FPM", "app"),
    ("/var/log/mysql/error.log", "MySQL errors", "database"),
    ("/var/log/mysqld.log", "MySQL errors", "database"),
    ("/var/log/mariadb/mariadb.log", "MariaDB errors", "database"),
    ("/var/log/postgresql/*.log", "PostgreSQL", "database"),
    ("/var/log/redis/redis-server.log", "Redis", "database"),
    ("/var/log/syslog", "System log", "system"),
    ("/var/log/messages", "System log", "system"),
    ("/var/log/auth.log", "Logins & sudo", "security"),
    ("/var/log/secure", "Logins & sudo", "security"),
    ("/var/log/fail2ban.log", "Fail2Ban", "security"),
    ("/var/log/mail.log", "Mail", "mail"),
    ("/var/log/cloud-init-output.log", "Cloud init", "system"),
]

# Per-site logs live under the account homes on panel-managed boxes.
_SITE_LOG_GLOBS = [
    "/home/*/logs/*.log",
    "/usr/local/lsws/logs/*.log",
    "/var/log/virtualmin/*log",
]

_SENTINEL = "___SM_LOG___"


def _q(value: str) -> str:
    return shlex.quote(value)


def build_discovery_command() -> str:
    """One round trip that lists every catalogue path that exists, with its size.

    Uses `ls -l` on each glob and ignores misses. Read-only by construction: the globs are
    ours, never user input.
    """
    parts = []
    for glob, label, category in _CATALOGUE:
        parts.append(
            f"for f in {glob}; do [ -f \"$f\" ] && "
            f"echo \"{_SENTINEL}|{label}|{category}|$f|$(stat -c%s \"$f\" 2>/dev/null || echo 0)\"; done 2>/dev/null"
        )
    for glob in _SITE_LOG_GLOBS:
        parts.append(
            f"for f in {glob}; do [ -f \"$f\" ] && "
            f"echo \"{_SENTINEL}|Site log|site|$f|$(stat -c%s \"$f\" 2>/dev/null || echo 0)\"; done 2>/dev/null"
        )
    return "; ".join(parts) + "; true"


def parse_discovery(stdout: str) -> list[dict]:
    """Parse the sentinel lines into log entries, newest-useful first, de-duplicated."""
    seen: set[str] = set()
    out: list[dict] = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith(_SENTINEL):
            continue
        try:
            _s, label, category, path, size = line.split("|", 4)
        except ValueError:
            continue
        if path in seen:
            continue
        seen.add(path)
        try:
            size_bytes = int(size)
        except ValueError:
            size_bytes = 0
        out.append({
            "path": path,
            "label": label,
            "category": category,
            "size_bytes": size_bytes,
        })
    return out


async def discover(server: Server) -> list[dict]:
    """Which logs exist on this server? Never raises — an unreachable server returns []."""
    try:
        stdout, _stderr, _code = await connection_manager.execute(server, build_discovery_command())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Log discovery failed for %s: %s", server.id, exc)
        return []
    return parse_discovery(stdout)


def build_read_command(path: str, lines: int, search: str | None) -> str:
    """Tail ``path`` (optionally filtered by a plain-text search).

    Read-only: ``tail`` and ``grep`` only. ``search`` is passed via ``grep -F`` (fixed
    string, not a regex) and shell-quoted, so a search box can never become a command or
    an accidental catastrophic regex.
    """
    n = max(1, min(int(lines or DEFAULT_LINES), MAX_LINES))
    if search:
        # Filter first, then take the last n matches — what a user expects from a search.
        return f"grep -F -- {_q(search)} {_q(path)} 2>&1 | tail -n {n}"
    return f"tail -n {n} {_q(path)} 2>&1"


async def read(server: Server, path: str, lines: int = DEFAULT_LINES, search: str | None = None) -> dict:
    """Read the tail of a log. Returns ``{content, truncated, line_count}``."""
    cmd = build_read_command(path, lines, search)
    stdout, stderr, code = await connection_manager.execute(server, cmd)
    text = stdout or ""
    if code != 0 and not text.strip():
        text = (stderr or "").strip() or "Could not read this log file."
    truncated = len(text) > _OUTPUT_CAP
    if truncated:
        text = text[-_OUTPUT_CAP:]
    return {
        "content": text,
        "truncated": truncated,
        "line_count": text.count("\n") + (1 if text and not text.endswith("\n") else 0),
    }


# ── Severity hinting (pure, for the UI) ──────────────────────────────────────
# Log viewers are much more useful when the eye can find the problem. These are
# deliberately conservative substring/word checks — no attempt at parsing every format.

_ERROR_RE = re.compile(r"\b(error|fatal|critical|emerg|alert|panic|denied|failed|failure|exception)\b", re.I)
_WARN_RE = re.compile(r"\b(warn|warning|deprecated|notice)\b", re.I)


def line_severity(line: str) -> str:
    """'error' | 'warn' | 'info' for one log line."""
    if _ERROR_RE.search(line):
        return "error"
    if _WARN_RE.search(line):
        return "warn"
    return "info"


# --- One site's logs ----------------------------------------------------------------------
#
# The server-wide list answers "what is happening on this machine". On a machine with
# fifteen sites that is the wrong question — the one anyone actually asks is "what about
# THIS one", and until now there was no way to ask it.
#
# Our own installers name their log files after the domain, which is what makes this
# possible without guessing. An app's own log is found from the site's folder.

def build_site_log_command(domain: str, doc_root: str | None) -> str:
    """Which log files belong to this one site. One round trip, read-only.

    The domain is quoted rather than escaped, and the paths are ours — a customer's domain
    never becomes part of a command's structure.
    """
    d = shlex.quote(domain)
    parts = [
        # Written by every site our installers create, named after the domain.
        f'for f in /var/log/nginx/{{{d},{d}-error,{d}-access}}.log '
        f'/var/log/apache2/{d}-*.log /var/log/httpd/{d}-*.log; do '
        f'[ -f "$f" ] && echo "{_SENTINEL}|Web server|site|$f|'
        f'$(stat -c%s "$f" 2>/dev/null || echo 0)"; done 2>/dev/null'
    ]
    if doc_root:
        # The application's own log, which is where a 500 explains itself. Laravel writes
        # here; so do most PHP frameworks.
        site_dir = shlex.quote(doc_root.rstrip("/").removesuffix("/public"))
        parts.append(
            f'for f in {site_dir}/storage/logs/*.log {site_dir}/logs/*.log '
            f'{site_dir}/wp-content/debug.log; do '
            f'[ -f "$f" ] && echo "{_SENTINEL}|Application|site|$f|'
            f'$(stat -c%s "$f" 2>/dev/null || echo 0)"; done 2>/dev/null'
        )
    return "; ".join(parts) + "; true"


async def discover_for_site(server: Server, domain: str, doc_root: str | None) -> list[dict]:
    """This site's own log files. Never raises — an unreachable server returns nothing."""
    try:
        stdout, _stderr, _code = await connection_manager.execute(
            server, build_site_log_command(domain, doc_root))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Site log discovery failed for %s: %s", domain, exc)
        return []
    return parse_discovery(stdout)
