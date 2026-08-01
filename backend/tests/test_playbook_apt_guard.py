"""Every playbook that touches apt must wait for the server's own updater.

A brand-new Ubuntu runs unattended-upgrades on first boot and holds the apt lock for
minutes.  Racing it is how a customer's very first setup of a brand-new server fails.

Two bugs shipped here that `bash -n` cannot see, which is why these tests exist:

  * a script CALLED ``apt_wait`` while the definition lived in a prelude it did not
    include — an undefined function is a runtime error, not a syntax error;
  * the guard was anchored on ``set -euo pipefail``, which three playbooks spell
    ``set -uo pipefail``, so it was prepended ABOVE the shebang.
"""
import re
import subprocess

import pytest

from app.services import playbook_service as ps
from app.services import setup_service as ss

# A line that actually runs apt, ignoring comments.
_APT_CALL = re.compile(
    r"(?m)^[^#\n]*\b(?:apt|apt-get)\s+"
    r"(?:install|update|upgrade|autoremove|purge|remove|autoclean|dist-upgrade)\b")


def _bash_playbooks() -> list[tuple[str, str]]:
    out = []
    for item in ps.OFFICIAL_PLAYBOOKS:
        if item.get("script_type") == "powershell":
            continue
        script = ps._script_for(item)
        if script:
            out.append((item["slug"], script))
    return out


@pytest.mark.parametrize("slug,script", _bash_playbooks(), ids=lambda v: v if isinstance(v, str) and len(v) < 40 else "")
def test_apt_calls_are_guarded(slug: str, script: str) -> None:
    """No playbook may reach apt without the wait being defined in the same script."""
    if not _APT_CALL.search(script):
        return
    assert "apt_wait()" in script, f"{slug} runs apt but carries no apt_wait definition"
    assert "apt-get()" in script, f"{slug} runs apt but nothing makes the call wait"


def test_every_call_of_apt_wait_has_a_definition() -> None:
    """The shipped bug: a call whose definition lived in a prelude the script lacked."""
    for slug, script in _bash_playbooks():
        calls = re.search(r"(?m)^\s*apt_wait\b(?!\s*\()", script)
        if calls:
            assert "apt_wait()" in script, f"{slug} calls apt_wait but never defines it"


def test_guard_never_displaces_the_shebang() -> None:
    """The other shipped bug: injected text ended up above ``#!/bin/bash``."""
    for slug, script in _bash_playbooks():
        raw = next(i["script_bash"] for i in ps.OFFICIAL_PLAYBOOKS if i["slug"] == slug)
        if not raw.startswith("#!"):
            continue  # never had one; nothing to displace
        assert script.startswith("#!"), f"{slug} lost its shebang to an injected preamble"


def test_setup_recipe_steps_are_all_guarded() -> None:
    """The customer-facing path: first setup of a brand-new server."""
    by_slug = {i["slug"]: i for i in ps.OFFICIAL_PLAYBOOKS}
    for purpose in ss.PURPOSES:
        for step in ss.build_recipe(purpose, ssh_port=22).steps:
            item = by_slug.get(step.slug)
            assert item, f"setup step {step.slug} has no playbook"
            script = ps._script_for(item) or ""
            assert "apt_wait()" in script, f"setup step {step.slug} can race the apt lock"


def test_guard_is_syntactically_valid_bash() -> None:
    for slug, script in _bash_playbooks():
        r = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
        assert r.returncode == 0, f"{slug}: {r.stderr.strip()[:200]}"


def test_wait_is_bounded_below_the_step_watchdog() -> None:
    """Waiting forever would move the failure somewhere less clear — and so would waiting
    longer than the watchdog, which replaces our explanation with "took too long"."""
    from app.workers import setup_runner

    bound = re.search(r'\$_w" -gt (\d+)', ps._APT_GUARD)
    assert bound, "the wait is not bounded at all"
    assert int(bound.group(1)) < setup_runner._STEP_TIMEOUT


def test_detection_does_not_depend_on_an_optional_package() -> None:
    """fuser ships in psmisc; a minimal image has none, and a silent no-op is the bug.

    Asserted against executable lines only — the first version of this test matched the
    word in a comment, so deleting the fallback left it passing.
    """
    code = "\n".join(ln for ln in ps._APT_GUARD.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "pgrep -x" in code


def test_every_setup_step_can_actually_be_prepared() -> None:
    """A step whose variables cannot be filled kills the run before it starts.

    "Websites" shipped with a MySQL root password the recipe never supplied, so the
    stack step raised while the run was being prepared — outside the per-step handler,
    which is why the customer saw "something went wrong" and no failed step at all.
    """
    by_slug = {i["slug"]: i for i in ps.OFFICIAL_PLAYBOOKS}
    for purpose in ss.PURPOSES:
        for step in ss.build_recipe(purpose, ssh_port=22).steps:
            item = by_slug.get(step.slug)
            assert item, f"setup step {step.slug} has no playbook"
            pb = ps._build_playbook(item)
            variables = {**ps.declared_defaults(pb), **(step.variables or {})}
            # Raises UnresolvedVariables if anything is still unfilled.
            ps.substitute_variables(pb.script_bash, variables)
