"""Firewall management — open and close ports without locking yourself out.

The playbooks can *set up* a firewall; there has never been a screen to see what is
open or to change it. That gap matters because the usual way people manage a firewall
is to SSH in and type `ufw` commands — which is exactly the situation where one wrong
command ends the session and every future one.

**The lockout guard is the feature.** Everything else here is plumbing around one
question: could this change stop us reaching the server? A firewall is the only thing
in ServerAlly that can make a server permanently unreachable through its own success —
the command runs, reports OK, and the connection is gone for good. Recovering needs
the provider's console, which many customers do not know they have.

So `lockout_risk` is consulted before every change and **fails closed**: anything it
cannot confidently prove safe is refused, not warned about. It knows the port SSH is
actually on and the address we are actually connecting from (read from the server's own
view of the connection, not assumed), because a rule that looks like it allows SSH on
port 22 is no help on a server whose SSH listens on 2222.

Reading is a fixed, read-only probe bundle authored here — never a user string, never
AI-chosen — the same shape as the metrics, security, threat and service probes.
"""
from __future__ import annotations

import ipaddress
import re
import shlex
from dataclasses import dataclass, field

SENTINEL = "___SM_FW___"

# Two managers cover essentially every server we support. Raw iptables/nftables is
# deliberately NOT managed: hand-written rule sets have ordering and chain semantics
# that a generic editor gets wrong, and getting them wrong here means an unreachable
# server. We report what is there and say honestly that we do not manage it.
UFW = "ufw"
FIREWALLD = "firewalld"
NONE = "none"
UNMANAGED = "unmanaged"

MAX_RULES = 200


class InvalidRule(ValueError):
    """The rule is not something we are willing to put in a firewall command."""


class WouldLockOut(Exception):
    """The change would, or might, end our own access to the server."""


@dataclass
class Rule:
    """One allow/deny rule, in the terms both managers share."""
    action: str                    # allow | deny
    port: str                      # "22", "80,443", "6000:6010"
    protocol: str = "tcp"          # tcp | udp
    source: str = ""               # "" = anywhere
    comment: str = ""
    raw: str = ""                  # what the firewall itself printed
    # firewalld writes the same opening once per address family. We show one row but
    # must remove BOTH, or "closed port 80" leaves it open over IPv6 — a hole the
    # customer believes they have shut.
    raws: list[str] = field(default_factory=list)
    # ufw numbers its rules and deletes by number; firewalld deletes by value.
    index: int | None = None


@dataclass
class FirewallState:
    manager: str = NONE
    active: bool = False
    default_incoming: str = ""     # allow | deny | reject | ""
    rules: list[Rule] = field(default_factory=list)
    # How the server sees US. The whole lockout guard rests on these two.
    ssh_port: int = 22
    our_ip: str = ""
    note: str = ""                 # plain-language explanation when unmanaged


# ── validation ────────────────────────────────────────────────────────────────
_PORT_RE = re.compile(r"^\d{1,5}(?::\d{1,5})?$")


def valid_port(spec: str) -> str:
    """A single port, or a range. Lists are split by the caller into separate rules.

    Refused rather than escaped: the safest string to hand a shell is one that was
    never user-controlled. Nothing here can carry a space, a semicolon or a quote.
    """
    raw = (spec or "").strip()
    if not _PORT_RE.match(raw):
        raise InvalidRule(
            f"“{spec}” is not a port. Use a number like 443, or a range like 6000:6010.")
    parts = [int(p) for p in raw.split(":")]
    for p in parts:
        if not 1 <= p <= 65535:
            raise InvalidRule(f"Port {p} is out of range — ports run from 1 to 65535.")
    if len(parts) == 2 and parts[0] >= parts[1]:
        raise InvalidRule("The start of a port range must be lower than the end.")
    return raw


def valid_protocol(proto: str) -> str:
    p = (proto or "tcp").strip().lower()
    if p not in ("tcp", "udp"):
        raise InvalidRule("Protocol must be tcp or udp.")
    return p


def valid_source(source: str) -> str:
    """An address or network, or empty for anywhere.

    Parsed as a real network rather than pattern-matched, so "10.0.0.0/8; rm -rf /"
    cannot survive as something that merely looks close enough.
    """
    raw = (source or "").strip()
    if not raw or raw.lower() in ("any", "anywhere", "0.0.0.0/0"):
        return ""
    try:
        return str(ipaddress.ip_network(raw, strict=False))
    except ValueError as exc:
        raise InvalidRule(
            f"“{source}” is not an address or network. Use something like 203.0.113.10 "
            "or 10.0.0.0/24, or leave it blank for anywhere.") from exc


def valid_action(action: str) -> str:
    a = (action or "").strip().lower()
    if a not in ("allow", "deny"):
        raise InvalidRule("A rule either allows or denies.")
    return a


# ── the guard ─────────────────────────────────────────────────────────────────
def _covers_ssh(rule: Rule, state: FirewallState) -> bool:
    """Would this rule keep our SSH working?"""
    if rule.action != "allow" or rule.protocol not in ("tcp", ""):
        return False
    if not _port_covers(rule.port, state.ssh_port):
        return False
    if not rule.source:
        return True                      # from anywhere — covers us
    if not state.our_ip:
        return False                     # we cannot prove it covers us; assume not
    try:
        return ipaddress.ip_address(state.our_ip) in ipaddress.ip_network(rule.source,
                                                                         strict=False)
    except ValueError:
        return False


def _port_covers(spec: str, port: int) -> bool:
    spec = (spec or "").strip()
    if not spec:
        return False
    for part in spec.replace(" ", "").split(","):
        if ":" in part:
            lo, _, hi = part.partition(":")
            if lo.isdigit() and hi.isdigit() and int(lo) <= port <= int(hi):
                return True
        elif part.isdigit() and int(part) == port:
            return True
    return False


def ssh_stays_open(state: FirewallState, *, without: Rule | None = None,
                   plus: Rule | None = None, default_incoming: str | None = None) -> bool:
    """Would SSH still be reachable after this change?

    Answers the question for the state as it WOULD be, not as it is — which is why
    removing a rule and adding one both go through the same function.
    """
    rules = [r for r in state.rules if r is not without]
    if plus is not None:
        rules = rules + [plus]
    policy = (default_incoming or state.default_incoming or "").lower()

    # An explicit deny that matches our SSH beats any allow in both managers' semantics
    # once it is earlier in the list; treating any matching deny as fatal is the
    # cautious reading, and caution is the right bias when the cost is a dead server.
    for r in rules:
        if r.action == "deny" and _port_covers(r.port, state.ssh_port) \
                and r.protocol in ("tcp", ""):
            if not r.source or (state.our_ip and _covers_ssh(
                    Rule("allow", r.port, r.protocol, r.source), state)):
                return False

    if policy in ("deny", "reject"):
        return any(_covers_ssh(r, state) for r in rules)
    # Default-allow: nothing is blocking us unless a deny matched above.
    return True


def lockout_risk(state: FirewallState, *, without: Rule | None = None,
                 plus: Rule | None = None, default_incoming: str | None = None,
                 enabling: bool = False) -> str:
    """Empty string if the change is safe. Otherwise, why it is refused.

    Fails closed by design. A firewall change that we cannot prove keeps SSH open is
    refused — the alternative is a warning the customer clicks through once and a
    server nobody can reach.
    """
    # Turning a firewall ON applies the default policy for the first time, which is
    # where most real lockouts happen: `ufw enable` with no SSH rule cuts the session
    # that typed it.
    if enabling and not ssh_stays_open(state, without=without, plus=plus,
                                       default_incoming=default_incoming or "deny"):
        return (f"Turning the firewall on now would block SSH on port {state.ssh_port} "
                "and you would lose access to this server. Add a rule allowing "
                f"port {state.ssh_port} first.")

    if not enabling and not state.active:
        return ""                        # firewall is off; nothing can lock us out yet

    if not ssh_stays_open(state, without=without, plus=plus,
                          default_incoming=default_incoming):
        if without is not None:
            return (f"That rule is what keeps SSH open on port {state.ssh_port}. "
                    "Removing it would lock you out of this server.")
        if default_incoming is not None:
            return (f"Blocking everything by default would cut SSH on port "
                    f"{state.ssh_port}. Add a rule allowing it first.")
        return (f"That change would block SSH on port {state.ssh_port} and you would "
                "lose access to this server.")
    return ""


# ── reading the server ────────────────────────────────────────────────────────
def discovery_probe(ssh_port: int) -> str:
    """One read-only round trip: which manager, is it on, what are the rules, who are we.

    `$SSH_CONNECTION` is read rather than assumed, because the address the server sees
    is the one its firewall will match — which is not necessarily the address we think
    we are coming from once NAT is in the way.
    """
    s = SENTINEL
    return (
        f'echo "{s}WHOAMI"; echo "${{SSH_CONNECTION:-}}"; echo "sshport={ssh_port}"; '
        f'echo "{s}UFW"; command -v ufw >/dev/null 2>&1 && '
        f'  (ufw status verbose numbered 2>/dev/null || echo "__needs_root__"); '
        f'echo "{s}FIREWALLD"; systemctl is-active firewalld 2>/dev/null; '
        f'  command -v firewall-cmd >/dev/null 2>&1 && '
        f'  (firewall-cmd --list-all 2>/dev/null || true); '
        f'echo "{s}NFT"; (nft list ruleset 2>/dev/null | head -5; '
        f'  iptables -S 2>/dev/null | head -5) | head -10; '
        f'echo "{s}END"'
    )


def _sections(out: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    current = ""
    for line in (out or "").splitlines():
        if line.startswith(SENTINEL):
            current = line[len(SENTINEL):].strip()
            parts[current] = ""
        elif current:
            parts[current] += line + "\n"
    return parts


_UFW_RULE = re.compile(
    r"^\[\s*(?P<n>\d+)\]\s+(?P<port>\S+?)(?:/(?P<proto>tcp|udp))?\s+"
    r"(?P<action>ALLOW IN|DENY IN|REJECT IN|ALLOW|DENY|REJECT)\s+(?P<src>.+?)\s*$",
    re.I)


def _parse_ufw(text: str) -> tuple[bool, str, list[Rule]]:
    active = bool(re.search(r"Status:\s*active", text, re.I))
    policy = ""
    m = re.search(r"Default:\s*(\w+)\s*\(incoming\)", text, re.I)
    if m:
        policy = m.group(1).lower()
    rules: list[Rule] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        # ufw prints a v6 twin of every rule; showing both would double the list for
        # something the customer did not ask for and cannot act on separately.
        if "(v6)" in line:
            continue
        m = _UFW_RULE.match(line)
        if not m:
            continue
        action = "allow" if m.group("action").lower().startswith("allow") else "deny"
        src = (m.group("src") or "").strip()
        if src.lower() in ("anywhere", "anywhere (v6)", "any"):
            src = ""
        rules.append(Rule(action=action, port=m.group("port"),
                          protocol=(m.group("proto") or "tcp").lower(),
                          source=src, raw=line, index=int(m.group("n"))))
        if len(rules) >= MAX_RULES:
            break
    return active, policy, rules


# A firewalld "service" is a named port set. The mapping matters for the guard: a
# server whose SSH is allowed only as `services: ssh` still has SSH open, and not
# knowing that would make us refuse changes that are perfectly safe.
_FIREWALLD_SERVICES = {
    "ssh": ("22", "tcp"), "http": ("80", "tcp"), "https": ("443", "tcp"),
    "ftp": ("21", "tcp"), "smtp": ("25", "tcp"), "smtps": ("465", "tcp"),
    "smtp-submission": ("587", "tcp"), "imap": ("143", "tcp"), "imaps": ("993", "tcp"),
    "pop3": ("110", "tcp"), "pop3s": ("995", "tcp"), "dns": ("53", "udp"),
    "mysql": ("3306", "tcp"), "postgresql": ("5432", "tcp"),
}

# `rule family="ipv4" source address="1.2.3.4/32" port port="80" protocol="tcp" accept`
_RICH = re.compile(
    r'rule\s+family="(?P<fam>ipv[46])"'
    r'(?:\s+source\s+address="(?P<src>[^"]+)")?'
    r'.*?port\s+port="(?P<port>[^"]+)"\s+protocol="(?P<proto>tcp|udp)"'
    r'\s+(?P<action>accept|reject|drop)', re.I)

# Horizontal whitespace only. `\s*` here would span the newline into the NEXT line —
# which is exactly what it did against a real server: an empty `ports:` swallowed the
# following `protocols:` line and produced rules that did not exist.
_H = r"[^\S\r\n]*"


def _parse_firewalld(text: str) -> tuple[bool, str, list[Rule]]:
    active = text.strip().startswith("active")
    rules: list[Rule] = []
    seen: set[tuple] = set()

    by_key: dict[tuple, Rule] = {}

    def add(rule: Rule) -> None:
        # firewalld writes an ipv4 and an ipv6 rule for the same opening. Showing both
        # doubles the list with something the customer cannot act on separately — but
        # every raw form is kept, because removal has to close all of them.
        key = (rule.action, rule.port, rule.protocol, rule.source)
        if rule.raw:
            rule.raws = [rule.raw]
        if key in by_key:
            if rule.raw and rule.raw not in by_key[key].raws:
                by_key[key].raws.append(rule.raw)
            return
        by_key[key] = rule
        seen.add(key)
        rules.append(rule)

    m = re.search(rf"^{_H}ports:{_H}(.*)$", text, re.M)
    if m:
        for token in m.group(1).split():
            port, _, proto = token.partition("/")
            add(Rule("allow", port, (proto or "tcp").lower(), raw=token))

    m = re.search(rf"^{_H}services:{_H}(.*)$", text, re.M)
    if m:
        for name in m.group(1).split():
            port, proto = _FIREWALLD_SERVICES.get(name, ("", "tcp"))
            add(Rule("allow", port, proto, comment=f"service: {name}", raw=name))

    # On a panel-managed server this is where everything actually is — CyberPanel puts
    # every opening in a rich rule and leaves `ports:` empty. Reading only `ports:`
    # showed three entries for a server with thirty openings.
    for m in _RICH.finditer(text):
        src = (m.group("src") or "").strip()
        if src in ("0.0.0.0/0", "::/0"):
            src = ""
        add(Rule("allow" if m.group("action").lower() == "accept" else "deny",
                 m.group("port"), m.group("proto").lower(), src, raw=m.group(0)))

    # firewalld's default for the public zone is to reject what is not listed.
    return active, "deny" if active else "", rules[:MAX_RULES]


def parse_probe(out: str, *, ssh_port: int = 22) -> FirewallState:
    sec = _sections(out)
    st = FirewallState(ssh_port=ssh_port)

    who = sec.get("WHOAMI", "")
    # "<client ip> <client port> <server ip> <server port>"
    first = who.strip().splitlines()[0].strip() if who.strip() else ""
    if first and not first.startswith("sshport="):
        st.our_ip = first.split()[0]
    m = re.search(r"sshport=(\d+)", who)
    if m:
        st.ssh_port = int(m.group(1))

    ufw = sec.get("UFW", "").strip()
    fwd = sec.get("FIREWALLD", "").strip()

    if ufw and "__needs_root__" not in ufw and "Status:" in ufw:
        st.manager = UFW
        st.active, st.default_incoming, st.rules = _parse_ufw(ufw)
        return st
    if fwd.startswith("active"):
        st.manager = FIREWALLD
        st.active, st.default_incoming, st.rules = _parse_firewalld(fwd)
        return st

    nft = sec.get("NFT", "").strip()
    if "__needs_root__" in ufw:
        st.manager = UNMANAGED
        st.note = ("We could not read the firewall — this usually means ServerAlly is "
                   "connecting as a user without permission to run firewall commands.")
    elif nft and len([l for l in nft.splitlines() if l.strip()]) > 2:
        st.manager = UNMANAGED
        st.active = True
        st.note = ("This server's rules are written directly in iptables or nftables. "
                   "We show them but do not change them — hand-written rule sets have "
                   "ordering that a generic editor gets wrong, and getting it wrong "
                   "here means a server nobody can reach.")
    else:
        st.manager = NONE
        st.note = ("No firewall is set up on this server. Everything a program listens "
                   "on is reachable from the internet.")
    return st


# ── writing ───────────────────────────────────────────────────────────────────
def add_command(state: FirewallState, rule: Rule) -> str:
    q = shlex.quote
    if state.manager == UFW:
        parts = ["ufw", rule.action]
        if rule.source:
            parts += ["from", q(rule.source), "to", "any", "port", q(rule.port),
                      "proto", rule.protocol]
        else:
            parts += [q(f"{rule.port}/{rule.protocol}")]
        cmd = " ".join(parts)
        if rule.comment:
            cmd += f" comment {q(rule.comment[:120])}"
        return cmd
    if state.manager == FIREWALLD:
        if rule.action == "deny":
            raise InvalidRule(
                "This server uses firewalld, which blocks everything by default — "
                "there is nothing to deny. Remove the rule that allows it instead.")
        if rule.source:
            rich = (f'rule family="ipv4" source address="{rule.source}" '
                    f'port port="{rule.port}" protocol="{rule.protocol}" accept')
            return (f"firewall-cmd --permanent --add-rich-rule={q(rich)} && "
                    "firewall-cmd --reload")
        return (f"firewall-cmd --permanent --add-port={q(f'{rule.port}/{rule.protocol}')}"
                " && firewall-cmd --reload")
    raise InvalidRule("We do not change the firewall on this server.")


def remove_command(state: FirewallState, rule: Rule) -> str:
    q = shlex.quote
    if state.manager == UFW:
        if rule.index is None:
            raise InvalidRule("That rule cannot be identified well enough to remove.")
        # ufw renumbers after every delete, so deleting by number is only correct
        # against the listing we just read — which is why the caller re-reads first.
        return f"ufw --force delete {int(rule.index)}"
    if state.manager == FIREWALLD:
        if rule.comment.startswith("service: "):
            svc = rule.comment.split(": ", 1)[1]
            return (f"firewall-cmd --permanent --remove-service={q(svc)} && "
                    "firewall-cmd --reload")
        rich = [r for r in (rule.raws or ([rule.raw] if rule.raw else []))
                if r.strip().startswith("rule ")]
        if rich:
            # Removed by the exact text firewalld printed. firewall-cmd matches a rich
            # rule literally, so a rebuilt-from-parts string that differs by one
            # attribute silently removes nothing and reports success.
            parts = [f"firewall-cmd --permanent --remove-rich-rule={q(r.strip())}"
                     for r in rich]
            return " && ".join(parts) + " && firewall-cmd --reload"
        if rule.source:
            built = (f'rule family="ipv4" source address="{rule.source}" '
                     f'port port="{rule.port}" protocol="{rule.protocol}" accept')
            return (f"firewall-cmd --permanent --remove-rich-rule={q(built)} && "
                    "firewall-cmd --reload")
        return (f"firewall-cmd --permanent "
                f"--remove-port={q(f'{rule.port}/{rule.protocol}')} && "
                "firewall-cmd --reload")
    raise InvalidRule("We do not change the firewall on this server.")


def enable_command(state: FirewallState) -> str:
    if state.manager == UFW:
        return "ufw --force enable"
    if state.manager == FIREWALLD:
        return "systemctl enable --now firewalld"
    raise InvalidRule("We do not change the firewall on this server.")


def disable_command(state: FirewallState) -> str:
    """Turning a firewall OFF cannot lock anyone out — it only opens things.

    It is still a real reduction in protection, so the caller confirms it and it is
    recorded; but it is not the guard's business.
    """
    if state.manager == UFW:
        return "ufw --force disable"
    if state.manager == FIREWALLD:
        return "systemctl disable --now firewalld"
    raise InvalidRule("We do not change the firewall on this server.")


# ── plain language for the screen ─────────────────────────────────────────────
_WELL_KNOWN = {
    "22": "SSH — how you and ServerAlly connect",
    "80": "Web traffic (http)",
    "443": "Secure web traffic (https)",
    "3306": "MySQL / MariaDB database",
    "5432": "PostgreSQL database",
    "6379": "Redis",
    "27017": "MongoDB",
    "25": "Outgoing mail (smtp)",
    "587": "Mail submission",
    "993": "Mail (imaps)",
    "21": "FTP",
    "3389": "Remote Desktop",
    "8090": "CyberPanel",
    "2083": "cPanel",
    "8443": "Plesk",
    "2222": "DirectAdmin, or SSH on some servers",
}


def describe(rule: Rule, state: FirewallState) -> str:
    """What this rule means, for someone who does not know what a port is."""
    known = _WELL_KNOWN.get(rule.port.split("/")[0]) if rule.port else None
    if rule.port and rule.port == str(state.ssh_port) and not known:
        known = "SSH — how you and ServerAlly connect"
    if not known and rule.comment.startswith("service: "):
        # A named service we do not have a port for. Naming it beats "port ".
        known = rule.comment.split(": ", 1)[1]
    what = known or (f"port {rule.port}" if rule.port else "an unnamed opening")
    where = f" from {rule.source}" if rule.source else " from anywhere"
    return f"{'Open' if rule.action == 'allow' else 'Blocked'}: {what}{where}"
