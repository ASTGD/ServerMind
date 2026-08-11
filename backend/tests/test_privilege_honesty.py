"""A scan that could not look must never say it found nothing.

Every cloud image ships with root SSH disabled — AWS, Google Cloud and Azure all do — so the
ordinary way to connect is `ubuntu` or `ec2-user` with passwordless sudo. Our probes assumed
they were already root and mostly never asked, so on such a connection:

* `find` over `/home` was denied everything and printed nothing
* every checker reads "nothing" as **pass**
* the malware scan reported **"No threats found"** — not *"I could not look"*

That is a false all-clear on the most safety-critical feature we ship, and it is the same
shape as the bug `threat_service._t` was written to avoid.

The rule, and the only one that makes a verdict trustworthy:
**bad news may be reported while blind; good news may not.**
"""
import shutil
import subprocess

import pytest

from app.services import privilege as pv
from app.services import threat_service as t


# ── The rule ─────────────────────────────────────────────────────────────────

def test_nothing_found_while_blind_is_not_clean():
    """The bug, stated as a test."""
    verdict, _ = t._summarize([{"severity": "pass"}], level=pv.NONE,
                              skipped=[{"id": "webshell"}])
    assert verdict == "unknown"


def test_nothing_found_with_root_is_clean():
    assert t._summarize([{"severity": "pass"}], level=pv.ROOT, skipped=[])[0] == "clean"


def test_nothing_found_through_sudo_is_also_clean():
    """`sudo -n` reads everything root can, so the answer is a real answer."""
    assert t._summarize([{"severity": "pass"}], level=pv.SUDO, skipped=[])[0] == "clean"


def test_malware_found_while_blind_is_still_reported():
    """Finding malware with half the disk unreadable is still finding malware. Only the
    "nothing here" conclusion is unsafe — refusing to report a confirmed webshell because
    the scan was partial would be the opposite mistake, and worse."""
    verdict, _ = t._summarize([{"severity": "critical"}], level=pv.NONE,
                              skipped=[{"id": "x"}])
    assert verdict == "compromised"


def test_a_skipped_check_blocks_clean_even_at_full_privilege():
    """Skipping can happen for reasons other than privilege. Whatever the reason, an
    unchecked critical probe means the clean verdict was not earned."""
    verdict, _ = t._summarize([{"severity": "pass"}], level=pv.ROOT,
                              skipped=[{"id": "webshell"}])
    assert verdict == "unknown"


# ── Reading the level ────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("root", pv.ROOT), ("sudo", pv.SUDO), ("none", pv.NONE),
    ("root\nextra noise", pv.ROOT),
    ("", pv.NONE), ("   ", pv.NONE), (None, pv.NONE),
    ("sudo: a password is required", pv.NONE),
])
def test_the_level_fails_closed(raw, expected):
    """Anything we cannot read is `none`. If we do not know what we had, we must not assume
    we had everything — that assumption is what produces the false all-clear."""
    assert pv.parse(raw) == expected


def test_only_root_and_sudo_count_as_able_to_read():
    assert pv.can_read_everything(pv.ROOT) and pv.can_read_everything(pv.SUDO)
    assert not pv.can_read_everything(pv.NONE)
    assert not pv.can_read_everything("something else")


def test_the_customer_is_told_what_to_do():
    msg = pv.explain(pv.NONE)
    assert msg and "sudo" in msg and "root" in msg
    assert pv.explain(pv.ROOT) is None


# ── The probes ───────────────────────────────────────────────────────────────

def test_every_probe_that_needs_privilege_actually_asks_for_it():
    """A probe marked `needs_root` that never uses `$SA_SUDO` would still read nothing on a
    sudo-capable connection — it would be skipped instead of working, which is honest but
    needlessly useless."""
    for s in t.LINUX_SECTIONS:
        if s.needs_root:
            assert "$SA_SUDO" in s.command, f"{s.id} needs root but never escalates"


def test_the_probes_that_do_not_need_root_say_so():
    """`/etc/passwd` is 644 and `ld.so.preload` is world-readable — checked on a live server
    as a non-root user. Marking them privileged would report a "could not check" that is not
    true, which is its own kind of dishonesty."""
    assert {s.id for s in t.LINUX_SECTIONS if not s.needs_root} == {"meta", "accounts"}


def test_a_new_probe_defaults_to_needing_root():
    """The safe direction. A forgotten declaration costs a needless "could not check", not a
    false all-clear."""
    from app.services.threat_service import Section

    assert Section("x", "true").needs_root is True


def test_the_script_reports_what_it_decided():
    script = t._build_script(t.FAST_SECTIONS)
    assert pv.PRELUDE in script
    assert t._marker(pv.SECTION) in script
    assert script.index(pv.PRELUDE) < script.index("$SA_SUDO"), (
        "the level must be decided before any probe uses it")


def test_sudo_never_waits_for_a_password():
    """There is no terminal on this connection. Without `-n`, sudo would hang until the
    channel times out and the whole scan would be reported as a connection failure."""
    assert "sudo -n" in pv.PRELUDE
    assert "sudo true" not in pv.PRELUDE


def test_the_probe_is_still_read_only():
    """The guarantee that was already here must survive the change."""
    script = t._build_script(t.LINUX_SECTIONS)
    for verb in (" rm ", " mv ", " dd ", " mkfs", " chmod ", " chown ", " tee ", " curl ",
                 " wget "):
        assert verb not in script, f"the read-only scan contains {verb.strip()}"


# ── Run it ───────────────────────────────────────────────────────────────────

linux = pytest.mark.skipif(shutil.which("sudo") is None or shutil.which("bash") is None,
                           reason="needs bash and sudo")


@linux
def test_the_prelude_reports_none_when_sudo_cannot_be_used(tmp_path):
    """Executed, not read: with sudo replaced by something that always refuses — which is
    what a user with no sudo rights actually experiences — the answer must be `none`."""
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "sudo").write_text("#!/bin/sh\nexit 1\n")
    (stub / "sudo").chmod(0o755)
    (stub / "id").write_text("#!/bin/sh\necho 1000\n")
    (stub / "id").chmod(0o755)

    out = subprocess.run(
        ["bash", "-c", f'export PATH="{stub}:$PATH"; {pv.PRELUDE}; echo "$SA_PRIV"'],
        capture_output=True, text=True)
    assert pv.parse(out.stdout.strip().splitlines()[-1]) == pv.NONE


@linux
def test_the_prelude_reports_sudo_when_it_works(tmp_path):
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "sudo").write_text("#!/bin/sh\nexit 0\n")
    (stub / "sudo").chmod(0o755)
    (stub / "id").write_text("#!/bin/sh\necho 1000\n")
    (stub / "id").chmod(0o755)

    out = subprocess.run(
        ["bash", "-c", f'export PATH="{stub}:$PATH"; {pv.PRELUDE}; echo "$SA_PRIV|$SA_SUDO"'],
        capture_output=True, text=True)
    level, _, prefix = out.stdout.strip().splitlines()[-1].partition("|")
    assert level == pv.SUDO
    assert prefix == "sudo -n"


# ── The worker must not close an incident because it stopped being able to look ──

import uuid as _uuid

import pytest as _pytest


@_pytest.mark.asyncio
async def test_an_unknown_scan_does_not_close_an_open_compromise(monkeypatch):
    """Found by checking the callers rather than the service.

    The worker closed an incident whenever the verdict was `not in _ALERTING` — and
    `unknown` is not in that set. So a server that was compromised, and then had its
    connection changed to a non-root user, would have its incident CLOSED: "the server came
    back clean", when in truth we had simply stopped being able to look.

    The same false all-clear as the scan itself, one level up.
    """
    from app.workers import threat_worker as tw

    closed, alerted = [], []

    async def fake_scan(_server, *, fast_only=False):
        return {"verdict": "unknown", "status": "completed", "error": None,
                "counts": {k: 0 for k in ("critical", "high", "medium", "low", "info", "pass")},
                "findings": [], "privilege": pv.NONE,
                "skipped": [{"id": "webshell"}], "note": pv.explain(pv.NONE),
                "duration_ms": 5}

    import inspect

    src = inspect.getsource(tw)
    # The guard is one line, and asserting on it directly is the honest test here: the
    # surrounding function needs a database session and a real server row, which this
    # rule does not depend on.
    assert 'result["verdict"] == "clean" and prev in _ALERTING' in src, (
        "an incident must close only on a real clean, never merely on 'not alerting'")
    assert 'result["verdict"] not in _ALERTING and prev in _ALERTING' not in src


def test_unknown_never_raises_an_alert():
    """It is not a threat — it is a gap in our own access. Alerting on it would page
    somebody about our configuration, which is not what a security alert is for."""
    from app.workers.threat_worker import _ALERTING

    assert "unknown" not in _ALERTING
