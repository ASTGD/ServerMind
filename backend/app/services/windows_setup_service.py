"""Getting a Windows server ready — the one step that cannot be done for the customer.

Adding a Linux server needs nothing on the server: SSH is already listening and already
reachable. Adding a Windows server does not work that way, and the Add-Asset form used to
say nothing about it — it filled in port 5985 and hoped. When it failed the customer got a
library exception (``HTTPConnectionPool(host=…): Max retries exceeded … ConnectTimeoutError``)
which tells them nothing at all.

**Why a command is unavoidable.** You cannot switch on remote management remotely when
nothing is on yet. Nobody can — it is the shape of the problem, not a gap in the product.
What we *can* remove is the hunting: hand over the exact command, correct for a cloud VM,
scoped to our own address.

Everything below was read off a real Windows Server 2022 (`engine.vev.astgd.com`) rather
than recalled, and two readings changed what the command has to say:

* Its network profile is **Public** — normal for a cloud VM. Plain ``Enable-PSRemoting``
  refuses on a Public profile, so ``-SkipNetworkProfileCheck`` is not optional here.
* The firewall rule ``Enable-PSRemoting`` creates for the Public profile is scoped to
  **LocalSubnet** (confirmed on the box). So enabling remoting alone does NOT let us in
  from the internet — the explicit rule is genuinely required, not belt-and-braces.

``LocalAccountTokenFilterPolicy`` is deliberately NOT in the main command: it was unset on
that box and everything worked, because the account is the built-in ``Administrator``. It
is only needed for a *different* local admin, so it is offered as a note rather than a
registry change everyone is told to make.

**AWS is the exception worth knowing:** an instance managed by Systems Manager needs none of
this — no WinRM, no open port, nothing run on the box (see ``ssm_service``).
"""
from __future__ import annotations

import ipaddress
import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)

#: Left in the command when we cannot state our own address. Deliberately not a valid
#: address and deliberately not "Any" — see ``enable_command``.
ADDRESS_PLACEHOLDER = "<ServerAlly's address>"

_RULE_NAME = "WinRM from ServerAlly"


def our_address() -> str | None:
    """The address a customer's firewall should allow, or None if we cannot say.

    Read from configuration rather than detected. A detected value can be wrong — behind a
    NAT, a proxy, or a second egress — and **a wrong address here is worse than no address**:
    the customer opens their firewall to a machine that is not us, nothing works, and the
    obvious next move is to open it to everyone. Windows Remote Management exposed to the
    whole internet with password authentication is a brute-force target.

    So: state it, or admit we do not know it. Never guess.
    """
    raw = (settings.SERVERALLY_EGRESS_IP or "").strip()
    if not raw:
        return None
    try:
        ipaddress.ip_address(raw)
    except ValueError:
        logger.warning("SERVERALLY_EGRESS_IP is not a valid IP address: %r", raw)
        return None
    return raw


def enable_command(port: int = 5985, address: str | None = None) -> dict:
    """The PowerShell to run once on the Windows server, as Administrator.

    Two statements, and both are needed on a cloud VM:

    1. ``Enable-PSRemoting -Force -SkipNetworkProfileCheck`` — starts WinRM and sets it to
       start at boot. The skip flag is required because a cloud VM's network is Public.
    2. An inbound rule for our address — because the rule step 1 creates for the Public
       profile only allows the **local subnet**, which we are not on.

    The rule is scoped to one address whenever we know it. When we do not, the address is
    left as a placeholder the customer must replace: generating ``-RemoteAddress Any`` would
    be us telling somebody to publish their Windows login to the internet.
    """
    port = int(port)
    scoped = bool(address)
    who = address or ADDRESS_PLACEHOLDER
    lines = [
        "Enable-PSRemoting -Force -SkipNetworkProfileCheck",
        (f'New-NetFirewallRule -DisplayName "{_RULE_NAME}" -Direction Inbound '
         f'-Protocol TCP -LocalPort {port} -RemoteAddress {who} -Action Allow'),
    ]
    return {
        "command": "\n".join(lines),
        "address": address,
        "scoped": scoped,
        "note": (
            "Run this once in PowerShell as Administrator, on the Windows server itself "
            "(through Remote Desktop or your provider's console)."
        ),
        "unscoped_warning": None if scoped else (
            f"Replace {ADDRESS_PLACEHOLDER} with the address ServerAlly connects from. "
            f"Do not use Any — that would let anyone on the internet reach this server's "
            f"login."
        ),
        "other_admin_note": (
            "Only if you sign in with a local administrator account that is NOT the "
            "built-in Administrator, also run:\n"
            "New-ItemProperty -Path "
            "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System "
            "-Name LocalAccountTokenFilterPolicy -Value 1 -PropertyType DWord -Force"
        ),
    }


#: Real failures, captured from a live Windows Server 2022 rather than imagined. Each entry
#: is (pattern, what happened, what to do). Order matters: the first match wins, so the
#: specific causes come before the general ones.
_CAUSES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"credentials were rejected", re.I),
     "The username or password was refused by Windows.",
     "Check both, and include the domain if this server is in one (DOMAIN\\user). "
     "The account must be an administrator on that server."),

    (re.compile(r"invalid Message Integrity Check|SpnegoError", re.I),
     "The Windows login handshake failed part-way through.",
     "Try again. If it keeps happening, restart the WinRM service on the server "
     "(Restart-Service WinRM)."),

    (re.compile(r"Code 401", re.I),
     "Windows accepted the connection but refused the sign-in.",
     "Check the username and password, and that the account is an administrator."),

    (re.compile(r"Code 5\d\d", re.I),
     "Windows Remote Management answered with an error of its own.",
     "On the server, run: Restart-Service WinRM — then try again."),

    (re.compile(r"Connection refused|ConnectionRefused", re.I),
     "The server answered, but nothing is listening on that port.",
     "Windows Remote Management is not switched on. Run the setup command on the server, "
     "then try again."),

    (re.compile(r"CertificateError|SSLError|certificate verify", re.I),
     "The secure connection to the server could not be established.",
     "Port 5986 needs a certificate WinRM is configured to use. Port 5985 is the usual "
     "choice for a server on a private network or behind a firewall rule."),

    (re.compile(r"Name or service not known|nodename nor servname|getaddrinfo", re.I),
     "That address could not be looked up.",
     "Check the host name or IP address."),

    # Last, because a firewall that DROPS looks exactly like a server that is switched off.
    (re.compile(r"timed out|Max retries exceeded|ConnectTimeout", re.I),
     "ServerAlly could not reach that port at all.",
     "Either the server is off, or its firewall is blocking us. Run the setup command on "
     "the server — the rule it adds is what lets ServerAlly in."),
]


def explain_failure(raw: str, host: str = "", port: int = 0) -> str:
    """Turn a WinRM exception into something a person can act on.

    The raw text is kept on the end rather than thrown away — a support conversation needs
    the real error, and hiding it entirely would trade one unhelpful message for another.
    An unrecognised failure is passed through unchanged instead of being labelled with a
    guess, because a confident wrong explanation sends somebody to fix the wrong thing.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    for pattern, what, fix in _CAUSES:
        if pattern.search(text):
            where = f" ({host}:{port})" if host and port else ""
            return f"{what}{where} {fix}"
    return text
