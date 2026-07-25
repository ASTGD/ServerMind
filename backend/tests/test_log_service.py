"""Server log viewer guarantees (docs/MARKET-RESEARCH-2026-07.md §8.2, Wave 1 #5).

The security property that matters: **the search box and the file path are user input that
ends up in a shell command.** They must never be able to become a command, and nothing here
may ever mutate the server — this is a *viewer*.
"""
from __future__ import annotations

import re

from app.services.log_service import (
    DEFAULT_LINES,
    MAX_LINES,
    build_discovery_command,
    build_read_command,
    line_severity,
    parse_discovery,
)

# Anything that changes the server has no business in a read-only viewer.
_MUTATORS = (
    r"\brm\b", r"\bmv\b", r"\bcp\b", r"\bdd\b", r"mkfs", r"\bchmod\b", r"\bchown\b",
    r"\btee\b", r"\btruncate\b", r"shred", r"\bkill\b", r"systemctl", r"\bapt\b",
    r"\byum\b", r"\bdnf\b", r"curl", r"wget", r"sed\s+-i", r"\beval\b", r">>",
    # A redirect that WRITES A FILE. `2>&1` and `2>/dev/null` are stderr plumbing, not writes.
    r">\s*(?!&|/dev/null)\S",
)


def _assert_read_only(cmd: str, what: str) -> None:
    for pattern in _MUTATORS:
        assert not re.search(pattern, cmd), f"{what} must not contain {pattern!r}: {cmd[:160]}"


def test_discovery_is_read_only():
    """Discovery runs a FIXED catalogue — never a user glob — and only looks."""
    cmd = build_discovery_command()
    _assert_read_only(cmd, "discovery")
    # It only tests for existence and stats size.
    assert "[ -f" in cmd and "stat -c%s" in cmd


def test_read_command_is_read_only():
    cmd = build_read_command("/var/log/nginx/error.log", 200, None)
    assert cmd.startswith("tail -n 200 ")
    _assert_read_only(cmd, "read")
    _assert_read_only(build_read_command("/var/log/syslog", 50, "boom"), "search read")


def test_search_cannot_escape_into_a_command():
    """A user typing shell metacharacters into the search box must stay a search term."""
    evil = "'; rm -rf / #"
    cmd = build_read_command("/var/log/syslog", 100, evil)
    # shlex.quote breaks the closing quote into '"'"' — the payload can never start a
    # new command. Verified by re-parsing the command the way a shell would.
    import shlex as _shlex
    tokens = _shlex.split(cmd.split("|")[0])
    assert evil in tokens, "the payload must survive as ONE argument, not become syntax"
    assert "rm" not in tokens, "the payload became a separate command"
    # grep -F means it is a fixed string, not a regex — no catastrophic backtracking either.
    assert "grep -F --" in cmd


def test_path_cannot_escape_into_a_command():
    import shlex as _shlex
    path = "/var/log/a b; rm -rf /tmp/x"
    tokens = _shlex.split(build_read_command(path, 50, None))
    assert path in tokens, "the path must survive as ONE argument"
    assert "rm" not in tokens, "the path became a separate command"


def test_search_uses_fixed_string_not_regex():
    """A regex-special search ('.*' or an unbalanced paren) must not blow up or match all."""
    cmd = build_read_command("/var/log/syslog", 10, ".*")
    assert "grep -F" in cmd


def test_line_count_is_clamped():
    assert f"tail -n {MAX_LINES} " in build_read_command("/x", 999_999, None), "no unbounded reads"
    assert "tail -n 1 " in build_read_command("/x", -5, None), "negative clamps to 1"
    # 0 / None mean "unspecified" and fall back to the default, not to 1.
    assert f"tail -n {DEFAULT_LINES} " in build_read_command("/x", 0, None)


def test_parse_discovery_reads_entries():
    out = parse_discovery(
        "___SM_LOG___|Nginx errors|web|/var/log/nginx/error.log|4096\n"
        "___SM_LOG___|System log|system|/var/log/syslog|123\n"
        "some unrelated noise\n"
    )
    assert len(out) == 2
    assert out[0] == {
        "path": "/var/log/nginx/error.log", "label": "Nginx errors",
        "category": "web", "size_bytes": 4096,
    }


def test_parse_discovery_dedupes_and_survives_junk():
    """The same file can match two globs; and a malformed line must not break the list."""
    out = parse_discovery(
        "___SM_LOG___|Nginx errors|web|/var/log/nginx/error.log|10\n"
        "___SM_LOG___|Site log|site|/var/log/nginx/error.log|10\n"
        "___SM_LOG___|broken line without enough fields\n"
        "___SM_LOG___|Bad size|system|/var/log/x|not-a-number\n"
    )
    paths = [e["path"] for e in out]
    assert paths.count("/var/log/nginx/error.log") == 1, "duplicate path"
    assert {"path": "/var/log/x", "label": "Bad size", "category": "system", "size_bytes": 0} in out


def test_parse_discovery_on_empty_output():
    assert parse_discovery("") == []
    assert parse_discovery(None) == []


def test_line_severity():
    assert line_severity("2026/07/25 [error] connect() failed") == "error"
    assert line_severity("PHP Fatal error: uncaught exception") == "error"
    assert line_severity("Permission denied") == "error"
    assert line_severity("[warn] deprecated directive") == "warn"
    assert line_severity('GET /index.php HTTP/1.1" 200') == "info"
    # 'error' inside a path must not be enough on its own to look like a failure line...
    assert line_severity("GET /assets/terror-movie.jpg 200") == "info", "word-boundary check"
