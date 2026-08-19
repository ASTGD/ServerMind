"""BUG-015 — the one class of damage ServerAlly can do to itself.

A `harden-server` mission applied `PermitRootLogin prohibit-password` to a LIVE server that
ServerAlly reaches as root with a password. Because the step used `reload` rather than
`restart`, the session kept working, the step reported **success**, and the lockout only
surfaced on the next connection. There is no recovery from inside the product — it needs the
customer's provider console.

The reasoning is the part worth remembering: the model correctly observed that no root SSH
key existed, and treated that as evidence the change was harmless. The opposite is true —
"no key is set up" is exactly what makes it fatal. Then its own verification read
`PasswordAuthentication` (which governs normal users) and reported all was well, concealing
the damage it had just done to root.

Two layers, because the prompt layer alone is a request rather than a guarantee (the lesson
of BUG-001):

1. **Code refuses it** — `safety_service.lockout_risk`, wired into the one choke point every
   AI-planned command passes through. It REFUSES rather than warns, the same call
   `firewall_service.lockout_risk` makes: a warning is something a customer clicks through
   once, and the cost here is a server nobody can reach.
2. **The skill and the prompt** stop it being proposed at all.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from app.services import safety_service as ss

ROOT_PW = ss.Access(username="root", auth_type="password", port=22)
ROOT_KEY = ss.Access(username="root", auth_type="key", port=22)
USER_PW = ss.Access(username="deploy", auth_type="password", port=22)
USER_KEY = ss.Access(username="deploy", auth_type="key", port=22)

#: Verbatim from the incident report.
INCIDENT_CMD = (
    "sed -i 's/^#\\?PermitRootLogin.*/PermitRootLogin prohibit-password/' "
    "/etc/ssh/sshd_config && systemctl reload sshd")


# ── the incident itself ──────────────────────────────────────────────────────

def test_the_exact_command_from_the_incident_is_refused():
    verdict = ss.validate_command(INCIDENT_CMD, "linux", ROOT_PW)
    assert verdict.status == "blocked"
    assert verdict.pattern == "self-lockout"


def test_the_refusal_says_what_it_protects_and_how_to_proceed():
    """A refusal that only says no teaches the customer the product is broken."""
    reason = ss.lockout_risk(INCIDENT_CMD, ROOT_PW)
    assert "lock ServerAlly out" in reason
    assert "provider's console" in reason
    assert "SSH key" in reason, "it must say what would make this safe"


@pytest.mark.parametrize("value", [
    "prohibit-password", "without-password", "no", "forced-commands-only",
])
def test_every_way_of_closing_root_login_is_caught(value):
    """One spelling caught and another missed is the same bug with a different word."""
    assert ss.lockout_risk(f"ssh_set PermitRootLogin {value}", ROOT_PW)


def test_reopening_root_login_is_not_refused():
    """`PermitRootLogin yes` is the RECOVERY. Refusing it would trap the customer."""
    assert ss.lockout_risk("ssh_set PermitRootLogin yes", ROOT_PW) == ""


# ── the other ways in get cut ────────────────────────────────────────────────

def test_turning_off_password_logins_is_refused_when_that_is_how_we_connect():
    assert ss.lockout_risk("ssh_set PasswordAuthentication no", USER_PW)


def test_requiring_a_key_is_refused_when_we_have_none():
    assert ss.lockout_risk("ssh_set AuthenticationMethods publickey", ROOT_PW)


@pytest.mark.parametrize("cmd", [
    "passwd -l root",
    "usermod -L root",
    "passwd --lock root",
])
def test_locking_the_root_account_is_refused(cmd):
    """Same outcome by a different route: the account we use stops accepting its password."""
    assert ss.lockout_risk(cmd, ROOT_PW)


def test_moving_the_ssh_port_is_refused():
    """ServerAlly reconnects on the stored port and would simply not find the server."""
    assert ss.lockout_risk("ssh_set Port 2222 && systemctl reload sshd", ROOT_PW)


def test_writing_the_same_port_is_not_refused():
    """Re-asserting the port we already use changes nothing."""
    assert ss.lockout_risk("ssh_set Port 22 # /etc/ssh/sshd_config", ROOT_PW) == ""


# ── it must not refuse legitimate work ───────────────────────────────────────

def test_a_server_we_reach_by_key_may_be_hardened():
    """The whole point of the guard is that it depends on how WE connect. On a key-authed
    server this is exactly the right hardening step and must go through."""
    assert ss.lockout_risk("ssh_set PermitRootLogin prohibit-password", ROOT_KEY) == ""
    assert ss.lockout_risk("ssh_set PasswordAuthentication no", USER_KEY) == ""


def test_closing_root_login_is_fine_when_root_is_not_the_account_we_use():
    assert ss.lockout_risk("ssh_set PermitRootLogin no", USER_PW) == ""


def test_reading_the_config_is_never_refused():
    """`grep "PasswordAuthentication no" sshd_config` is a normal thing to run while
    investigating. A guard that refuses looking is a guard people route around."""
    for cmd in ('grep -i "PasswordAuthentication no" /etc/ssh/sshd_config',
                "sshd -T | grep -i permitrootlogin",
                "cat /etc/ssh/sshd_config"):
        assert ss.lockout_risk(cmd, ROOT_PW) == "", cmd


def test_the_harmless_neighbour_setting_is_not_confused_for_the_dangerous_one():
    """`KbdInteractiveAuthentication no` sits directly beside `PasswordAuthentication no`
    in every hardening guide and is harmless."""
    assert ss.lockout_risk("ssh_set KbdInteractiveAuthentication no", ROOT_PW) == ""


def test_ordinary_commands_are_untouched():
    for cmd in ("apt-get update", "systemctl restart nginx", "df -h", "rm -rf /tmp/cache"):
        assert ss.lockout_risk(cmd, ROOT_PW) == "", cmd


def test_nothing_is_refused_when_we_do_not_know_how_we_connect():
    """Fails OPEN by choice. This runs on EVERY command, so refusing real work because a
    caller did not supply the facts would be its own kind of damage. The structural test
    below is what stops a caller omitting them."""
    assert ss.lockout_risk(INCIDENT_CMD, None) == ""


# ── the facts are read off the server, not guessed ───────────────────────────

def test_access_is_read_from_the_server_row():
    class _S:
        username, auth_type, port = "root", "PASSWORD", "22"

    a = ss.access_for(_S())
    assert (a.username, a.auth_type, a.port) == ("root", "password", 22)


def test_a_nonsense_port_falls_back_rather_than_crashing():
    class _S:
        username, auth_type, port = "root", "password", "not-a-port"

    assert ss.access_for(_S()).port == 22


# ── every caller supplies the facts ──────────────────────────────────────────

#: Modules that reach the safety layer with a server in hand. `app/evals/runner.py` is
#: deliberately absent — it validates a corpus of strings and genuinely has no server.
CALLERS = [
    "app/websocket/terminal.py",
    "app/mcp/server.py",
    "app/services/autopilot_service.py",
    "app/services/cron_service.py",
]


def test_every_caller_that_has_a_server_passes_it():
    """The guard is useless at a call site that forgets to hand it the facts — and an
    optional argument is exactly what three callers of `ssh_service._get_client` silently
    skipped, leaving host-key verification off for years.

    Parsed rather than grepped: a call is checked by its actual argument count.
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    missing = []
    for rel in CALLERS:
        tree = ast.parse((root / rel).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = ast.unparse(node.func)
            if not target.endswith(("safety_service.validate_command",
                                    "safety_service.validate_plan")):
                continue
            supplies = len(node.args) >= 3 or any(k.arg == "access" for k in node.keywords)
            if not supplies:
                missing.append(f"{rel}:{node.lineno} {ast.unparse(node)[:70]}")

    assert missing == [], (
        "these call the safety layer without saying how ServerAlly reaches the server, so "
        "the self-lockout guard cannot run there: " + "; ".join(missing))


def test_the_guard_runs_before_the_blocklist_so_its_message_wins():
    body = "\n".join(ln for ln in inspect.getsource(ss.validate_command).splitlines()
                     if not ln.strip().startswith("#"))
    assert body.index("lockout_risk(") < body.index("for pattern in blocked")


# ── the prompt half: don't propose it in the first place ─────────────────────

def flat(text: str) -> str:
    """Prose wrapped across lines, as one line — so an assertion is about the words and
    not about where the paragraph happened to break."""
    return " ".join(text.split())


def skill_body() -> str:
    p = pathlib.Path(__file__).resolve().parents[1] / "app" / "skills" / "harden-server.md"
    return p.read_text()


def test_the_skill_no_longer_calls_it_safe_always():
    """The exact words that produced the incident:
    'Safe always: disable direct root PASSWORD login (PermitRootLogin prohibit-password)'."""
    body = skill_body()
    assert "Safe always: disable direct root PASSWORD login" not in body
    assert 'NOTHING here is "safe always"' in body


def test_the_skill_tells_ally_to_establish_its_own_way_in_first():
    body = skill_body()
    assert "KNOW HOW YOU GOT IN" in body
    # And before the stage that changes those settings.
    assert body.index("KNOW HOW YOU GOT IN") < body.index("STAGE 4")


def test_the_skill_corrects_the_inverted_reasoning():
    """The specific mistake: 'no key is set up, so this just closes a risky path'."""
    assert "is NOT a reason it is safe" in flat(skill_body())


def test_the_skill_says_a_surviving_session_proves_nothing():
    assert "NOT evidence the change was safe" in flat(skill_body())


def test_the_skill_checks_the_setting_that_governs_the_account_it_uses():
    """The compounding failure: it read PasswordAuthentication and reported on root."""
    body = flat(skill_body())
    assert "PasswordAuthentication` governs" in body
    assert "PermitRootLogin` governs root" in body


def test_the_server_profile_tells_ally_how_ally_connects():
    """Without this the model cannot reason about the question at all."""
    from app.services import ai_context_service

    body = inspect.getsource(ai_context_service.build_server_profile)
    assert "ServerAlly reaches this server as" in body
    assert "lock ServerAlly out" in body


def test_the_guard_does_not_lean_on_the_read_only_classifier():
    """A trap found while building this. `is_read_only_command` reads as default-deny but
    is really a DENY-list — it returns True for anything without a known mutating token, so
    it calls `ssh_set PermitRootLogin prohibit-password` READ-ONLY.

    An earlier version of the guard skipped anything that classifier called read-only, which
    waved the incident command straight through. Pinned here because the classifier's
    verdict is the tempting thing to reuse.
    """
    cmd = "ssh_set PermitRootLogin prohibit-password"
    assert ss.is_read_only_command(cmd) is True, "the classifier's blind spot has moved"
    assert ss.lockout_risk(cmd, ROOT_PW), "the guard inherited that blind spot"


def test_a_read_chained_to_a_change_is_not_a_read():
    """`grep something && ssh_set PermitRootLogin no` starts with a read verb and ends by
    locking us out."""
    assert ss.lockout_risk("grep x /etc/hosts && ssh_set PermitRootLogin no", ROOT_PW)


def test_a_read_that_writes_is_not_a_read():
    assert ss.lockout_risk('echo "PermitRootLogin no" > /etc/ssh/sshd_config', ROOT_PW)
    assert ss.lockout_risk('echo "PasswordAuthentication no" | tee -a /etc/ssh/sshd_config',
                           USER_PW)
