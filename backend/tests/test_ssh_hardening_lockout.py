"""Hardening SSH must never close the door ServerAlly came through.

Found live on a fresh Ubuntu 24.04: the "Securing the login" step wrote
``PermitRootLogin no`` on a server ServerAlly reaches AS ROOT WITH A PASSWORD, where no
SSH key existed.  The restart happened to fail (wrong unit name on Debian), so the config
sat there armed — the next time sshd restarted for any reason, the server would have been
lost, recoverable only from the provider's console.

These tests run the real script's decision logic under bash with the applier stubbed, so
they assert what the script DECIDES to write, not what it prints.
"""
import os
import subprocess
import tempfile

import pytest

from app.services import playbook_service as ps
from app.services import setup_service as ss

# Replaces the real helpers: record the decisions, never touch a config, stop at apply.
# getent is stubbed because macOS has none, and the home directory is where the test
# controls whether a key exists.
_STUB = """
getent() { echo "u:x:0:0::${SM_TEST_HOME}:/bin/sh"; }
ssh_backup() { :; }
ssh_set() { echo "SET $1 $2"; }
ssh_apply() { echo "APPLIED"; exit 0; }
"""


def _decisions(slug: str, variables: dict, *, key_present: bool) -> tuple[int, str]:
    item = next(p for p in ps.OFFICIAL_PLAYBOOKS if p["slug"] == slug)
    script = ps.substitute_variables(ps._script_for(item), variables)
    assert ps._SSH_SAFE in script, f"{slug} is missing the ssh safety helpers"
    script = script.replace(ps._SSH_SAFE, _STUB)

    with tempfile.TemporaryDirectory() as home:
        if key_present:
            os.makedirs(os.path.join(home, ".ssh"))
            with open(os.path.join(home, ".ssh", "authorized_keys"), "w") as fh:
                fh.write("ssh-ed25519 AAAAC3Nz test@key\n")
        env = {**os.environ, "SM_TEST_HOME": home}
        r = subprocess.run(["bash", "-s"], input=script, capture_output=True,
                           text=True, env=env, timeout=60)
    return r.returncode, r.stdout + r.stderr


def _sets(out: str) -> dict[str, str]:
    return {ln.split()[1]: ln.split()[2]
            for ln in out.splitlines() if ln.startswith("SET ")}


# ── initial-hardening ────────────────────────────────────────────────────────

def test_root_by_password_keeps_root_login() -> None:
    """The exact live case. Writing PermitRootLogin no here strands the server."""
    _, out = _decisions("initial-hardening",
                        {"SSH_PORT": "22", "LOGIN_USER": "root", "AUTH_TYPE": "password"},
                        key_present=False)
    assert "PermitRootLogin" not in _sets(out)
    assert "PasswordAuthentication" not in _sets(out)


def test_root_by_password_still_hardens_what_is_safe() -> None:
    """Refusing the dangerous change is not an excuse to do nothing."""
    _, out = _decisions("initial-hardening",
                        {"SSH_PORT": "22", "LOGIN_USER": "root", "AUTH_TYPE": "password"},
                        key_present=False)
    assert _sets(out).get("X11Forwarding") == "no"


def test_root_by_key_hardens_to_key_only() -> None:
    _, out = _decisions("initial-hardening",
                        {"SSH_PORT": "22", "LOGIN_USER": "root", "AUTH_TYPE": "key"},
                        key_present=True)
    sets = _sets(out)
    assert sets.get("PermitRootLogin") == "prohibit-password"
    assert sets.get("PasswordAuthentication") == "no"


def test_key_auth_but_no_key_on_the_server_is_not_trusted() -> None:
    """The stored auth type says key; the server says otherwise. Believe the server."""
    _, out = _decisions("initial-hardening",
                        {"SSH_PORT": "22", "LOGIN_USER": "root", "AUTH_TYPE": "key"},
                        key_present=False)
    assert "PasswordAuthentication" not in _sets(out)
    assert "PermitRootLogin" not in _sets(out)


def test_non_root_login_may_close_root() -> None:
    _, out = _decisions("initial-hardening",
                        {"SSH_PORT": "22", "LOGIN_USER": "deploy", "AUTH_TYPE": "key"},
                        key_present=True)
    assert _sets(out).get("PermitRootLogin") == "no"


# ── ssh-key-auth, which a customer can run on its own ────────────────────────

@pytest.mark.parametrize("auth,key,should_run", [
    ("key", True, True),        # a key exists and it is how we sign in
    ("key", False, False),      # no key on the server at all
    ("password", True, False),  # a key exists, but ours is a password
    ("password", False, False),
])
def test_key_only_enforcement_refuses_unless_a_key_really_works(
        auth: str, key: bool, should_run: bool) -> None:
    code, out = _decisions("ssh-key-auth",
                           {"LOGIN_USER": "root", "AUTH_TYPE": auth}, key_present=key)
    if should_run:
        assert code == 0 and _sets(out).get("PasswordAuthentication") == "no"
    else:
        assert code != 0, "would have locked everyone out"
        assert "SET " not in out, "refused, but changed the config anyway"


# ── the plumbing that carries the decision ───────────────────────────────────

def test_recipe_carries_how_serverally_signs_in() -> None:
    """A default of root/password would silently re-enable the lockout."""
    steps = {s.slug: s for s in ss.build_recipe(
        "websites", ssh_port=22, login_user="deploy", auth_type="key").steps}
    v = steps["initial-hardening"].variables
    assert v["LOGIN_USER"] == "deploy" and v["AUTH_TYPE"] == "key"


def test_defaults_are_the_cautious_ones() -> None:
    """Run without knowing, and the script must assume the case it cannot recover from."""
    steps = {s.slug: s for s in ss.build_recipe("websites", ssh_port=22).steps}
    v = steps["initial-hardening"].variables
    assert v["AUTH_TYPE"] == "password"


def test_ssh_unit_name_is_resolved_not_assumed() -> None:
    """`systemctl restart sshd` is what failed on Ubuntu 24.04 — there is no such unit."""
    for slug in ("initial-hardening", "ssh-key-auth"):
        item = next(p for p in ps.OFFICIAL_PLAYBOOKS if p["slug"] == slug)
        script = ps._script_for(item)
        assert "restart sshd" not in script and "reload sshd" not in script
        assert "ssh_unit()" in script


def test_config_is_validated_before_it_is_applied() -> None:
    assert "sshd -t" in ps._SSH_SAFE
