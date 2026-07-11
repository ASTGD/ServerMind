"""Pre-mission Scout (proactivity Track B) — deterministic guards.

The scout runs a FIXED read-only probe before Ally plans a file / cross-server job.
These tests pin: when it fires, what it extracts, and — SECURITY-CRITICAL — that the
probe it builds is read-only and shell-safe no matter what the user typed.
"""
from __future__ import annotations

import re

from app.services import scout_service as sc


# ── should_scout: fires on file / cross-server jobs, quiet otherwise ───────────

def test_scout_fires_on_file_move():
    assert sc.should_scout("move index.php to my other server", has_other_servers=True)


def test_scout_fires_on_a_path_mention():
    assert sc.should_scout("copy /var/www/html/index.php somewhere", has_other_servers=False)


def test_scout_quiet_on_a_plain_problem_report():
    # Live Look's job, not the scout's — don't SFTP-probe a "why is it slow?".
    assert not sc.should_scout("why is my server so slow today?", has_other_servers=True)


def test_scout_quiet_on_a_service_restart():
    assert not sc.should_scout("restart nginx please", has_other_servers=True)


# ── extraction ────────────────────────────────────────────────────────────────

def test_extracts_absolute_paths():
    paths = sc._extract_paths("move /home/blog.serverally.org/public_html/index.php to TS3")
    assert "/home/blog.serverally.org/public_html/index.php" in paths


def test_extracts_bare_filenames_not_already_in_a_path():
    # index.php is covered by the explicit path → not re-searched; wp-config.php is new.
    paths = ["/var/www/site/index.php"]
    names = sc._extract_names("grab index.php and wp-config.php", paths)
    assert "wp-config.php" in names
    assert "index.php" not in names


def test_extraction_is_capped():
    msg = " ".join(f"/a/b/file{i}.txt" for i in range(20))
    assert len(sc._extract_paths(msg)) <= sc._MAX_PATHS


# ── the probe is read-only and injection-safe (SECURITY-CRITICAL) ─────────────

# Any verb that could CHANGE the server. A scout probe must contain none of them —
# it only ever observes (stat / ls / find / echo).
_MUTATORS = re.compile(
    r"\b(rm|mv|cp|dd|mkfs|chmod|chown|chattr|tee|truncate|shred|"
    r"install|apt|yum|dnf|systemctl|service|kill|reboot|shutdown|"
    r"mysql|psql|drop|delete|update|insert|write|touch|mkdir|rmdir|"
    r"curl|wget|nc|bash|sh|eval|export)\b",
    re.I,
)


def test_probe_is_read_only():
    probe = sc._build_probe(["/etc/passwd", "/var/www"], ["index.php"])
    # Strip the read-only verbs we DO expect, then assert nothing mutating remains.
    cleaned = re.sub(r"\b(stat|ls|find|echo|head|printf)\b", "", probe)
    hit = _MUTATORS.search(cleaned)
    assert hit is None, f"scout probe contains a mutating verb: {hit.group(0)!r}\n{probe}"


def test_probe_shell_quotes_user_paths():
    """A path with shell metacharacters must be quoted so it can only ever be an
    argument — never break out into a new command."""
    evil = "/tmp/x; rm -rf /"
    probe = sc._build_probe([evil], [])
    # The dangerous string appears ONLY inside a single-quoted shell token.
    assert "'/tmp/x; rm -rf /'" in probe
    # Strip every single-quoted span (the safe, inert arguments); the dangerous verb
    # must not survive OUTSIDE quotes as a runnable command.
    outside_quotes = re.sub(r"'[^']*'", "", probe)
    assert "rm -rf" not in outside_quotes


def test_probe_quotes_malicious_filename():
    probe = sc._build_probe([], ["$(reboot)"])
    assert "'$(reboot)'" in probe
