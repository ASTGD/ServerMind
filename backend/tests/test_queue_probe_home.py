"""The queue screen read an error message and presented it as configuration.

Found by walking every per-site screen on a real Laravel site. The queue screen returned:

    "default": "Writing to directory /var/www/.config/psysh is not allowed."
    "connections": []

`artisan tinker` is psysh, and psysh writes a config directory under `$HOME`. Running as the
site's own account that is `/var/www`, which it cannot write — so psysh prints its warning
**on stdout**, where the `2>/dev/null` on that command cannot catch it, and the sentence was
captured as the answer.

**Why it mattered more than a wrong label.** `retry_after` comes from the same read. Laravel
puts a job back on the queue after `retry_after` seconds, and a worker allowed to run longer
gets its job handed to a second worker while the first is still running — the customer is
charged twice, and nothing reports an error. `check_timeout` correctly skips when
`retry_after` is unknown (refusing a worker on a site we cannot read would be worse). But the
probe never worked, so it was ALWAYS unknown: the guard was inert on every Laravel site.

Two fixes: give tinker a writable HOME, and stop an unreadable value becoming data.
"""
from __future__ import annotations

import re

import pytest

from app.services import queue_worker_service as qw

#: Verbatim from the live server.
PSYSH_WARNING = ("  <warning> User Notice </warning> Writing to directory "
                 "/var/www/.config/psysh is not allowed.")

#: Verbatim from the same server once HOME was writable.
REAL_CONNECTIONS = ('{"sync":{"driver":"sync","retry_after":null},'
                    '"database":{"driver":"database","retry_after":90},'
                    '"redis":{"driver":"redis","retry_after":90}}')


def probe_output(default: str, connections: str) -> str:
    """The booted app answers both questions in one JSON blob."""
    s = qw._S                                                   # noqa: SLF001
    if connections in ("", None) or not connections.strip().startswith("{"):
        blob = connections if connections else '{"default": "%s", "connections": {}}' % default
    else:
        blob = '{"default": "%s", "connections": %s}' % (default, connections)
    return f"{s}|php|/usr/bin/php8.3\n{s}|path|/var/www/app\n{s}|queue|{blob}"


def script() -> str:
    return qw.build_probe_command("/var/www/app/public")


def code(text: str) -> str:
    """Executable lines only."""
    return "\n".join(ln for ln in text.splitlines()
                     if not ln.strip().startswith("#"))


# ── the read itself ──────────────────────────────────────────────────────────

def test_it_does_not_use_tinker_at_all():
    """tinker IS psysh, and psysh needs a writable $HOME it does not have here. Booting the
    application directly needs none, and writes nothing."""
    body = code(script())
    assert "tinker" not in body


def test_it_boots_the_application_so_env_applies():
    """`retry_after` is usually `env('QUEUE_RETRY_AFTER', 90)`, so reading config/queue.php
    would give the DEFAULT and be wrong exactly where it matters."""
    body = code(script())
    assert 'require "vendor/autoload.php"' in body
    assert 'require "bootstrap/app.php"' in body
    assert "->bootstrap()" in body


def test_it_asks_for_both_answers_in_one_read():
    body = code(script())
    assert 'config("queue.default")' in body
    assert 'config("queue.connections")' in body
    assert body.count("$RUNAS \"$PHP_BIN\" -r") == 1


def test_it_runs_inside_the_application_folder():
    """`require "vendor/autoload.php"` is relative — run from anywhere else it finds
    nothing and the read silently returns empty."""
    body = code(script())
    assert 'cd "$APP_PATH"' in body
    assert body.index('cd "$APP_PATH"') < body.index('vendor/autoload.php')


def test_it_writes_nothing():
    """The guarantee this probe is held to. Executable lines only — a comment about the
    "guarantee" contains "tee "."""
    body = code(script()).replace(">/dev/null", "")
    for verb in ("rm ", "mv ", "chmod", "chown", "mkdir", "tee ", "systemctl"):
        assert verb not in body, f"the probe writes: {verb!r}"


# ── an unreadable value must not become data ─────────────────────────────────

def test_the_warning_is_not_accepted_as_a_connection_name():
    """The bug as the customer saw it: a psysh warning shown as their default queue."""
    out = qw.parse_probe(probe_output(PSYSH_WARNING, PSYSH_WARNING))
    assert out["default"] == "", out["default"]
    assert out["connections"] == []


def test_an_unreadable_config_says_so_rather_than_looking_empty():
    """"No connections" and "we could not read the connections" are different facts, and
    only one of them means the timeout guard has nothing to check."""
    out = qw.parse_probe(probe_output(PSYSH_WARNING, PSYSH_WARNING))
    assert out["unreadable"] is True


def test_a_genuinely_empty_config_is_not_called_unreadable():
    out = qw.parse_probe(probe_output("database", ""))
    assert out["unreadable"] is False


@pytest.mark.parametrize("junk", [
    "  <warning> User Notice </warning> Writing to directory is not allowed.",
    "PHP Fatal error:  Uncaught Error: Class not found",
    "some words with spaces",
    "a" * 60,
])
def test_anything_that_is_not_an_identifier_is_refused(junk):
    assert qw.parse_probe(probe_output(junk, ""))["default"] == ""


@pytest.mark.parametrize("name", ["database", "redis", "sqs", "my_queue", "queue-1", "a.b"])
def test_a_real_connection_name_is_kept(name):
    assert qw.parse_probe(probe_output(name, ""))["default"] == name


def test_the_real_output_parses_with_its_retry_after():
    out = qw.parse_probe(probe_output("database", REAL_CONNECTIONS))
    assert out["default"] == "database"
    assert out["unreadable"] is False
    by_name = {c["name"]: c["retry_after"] for c in out["connections"]}
    assert by_name == {"sync": None, "database": 90, "redis": 90}


# ── the consequence, stated as a test ────────────────────────────────────────

def test_the_double_processing_guard_can_now_actually_fire():
    """With the config readable, a worker allowed to outlive `retry_after` is refused —
    which is the whole point of reading it."""
    out = qw.parse_probe(probe_output("database", REAL_CONNECTIONS))
    retry = qw.retry_after_for(out["connections"], "database")
    assert retry == 90
    with pytest.raises(qw.QueueError):
        qw.check_timeout(120, retry)
    qw.check_timeout(60, retry)          # comfortably inside — allowed


def test_the_broken_read_is_exactly_what_disabled_it():
    """The bug, demonstrated rather than asserted: with the warning as input there is no
    retry_after to compare against, so a worker that WOULD double-process is allowed."""
    out = qw.parse_probe(probe_output(PSYSH_WARNING, PSYSH_WARNING))
    retry = qw.retry_after_for(out["connections"], "database")
    assert retry is None
    qw.check_timeout(999999, retry)      # no error — the guard has nothing to check


def test_an_unknown_retry_after_still_does_not_refuse_a_good_worker():
    """Deliberate, and unchanged: refusing a worker on a site we genuinely cannot read
    would be worse than not checking. The fix is that "cannot read" is now rare, not that
    the fail-open changed."""
    qw.check_timeout(300, None)


def test_a_truncated_blob_degrades_instead_of_raising():
    """Realistic, not hypothetical: the read is capped with `tail -c 4000`, so a site with
    many queue connections gets a blob that STARTS with `{` and stops mid-way. That reaches
    `json.loads` and must come back as "we do not know", never as an exception that takes
    the screen down.
    """
    s = qw._S                                                   # noqa: SLF001
    cut = '{"default":"redis","connections":{"database":{"driver":"data'
    out = qw.parse_probe(f"{s}|php|/usr/bin/php8.3\n{s}|queue|{cut}")
    assert out["ok"] is True
    assert out["connections"] == []
    assert out["default"] == ""
    assert out["unreadable"] is True


def test_a_blob_that_is_not_an_object_degrades_too():
    """`json.loads` happily returns a string or a list. Either would then be asked for
    `.get("connections")` and raise."""
    s = qw._S                                                   # noqa: SLF001
    for junk in ('{"just": "a string"}', "[1,2,3]", '{"connections": "not a map"}'):
        out = qw.parse_probe(f"{s}|queue|{junk}")
        assert out["ok"] is True
        assert out["connections"] == []
