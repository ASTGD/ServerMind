"""Setting up a raw Ubuntu 22.04, and the three things it got wrong.

Driven on a real fresh server (TestServerNew) exactly as a customer would: Web Server,
everything left at its default. Setup reported 14 of 14 — and then:

1. **The Laravel site failed.** 22.04 ships PHP 8.1; our Laravel installer needs 8.3+. So
   the option titled *"Web Server (HTML, PHP, WordPress, **Laravel**)"* built a server where
   Laravel is refused, 16 minutes in. Worse on its own terms: that default is labelled
   *"Safe choice"* and installed a version the same screen labels *"No longer gets security
   fixes"*.

2. **"Turning on automatic security updates" was reported as skipped** — *"the server went
   quiet and the connection timed out"* — while on the machine unattended-upgrades was
   installed, enabled and running, and our own config file was written 3 seconds into the
   step. A step that had DONE its job was reported as not done.

3. The cause of 2: `unattended-upgrade --dry-run --debug >/dev/null 2>&1`, whose output we
   discard. On a fresh server Ubuntu's own first-boot updater holds the package lock, so it
   waits there in silence until the idle watchdog kills the connection.

Found on the way: `lemp-stack` included the shared PHP layer AND an inline copy of it, so
three functions were defined twice and the later copy silently won — the shell version of
the redefinition trap the Python sweep already guards. The last test here is that sweep,
for generated shell.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

import pytest

from app.services.playbook_service import OFFICIAL_PLAYBOOKS

BASH = [p for p in OFFICIAL_PLAYBOOKS if p.get("script_bash")]


def script(slug: str) -> str:
    return next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == slug)["script_bash"]


def run_shell(setup: str, *, stub_apt_candidate: str) -> str:
    """Run the version rule out of the REAL generated script, with apt-cache stubbed.

    The functions are pulled from the script rather than restated here, so a change to the
    script is a change to what this tests.
    """
    body = script("lemp-stack")
    start = body.index("PHP_MIN=")
    end = body.index("php_install_version() {")
    layer = body[start:end]

    prog = f"""
FAMILY=debian
PM=apt
apt-cache() {{ printf '%s\\n' '  Candidate: {stub_apt_candidate}'; }}
{layer}
{setup}
"""
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(prog)
        path = f.name
    try:
        r = subprocess.run(["bash", path], capture_output=True, text=True, timeout=30)
        return (r.stdout + r.stderr).strip()
    finally:
        os.unlink(path)


# ── the PHP rule, run rather than read ───────────────────────────────────────

@pytest.mark.parametrize("candidate,expected", [
    ("2:8.1+92ubuntu1", "OLD"),      # Ubuntu 22.04 — the server this was found on
    ("2:7.4+76ubuntu1", "OLD"),      # Ubuntu 20.04
    ("2:8.2+93ubuntu2", "OLD"),      # Debian 12
    ("2:8.3+93ubuntu2", "CURRENT"),  # Ubuntu 24.04 — must NOT reach for the archive
    ("2:8.4+94ubuntu1", "CURRENT"),
])
def test_the_rule_decides_correctly_per_distro(candidate, expected):
    out = run_shell(
        'if php_is_old "$(php_distro_version)"; then echo OLD; else echo CURRENT; fi',
        stub_apt_candidate=candidate)
    assert out.endswith(expected), f"{candidate} -> {out}"


def test_the_version_is_parsed_out_of_the_package_string():
    """`2:8.1+92ubuntu1` is an epoch, a version and a revision. Reading it wrong is how the
    rule would silently decide the opposite of what it should."""
    out = run_shell("php_distro_version", stub_apt_candidate="2:8.1+92ubuntu1")
    assert out.endswith("8.1"), out


def test_an_unknown_version_is_not_treated_as_old():
    """Fails toward the distro's own PHP. We never reach for a third-party archive on a
    guess — if we cannot tell what the system ships, its own package is the safer choice."""
    for junk in ("", "none", "(none)"):
        out = run_shell('if php_is_old "%s"; then echo OLD; else echo CURRENT; fi' % junk,
                        stub_apt_candidate="2:8.1+92ubuntu1")
        assert out.endswith("CURRENT"), f"{junk!r} -> {out}"


def test_the_minimum_is_what_laravel_actually_needs():
    """The number here and the number the Laravel installer enforces have to agree, or the
    setup builds a server its own installer then refuses."""
    stack = script("lemp-stack")
    assert re.search(r"^PHP_MIN=8\.3$", stack, re.M), "PHP_MIN moved"
    laravel = script("laravel-site")
    assert "80300" in laravel, "the Laravel installer no longer requires 8.3"


def test_a_current_distro_php_does_not_pull_in_a_third_party_archive():
    """Ubuntu 24.04 already ships 8.3. Adding the PHP archive there would put a third-party
    package source on a server that had no need of one."""
    stack = script("lemp-stack")
    default_branch = stack[stack.index('if [ "$PHP_VERSION" = default ]'):]
    default_branch = default_branch[:default_branch.index("\nelse\n")]
    lines = [ln for ln in default_branch.splitlines() if not ln.strip().startswith("#")]
    archive = [ln for ln in lines if "php_archive_add" in ln]
    assert archive, "the old-PHP path no longer installs a supported version"
    for ln in archive:
        assert "php_is_old" in default_branch, "the archive is added unconditionally"


def test_the_customer_is_told_what_happened_either_way():
    stack = script("lemp-stack")
    assert "no longer gets security fixes and cannot" in stack
    assert "which is current. Using it." in stack


def test_a_failed_archive_falls_back_rather_than_leaving_no_php():
    """No PHP at all is worse than an old PHP — but the customer has to be told, because
    Laravel will not install on what they end up with."""
    stack = script("lemp-stack")
    assert "the PHP archive was unreachable" in stack
    assert "Laravel needs PHP $PHP_MIN or newer" in stack


# ── the step that reported its own success as a skip ─────────────────────────

def test_the_update_check_cannot_go_quiet_for_minutes():
    """It ran 5 minutes on a fresh server and was killed by the idle watchdog, after the
    real work had already finished 3 seconds in."""
    body = script("auto-updates")
    line = next(ln for ln in body.splitlines() if "unattended-upgrade --dry-run" in ln)
    assert "timeout " in line, f"unbounded: {line.strip()}"


def test_it_says_something_before_it_goes_quiet():
    """A step that prints nothing for a minute looks identical to a step that has hung."""
    body = script("auto-updates")
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    i = next(i for i, ln in enumerate(lines) if "unattended-upgrade --dry-run" in ln)
    assert any("echo" in ln and "Checking the update job" in ln for ln in lines[max(0, i - 3):i])


def test_a_check_that_times_out_is_not_reported_as_a_failure():
    """The configuration is already written by then. Saying the step failed would be the
    same dishonesty in the other direction."""
    body = script("auto-updates")
    assert "Automatic updates are on." in body


# ── the sweep this work turned up ────────────────────────────────────────────

_FUNC = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\)\s*\{", re.M)


@pytest.mark.parametrize("pb", BASH, ids=lambda p: p["slug"])
def test_no_generated_script_defines_a_function_twice(pb):
    """`lemp-stack` included the shared PHP layer AND an inline copy of it, so three
    functions were defined twice and the LATER one silently won — meaning a fix to the
    shared layer would not have reached the script that matters.

    Bash says nothing about this, exactly like Python. The Python sweep already guards
    against it in `app/`; this is the same guard for the shell we generate.
    """
    names = _FUNC.findall(pb["script_bash"])
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert dupes == [], f"{pb['slug']} defines {dupes} more than once"


@pytest.mark.parametrize("pb", BASH, ids=lambda p: p["slug"])
def test_every_generated_script_still_parses(pb):
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(pb["script_bash"])
        path = f.name
    try:
        r = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[:400]
    finally:
        os.unlink(path)


def test_looking_up_the_version_can_never_kill_the_setup():
    """Caught by an existing test the moment this was written: the scripts run under
    `set -euo pipefail`, so a lookup pipeline that finds nothing exits non-zero and takes
    the WHOLE setup down — at "Installing the web server", with no explanation.

    A version we cannot read has to mean "use the distro's PHP", not "stop".
    """
    out = run_shell(
        'apt-cache() { echo "  Candidate: (none)"; }\n'
        'V="$(php_distro_version)"; echo "survived version=[$V]"',
        stub_apt_candidate="unused")
    assert "survived" in out, out
    assert "version=[]" in out, out


def test_a_missing_package_manager_does_not_kill_it_either():
    out = run_shell(
        'apt-cache() { return 127; }\n'
        'V="$(php_distro_version)"; echo "survived version=[$V]"',
        stub_apt_candidate="unused")
    assert "survived version=[]" in out, out
