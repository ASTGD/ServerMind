"""A step that is quiet is not a step that is slow.

The owner pressed "Set up this server" on a freshly rebuilt Ubuntu and it failed on step 1
after 79 seconds, saying it "took longer than 30 minutes".

Three faults stacked up. The apt-lock guard — added so a new server's own updater cannot
break the install — waits in silence. paramiko gives up on a channel that has produced no
output for 60 seconds, so the guard was killed by the CONNECTION, an order of magnitude
inside its own 10-minute bound. And on Python 3.11+ `asyncio.TimeoutError`,
`socket.timeout` and `TimeoutError` are the same class, so that arrived at the handler for
our own watchdog and was reported as it — a sentence that was not true about a step that
had run for a minute.
"""
import re
import subprocess

import pytest

from app.services import playbook_service as ps
from app.workers import setup_runner


# ── The wait must not go quiet ───────────────────────────────────────────────

def _run_the_real_wait(tmp_path) -> str:
    """Run the actual guard with the updater permanently busy and sleep made instant.

    Real sleeps would make this a ten-minute test; the guard counts in its own units, so
    the cadence it reports is the cadence it would really produce.
    """
    binstub = tmp_path / "bin"
    binstub.mkdir()
    (binstub / "apt-get").write_text("#!/bin/sh\nexit 0\n")       # so type -P finds one
    (binstub / "pgrep").write_text("#!/bin/sh\nexit 0\n")         # always busy
    (binstub / "sleep").write_text("#!/bin/sh\nexit 0\n")         # instant
    (binstub / "fuser").write_text("#!/bin/sh\nexit 1\n")
    for f in binstub.iterdir():
        f.chmod(0o755)
    script = f'{ps._APT_GUARD}\napt_wait\n'
    proc = subprocess.run(["bash", "-c", f'export PATH="{binstub}:$PATH"; {script}'],
                          capture_output=True, text=True, timeout=60)
    return proc.stdout


def test_the_wait_never_goes_quiet_for_a_minute(tmp_path):
    """The property, measured rather than asserted: no gap between two things it says is
    wide enough for the connection to give up.

    Written against the seconds the guard itself reports, so it fails if the heartbeat is
    removed OR merely slowed past the limit — the second of which reads as harmless.
    """
    out = _run_the_real_wait(tmp_path)
    marks = [0] + [int(m) for m in re.findall(r"\((\d+)s\)", out)]
    assert len(marks) > 1, f"the wait said nothing while it waited:\n{out}"
    gaps = [b - a for a, b in zip(marks, marks[1:])]
    assert max(gaps) <= 60, (
        f"went quiet for {max(gaps)}s — paramiko gives up at 60s, so this step is killed "
        f"by the connection long before its own bound")


def test_the_wait_is_still_bounded(tmp_path):
    """The heartbeat must not turn a stuck dpkg into a forever wait."""
    out = _run_the_real_wait(tmp_path)
    assert "busy for 10 minutes" in out
    assert "nothing was changed" in out


def test_it_still_says_what_is_happening_the_first_time(tmp_path):
    """A customer watching a brand-new server needs the reason, not just a counter."""
    out = _run_the_real_wait(tmp_path)
    assert "Waiting for the server's own updater" in out
    assert out.index("Waiting for the server") < out.index("still waiting")


# ── The message must say which timeout fired ─────────────────────────────────

def test_a_quiet_connection_is_not_reported_as_a_slow_step():
    """The exact false sentence, from the exact elapsed time it was said about."""
    note = setup_runner._timeout_note(79)
    assert "30 minutes" not in note
    assert "quiet" in note


def test_a_step_that_really_did_run_out_of_time_says_so():
    assert "30 minutes" in setup_runner._timeout_note(setup_runner._STEP_TIMEOUT)


# ── A long installer gets a longer silence limit than a short probe ──────────

@pytest.mark.asyncio
async def test_the_setup_runner_allows_a_step_to_be_quiet_longer_than_a_probe(monkeypatch):
    """Reads the value that actually reaches paramiko, because the whole bug was a default
    nobody had chosen sitting under a budget somebody had."""
    seen = {}

    async def _fake(_sid, _h, _p, _u, _a, _c, _cmd, expected_fingerprint=None,
                    read_timeout=60):
        seen["read_timeout"] = read_timeout
        return "", "", 0

    from app.services import connection_manager, ssh_service

    monkeypatch.setattr(ssh_service, "execute", _fake)

    class _Server:
        id, host, port = "s", "h", 22
        username, auth_type, encrypted_cred = "root", "password", "x"
        fingerprint, connection_type = None, "ssh"

    await connection_manager.execute(_Server(), "echo hi",
                                     read_timeout=setup_runner._QUIET_LIMIT)
    assert seen["read_timeout"] == setup_runner._QUIET_LIMIT
    assert setup_runner._QUIET_LIMIT > 60, "a step is quieter than a probe, not louder"
    assert setup_runner._QUIET_LIMIT < setup_runner._STEP_TIMEOUT, (
        "a silence limit above the step budget can never fire, so a hung step would hang")


def test_the_runner_actually_passes_it():
    import inspect
    src = inspect.getsource(setup_runner._run_steps)
    assert "read_timeout=_QUIET_LIMIT" in src
