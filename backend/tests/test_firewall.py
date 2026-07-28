"""Firewall — the properties that stop a change from making a server unreachable.

A firewall is the only thing here that can end access through its own success: the
command runs, reports OK, and the server is gone. So the lockout guard is tested harder
than everything else, including the cases where it must refuse something that *looks*
fine.
"""
from __future__ import annotations

import shlex

import pytest

from app.services import firewall_service as fw


def state(**kw) -> fw.FirewallState:
    base = dict(manager=fw.UFW, active=True, default_incoming="deny",
                ssh_port=22, our_ip="203.0.113.9")
    base.update(kw)
    return fw.FirewallState(**base)


SSH_ANY = fw.Rule("allow", "22", "tcp", "", index=1)
WEB = fw.Rule("allow", "80", "tcp", "", index=2)


# ── the guard: removing the rule that keeps us in ────────────────────────────
def test_removing_the_only_ssh_rule_is_refused():
    s = state(rules=[SSH_ANY, WEB])
    why = fw.lockout_risk(s, without=SSH_ANY)
    assert why and "lock you out" in why


def test_removing_an_ordinary_rule_is_allowed():
    s = state(rules=[SSH_ANY, WEB])
    assert fw.lockout_risk(s, without=WEB) == ""


def test_ssh_on_a_nonstandard_port_is_understood():
    """A rule allowing 22 is no help when SSH listens on 2222 — the guard reads the
    port the server is actually using, not the one everyone assumes."""
    s = state(ssh_port=2222, rules=[fw.Rule("allow", "22", "tcp", "", index=1),
                                    fw.Rule("allow", "2222", "tcp", "", index=2)])
    assert fw.lockout_risk(s, without=s.rules[0]) == "", "port 22 is not our way in"
    assert fw.lockout_risk(s, without=s.rules[1]), "2222 is, and must be protected"


def test_a_rule_from_someone_elses_address_does_not_count_as_ours():
    """An allow scoped to another office keeps SSH open for THEM. Removing our own
    rule still locks us out, and the guard must not be fooled by the port matching."""
    s = state(rules=[fw.Rule("allow", "22", "tcp", "198.51.100.0/24", index=1),
                     fw.Rule("allow", "22", "tcp", "203.0.113.0/24", index=2)])
    assert fw.lockout_risk(s, without=s.rules[1]), "that was the rule covering us"
    assert fw.lockout_risk(s, without=s.rules[0]) == ""


def test_a_rule_for_our_own_network_does_count():
    s = state(rules=[fw.Rule("allow", "22", "tcp", "203.0.113.0/24", index=1)])
    assert fw.lockout_risk(s, without=s.rules[0])


def test_when_we_cannot_tell_where_we_are_coming_from_a_scoped_rule_is_not_trusted():
    """Fails closed: an unknown source address means we cannot prove the rule covers
    us, and the cost of being wrong is an unreachable server."""
    s = state(our_ip="", rules=[fw.Rule("allow", "22", "tcp", "203.0.113.0/24", index=1)])
    assert not fw.ssh_stays_open(s)


# ── the guard: turning it on ─────────────────────────────────────────────────
def test_turning_on_a_firewall_with_no_ssh_rule_is_refused():
    """The classic lockout: `ufw enable` with default-deny cuts the session that ran it."""
    s = state(active=False, default_incoming="", rules=[WEB])
    why = fw.lockout_risk(s, enabling=True)
    assert why and "lose access" in why


def test_turning_it_on_is_fine_once_ssh_is_allowed():
    s = state(active=False, default_incoming="", rules=[SSH_ANY, WEB])
    assert fw.lockout_risk(s, enabling=True) == ""


def test_switching_the_default_to_deny_without_an_ssh_rule_is_refused():
    s = state(default_incoming="allow", rules=[WEB])
    assert fw.lockout_risk(s, default_incoming="deny")


def test_adding_a_deny_that_covers_our_ssh_is_refused():
    s = state(rules=[SSH_ANY])
    bad = fw.Rule("deny", "22", "tcp", "")
    assert fw.lockout_risk(s, plus=bad)


def test_a_deny_range_that_swallows_the_ssh_port_is_refused():
    """The one people do not see coming: 20:30 contains 22."""
    s = state(rules=[SSH_ANY])
    assert fw.lockout_risk(s, plus=fw.Rule("deny", "20:30", "tcp", ""))


def test_an_inactive_firewall_cannot_lock_anyone_out():
    s = state(active=False, default_incoming="", rules=[])
    assert fw.lockout_risk(s, without=None, plus=fw.Rule("deny", "22", "tcp", "")) == ""


# ── input that reaches a shell ───────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    "22; rm -rf /", "22 80", "$(id)", "`id`", "--force", "", "  ", "abc",
    "99999", "0", "80:70",
])
def test_a_port_that_is_not_a_port_is_refused(bad):
    with pytest.raises(fw.InvalidRule):
        fw.valid_port(bad)


@pytest.mark.parametrize("good,expect", [("22", "22"), ("6000:6010", "6000:6010"),
                                         (" 443 ", "443")])
def test_real_ports_are_accepted(good, expect):
    assert fw.valid_port(good) == expect


@pytest.mark.parametrize("bad", [
    "10.0.0.0/8; rm -rf /", "not-an-address", "1.2.3.4.5", "$(id)", "10.0.0.0/99",
])
def test_a_source_that_is_not_an_address_is_refused(bad):
    with pytest.raises(fw.InvalidRule):
        fw.valid_source(bad)


def test_anywhere_is_expressed_as_no_source():
    for word in ("", "any", "Anywhere", "0.0.0.0/0"):
        assert fw.valid_source(word) == ""


def test_everything_user_typed_reaches_the_shell_as_one_argument():
    """Re-parse the way a shell would: the value must survive as a single token and
    never become a second command."""
    s = state()
    rule = fw.Rule("allow", fw.valid_port("6000:6010"), "tcp",
                   fw.valid_source("203.0.113.0/24"), comment="app cluster")
    args = shlex.split(fw.add_command(s, rule))
    assert "6000:6010" in args and "203.0.113.0/24" in args
    assert ";" not in args and "&&" not in args


def test_a_comment_cannot_carry_a_second_command():
    s = state()
    rule = fw.Rule("allow", "80", "tcp", "", comment='x"; rm -rf / #')
    args = shlex.split(fw.add_command(s, rule))
    assert 'x"; rm -rf / #' in args, "the whole comment must be one argument"


# ── reading a real ufw listing ───────────────────────────────────────────────
UFW_OUT = """Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), disabled (routed)

     To                         Action      From
     --                         ------      ----
[ 1] 22/tcp                     ALLOW IN    Anywhere
[ 2] 80/tcp                     ALLOW IN    Anywhere
[ 3] 3306/tcp                   ALLOW IN    10.0.0.0/24
[ 4] 22/tcp (v6)                ALLOW IN    Anywhere (v6)
"""


def test_reading_ufw_rules():
    active, policy, rules = fw._parse_ufw(UFW_OUT)
    assert active and policy == "deny"
    assert [r.port for r in rules] == ["22", "80", "3306"], "the v6 twin is not shown twice"
    assert rules[2].source == "10.0.0.0/24"
    assert rules[0].index == 1


def test_the_probe_reads_who_we_are_from_the_server():
    out = (f"{fw.SENTINEL}WHOAMI\n203.0.113.9 51234 10.1.1.5 2222\nsshport=2222\n"
           f"{fw.SENTINEL}UFW\n{UFW_OUT}\n{fw.SENTINEL}FIREWALLD\n\n"
           f"{fw.SENTINEL}NFT\n\n{fw.SENTINEL}END\n")
    st = fw.parse_probe(out, ssh_port=2222)
    assert st.manager == fw.UFW and st.active
    assert st.our_ip == "203.0.113.9", "the address the server sees, not the one we assume"
    assert st.ssh_port == 2222


def test_a_server_with_no_firewall_says_so_plainly():
    out = (f"{fw.SENTINEL}WHOAMI\n\n{fw.SENTINEL}UFW\n\n{fw.SENTINEL}FIREWALLD\n"
           f"inactive\n{fw.SENTINEL}NFT\n\n{fw.SENTINEL}END\n")
    st = fw.parse_probe(out)
    assert st.manager == fw.NONE and not st.active
    assert "No firewall" in st.note


def test_hand_written_rules_are_shown_but_not_managed():
    """Editing someone's hand-built iptables generically is how a server becomes
    unreachable; we are honest about it instead."""
    nft = "\n".join(f"-A INPUT -p tcp --dport {p} -j ACCEPT" for p in (22, 80, 443))
    out = (f"{fw.SENTINEL}WHOAMI\n\n{fw.SENTINEL}UFW\n\n{fw.SENTINEL}FIREWALLD\n"
           f"inactive\n{fw.SENTINEL}NFT\n{nft}\n{fw.SENTINEL}END\n")
    st = fw.parse_probe(out)
    assert st.manager == fw.UNMANAGED
    with pytest.raises(fw.InvalidRule):
        fw.add_command(st, fw.Rule("allow", "8080", "tcp"))


def test_being_unable_to_read_the_firewall_is_not_reported_as_no_firewall():
    """Saying "no firewall" when we simply lack permission would invite someone to
    turn one on and lock themselves out of a server that was already protected."""
    out = (f"{fw.SENTINEL}WHOAMI\n\n{fw.SENTINEL}UFW\n__needs_root__\n"
           f"{fw.SENTINEL}FIREWALLD\n\n{fw.SENTINEL}NFT\n\n{fw.SENTINEL}END\n")
    st = fw.parse_probe(out)
    assert st.manager == fw.UNMANAGED and "permission" in st.note


# ── firewalld ────────────────────────────────────────────────────────────────
FIREWALLD_OUT = """active
public (active)
  target: default
  interfaces: eth0
  services: ssh dhcpv6-client
  ports: 80/tcp 443/tcp
"""


def test_reading_firewalld_including_ssh_as_a_service():
    """firewalld often allows SSH by service name, not port. Missing that would make
    the guard refuse perfectly safe changes on every RHEL server."""
    active, policy, rules = fw._parse_firewalld(FIREWALLD_OUT)
    assert active and policy == "deny"
    assert any(r.port == "22" for r in rules), "ssh service means port 22 is open"
    assert {"80", "443"} <= {r.port for r in rules}


def test_firewalld_ssh_service_satisfies_the_guard():
    _a, policy, rules = fw._parse_firewalld(FIREWALLD_OUT)
    s = state(manager=fw.FIREWALLD, default_incoming=policy, rules=rules)
    assert fw.lockout_risk(s, without=next(r for r in rules if r.port == "80")) == ""


def test_denying_on_firewalld_is_explained_rather_than_faked():
    s = state(manager=fw.FIREWALLD)
    with pytest.raises(fw.InvalidRule) as e:
        fw.add_command(s, fw.Rule("deny", "80", "tcp"))
    assert "blocks everything by default" in str(e.value)


# ── removal must be by the listing we just read ──────────────────────────────
def test_removing_a_ufw_rule_without_its_number_is_refused():
    """ufw renumbers after each delete, so a rule with no number cannot be deleted
    safely — guessing would delete a different rule."""
    with pytest.raises(fw.InvalidRule):
        fw.remove_command(state(), fw.Rule("allow", "80", "tcp"))


def test_plain_language_names_the_common_ports():
    s = state()
    assert "SSH" in fw.describe(SSH_ANY, s)
    assert "Secure web" in fw.describe(fw.Rule("allow", "443", "tcp"), s)
    assert "from 10.0.0.0/24" in fw.describe(fw.Rule("allow", "3306", "tcp", "10.0.0.0/24"), s)


def test_ssh_is_recognised_even_on_an_unusual_port():
    s = state(ssh_port=2222)
    assert "SSH" in fw.describe(fw.Rule("allow", "2222", "tcp"), s)


# ── a real panel-managed server ──────────────────────────────────────────────
# Verbatim from a live CyberPanel box. Everything it opens lives in `rich rules:`,
# `ports:` is empty, and each opening is written once per address family.
REAL_CYBERPANEL = """active
public
  target: default
  icmp-block-inversion: no
  interfaces: 
  sources: 
  services: dhcpv6-client ftp ssh
  ports: 
  protocols: 
  forward: yes
  masquerade: no
  forward-ports: 
  source-ports: 
  icmp-blocks: 
  rich rules: 
\trule family="ipv4" source address="0.0.0.0/0" port port="80" protocol="tcp" accept
\trule family="ipv6" port port="80" protocol="tcp" accept
\trule family="ipv4" source address="0.0.0.0/0" port port="443" protocol="tcp" accept
\trule family="ipv6" port port="443" protocol="tcp" accept
\trule family="ipv4" source address="0.0.0.0/0" port port="8090" protocol="tcp" accept
\trule family="ipv4" source address="0.0.0.0/0" port port="40110-40210" protocol="tcp" accept
"""


def test_a_panel_server_keeps_its_openings_in_rich_rules():
    """Found live: reading only `ports:` showed three entries for a server with thirty
    openings, because CyberPanel writes every one of them as a rich rule."""
    _active, _policy, rules = fw._parse_firewalld(REAL_CYBERPANEL)
    ports = {r.port for r in rules}
    assert {"80", "443", "8090", "40110-40210"} <= ports
    assert "22" in ports, "ssh comes from the services line"


def test_an_empty_field_does_not_swallow_the_next_line():
    """Also found live. `\\s*` after `ports:` spans the newline, so an empty `ports:`
    absorbed the following `protocols:` line and invented rules that did not exist."""
    _a, _p, rules = fw._parse_firewalld(REAL_CYBERPANEL)
    assert not any("protocols" in r.port for r in rules)
    assert all(r.port for r in rules if not r.comment.startswith("service: ")), \
        "no rule should have an empty port"


def test_the_ipv6_twin_is_not_shown_as_a_second_rule():
    _a, _p, rules = fw._parse_firewalld(REAL_CYBERPANEL)
    assert len([r for r in rules if r.port == "80"]) == 1


def test_closing_a_port_closes_it_for_ipv6_too():
    """The quiet hole: removing only the ipv4 rule leaves the port open over IPv6
    while the screen shows it as closed."""
    _a, policy, rules = fw._parse_firewalld(REAL_CYBERPANEL)
    s = state(manager=fw.FIREWALLD, default_incoming=policy, rules=rules)
    cmd = fw.remove_command(s, next(r for r in rules if r.port == "80"))
    assert cmd.count("--remove-rich-rule") == 2
    assert 'family="ipv4"' in cmd and 'family="ipv6"' in cmd


def test_a_rich_rule_is_removed_by_the_exact_text_firewalld_printed():
    """firewall-cmd matches a rich rule literally: a rebuilt string that differs by one
    attribute removes nothing and still reports success."""
    _a, policy, rules = fw._parse_firewalld(REAL_CYBERPANEL)
    s = state(manager=fw.FIREWALLD, default_incoming=policy, rules=rules)
    rule = next(r for r in rules if r.port == "8090")
    args = shlex.split(fw.remove_command(s, rule).replace("&&", " "))
    flag = next(a for a in args if a.startswith("--remove-rich-rule="))
    assert flag == f"--remove-rich-rule={rule.raws[0].strip()}", \
        "the rule text must survive verbatim, as one argument"


def test_the_guard_still_protects_ssh_on_a_real_panel_server():
    _a, policy, rules = fw._parse_firewalld(REAL_CYBERPANEL)
    s = state(manager=fw.FIREWALLD, default_incoming=policy, rules=rules)
    ssh = next(r for r in rules if r.port == "22")
    assert fw.lockout_risk(s, without=ssh), "removing the ssh service would lock us out"
    assert fw.lockout_risk(s, without=next(r for r in rules if r.port == "443")) == ""


def test_a_named_service_we_do_not_know_is_named_not_called_port_nothing():
    _a, _p, rules = fw._parse_firewalld(REAL_CYBERPANEL)
    s = state(manager=fw.FIREWALLD, rules=rules)
    dhcp = next(r for r in rules if r.comment == "service: dhcpv6-client")
    assert "dhcpv6-client" in fw.describe(dhcp, s)
    assert "port " not in fw.describe(dhcp, s)
