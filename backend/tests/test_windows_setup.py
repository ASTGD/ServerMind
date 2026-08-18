"""Getting a Windows server ready — the command, and saying what went wrong.

Adding a Linux server needs nothing on the server. Adding a Windows one does, and the form
used to say nothing about it: it filled in port 5985 and hoped. When it failed the customer
was handed a library exception.

Every fact the command depends on was READ off a real Windows Server 2022
(`engine.vev.astgd.com`), not recalled, and two of those readings changed what it has to do:

    Get-NetConnectionProfile        -> NetworkCategory = Public
    <the Public WinRM rule>         -> RemoteAddress   = LocalSubnet

The first means plain `Enable-PSRemoting` refuses. The second means enabling remoting does
NOT let us in from the internet — the explicit rule is genuinely required.

The failure strings are the real ones too, captured by pointing the live service at a closed
port, an unroutable host, a wrong password and a missing account. Inventing them is how a
parser ends up handling only what its author imagined — the exact way BUG-022 survived.
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.services import windows_setup_service as ws

#: Verbatim from a live Windows Server 2022. Do not tidy these.
REAL_ERRORS = {
    "closed port":
        "HTTPConnectionPool(host='23.106.52.144', port=5987): Max retries exceeded with url: "
        "/wsman (Caused by ConnectTimeoutError(<HTTPConnection(host='23.106.52.144', "
        "port=5987)>, 'Connection to 23.106.52.144 timed out. (connect timeout=70)'))",
    "unroutable host":
        "HTTPConnectionPool(host='192.0.2.1', port=5985): Max retries exceeded with url: "
        "/wsman (Caused by ConnectTimeoutError(<HTTPConnection(host='192.0.2.1', port=5985)>, "
        "'Connection to 192.0.2.1 timed out. (connect timeout=70)'))",
    "wrong password": "the specified credentials were rejected by the server",
    "no such account": "the specified credentials were rejected by the server",
    "interleaved auth": "SpnegoError (6): A token had an invalid Message Integrity Check (MIC)",
    "winrm errored": "Bad HTTP response returned from server. Code 500",
}


def statements(command: str) -> list[str]:
    """The lines of the command that would actually RUN.

    A test that only asks whether text appears accepts a line commented out with `#` — the
    same trap that has repeatedly caught this repo from the other direction, where a search
    matched a comment instead of code. PowerShell here is generated, so the check should
    read it the way PowerShell would.
    """
    return [ln.strip() for ln in command.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


# ── the command ──────────────────────────────────────────────────────────────

def test_it_skips_the_network_profile_check():
    """Read off the real box: a cloud VM's profile is Public, and `Enable-PSRemoting`
    refuses there. Without this flag the command fails on exactly the servers it targets."""
    runs = statements(ws.enable_command(5985, "192.3.193.50")["command"])
    assert any("-SkipNetworkProfileCheck" in ln for ln in runs), runs


def test_it_opens_the_firewall_because_enabling_remoting_is_not_enough():
    """Also read off the box: the rule `Enable-PSRemoting` creates for the Public profile is
    scoped to LocalSubnet. We are not on the customer's local subnet, so remoting alone
    leaves us locked out — which is the whole reason this step exists."""
    runs = statements(ws.enable_command(5985, "192.3.193.50")["command"])
    rule = [ln for ln in runs if "New-NetFirewallRule" in ln]
    assert rule, f"no firewall rule that would actually run: {runs}"
    assert "-LocalPort 5985" in rule[0]
    assert "-RemoteAddress 192.3.193.50" in rule[0]


def test_the_rule_is_never_open_to_everyone():
    """The safety property, and the reason the address is never guessed.

    Windows Remote Management reachable from the whole internet, with password
    authentication, is a brute-force target. We must not be the ones who told somebody to
    do that — not when we know our address, and not when we don't.
    """
    for address in ("192.3.193.50", None):
        cmd = ws.enable_command(5985, address)["command"]
        assert not re.search(r"-RemoteAddress\s+(Any|\*|0\.0\.0\.0)", cmd, re.I), cmd


def test_an_unknown_address_is_admitted_rather_than_invented():
    """A wrong address is worse than no address: nothing works, and the obvious next move
    is to open the firewall to everyone."""
    out = ws.enable_command(5985, None)
    assert out["scoped"] is False
    assert ws.ADDRESS_PLACEHOLDER in out["command"]
    assert out["unscoped_warning"] and "Any" in out["unscoped_warning"]


def test_a_known_address_carries_no_warning():
    out = ws.enable_command(5985, "192.3.193.50")
    assert out["scoped"] is True and out["unscoped_warning"] is None


def test_the_registry_change_is_a_note_and_not_in_the_command():
    """`LocalAccountTokenFilterPolicy` was UNSET on the real box and everything worked,
    because the account is the built-in Administrator. It only matters for a different local
    admin — so it is offered when relevant, not handed to everyone as a registry edit that
    weakens a protection they may not need to weaken."""
    out = ws.enable_command(5985, "192.3.193.50")
    assert "LocalAccountTokenFilterPolicy" not in out["command"]
    assert "LocalAccountTokenFilterPolicy" in out["other_admin_note"]


def test_the_port_asked_for_is_the_port_opened():
    runs = statements(ws.enable_command(5986, "192.3.193.50")["command"])
    assert any("-LocalPort 5986" in ln for ln in runs), runs


# ── our own address ──────────────────────────────────────────────────────────

def test_our_address_comes_from_configuration_not_detection(monkeypatch):
    monkeypatch.setattr(ws.settings, "SERVERALLY_EGRESS_IP", "192.3.193.50")
    assert ws.our_address() == "192.3.193.50"


def test_an_unset_address_is_none_rather_than_something_plausible(monkeypatch):
    monkeypatch.setattr(ws.settings, "SERVERALLY_EGRESS_IP", "")
    assert ws.our_address() is None


@pytest.mark.parametrize("bad", ["not-an-ip", "192.3.193", "999.1.1.1", "0.0.0.0/0", "  "])
def test_a_malformed_configured_address_is_refused_not_printed(monkeypatch, bad):
    """A typo in configuration would otherwise be pasted into a customer's firewall rule."""
    monkeypatch.setattr(ws.settings, "SERVERALLY_EGRESS_IP", bad)
    assert ws.our_address() is None


def test_it_is_never_detected_over_the_network():
    """Detection can be wrong behind a NAT or a second egress, and it makes generating the
    command depend on an outside service being up."""
    src = inspect.getsource(ws.our_address)
    for reached_out in ("requests", "urllib", "httpx", "socket"):
        assert reached_out not in src, f"our_address() reaches for {reached_out}"


# ── saying what went wrong ───────────────────────────────────────────────────

def test_a_closed_firewall_is_explained_not_dumped():
    """The message a customer actually got. It names no cause and suggests no action."""
    said = ws.explain_failure(REAL_ERRORS["closed port"], "23.106.52.144", 5987)
    assert "HTTPConnectionPool" not in said and "ConnectTimeoutError" not in said
    assert "could not reach" in said.lower()
    assert "firewall" in said.lower()


def test_a_rejected_login_says_so():
    said = ws.explain_failure(REAL_ERRORS["wrong password"])
    assert "username or password" in said.lower()
    assert "administrator" in said.lower()


def test_a_closed_port_is_not_reported_as_a_password_problem():
    """The two most common failures must not be confused — they send the customer to
    completely different places."""
    closed = ws.explain_failure(REAL_ERRORS["closed port"]).lower()
    assert "password" not in closed


def test_the_handshake_failure_gets_its_own_answer():
    said = ws.explain_failure(REAL_ERRORS["interleaved auth"])
    assert "handshake" in said.lower() and "WinRM" in said


def test_winrms_own_error_points_at_the_service():
    said = ws.explain_failure(REAL_ERRORS["winrm errored"])
    assert "Restart-Service WinRM" in said


@pytest.mark.parametrize("label", sorted(REAL_ERRORS))
def test_every_real_failure_is_recognised(label):
    """None of the strings a live box actually produced may fall through unexplained."""
    said = ws.explain_failure(REAL_ERRORS[label])
    assert said != REAL_ERRORS[label], f"{label!r} is passed through with no explanation"


def test_an_unknown_failure_is_passed_through_rather_than_guessed_at():
    """A confident wrong explanation sends somebody to fix the wrong thing. Better to show
    the real error than to invent a cause for it."""
    odd = "Some failure nobody has seen before: qzx-4471"
    assert ws.explain_failure(odd) == odd


def test_nothing_is_said_about_nothing():
    assert ws.explain_failure("") == "" and ws.explain_failure(None) == ""


# ── the wiring ───────────────────────────────────────────────────────────────

def test_the_connection_test_explains_instead_of_dumping():
    from app.services import winrm_service

    body = "\n".join(ln for ln in inspect.getsource(winrm_service.test_connection).splitlines()
                     if not ln.strip().startswith("#"))
    assert "explain_failure(" in body
    assert "str(exc)}" not in body, "the raw exception still reaches the customer"


def test_the_setup_route_is_registered_before_the_id_route():
    """A literal path declared after a path parameter of the same depth is swallowed by it.
    That is how `/resize` and `/destroy` silently stopped existing in the cloud lifecycle
    work — the two most consequential routes in that feature."""
    from app.routers import servers as r

    src = inspect.getsource(r)
    assert src.index('"/windows-setup"') < src.index('"/{server_id}"')
