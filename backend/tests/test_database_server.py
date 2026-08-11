"""A dedicated database server.

The most dangerous thing in the product. A database is only useful here if another machine
can reach it — and a reachable database with a weak password is the single most reliably
exploited thing anyone puts on the internet. Our own Redis playbook says so: it is how a
large share of crypto-miner infections get in.

So the property that matters is not "does it install MariaDB". It is: **the port is never
opened to anyone except addresses we were explicitly given.** These tests run the real
script with the firewall replaced by a recorder and read back every rule it tried to add.
"""
import re
import subprocess

import pytest

from app.services import playbook_service as pb
from app.services import setup_service as s


def entry() -> dict:
    for item in pb.OFFICIAL_PLAYBOOKS:
        if item["slug"] == "database-server":
            return item
    raise AssertionError("database-server is gone")


def script(engine: str, allow: str) -> str:
    return pb.substitute_variables(
        entry()["script_bash"], {"DB_ENGINE": engine, "ALLOW_FROM": allow})


def run(tmp_path, engine: str, allow: str, os_id: str = "ubuntu"):
    """Run it for real, recording every firewall rule and every package."""
    binstub = tmp_path / "bin"
    binstub.mkdir(exist_ok=True)
    fw, pkgs = tmp_path / "fw.txt", tmp_path / "pkg.txt"
    (binstub / "ufw").write_text(
        f'#!/bin/sh\n[ "$1" = status ] && echo "Status: active" && exit 0\n'
        f'echo "$@" >> "{fw}"\nexit 0\n')
    (binstub / "apt-get").write_text(
        f'#!/bin/sh\n[ "$1" = install ] && shift && for a in "$@"; do\n'
        f'  case "$a" in -*) ;; *) echo "$a" >> "{pkgs}" ;; esac\ndone\nexit 0\n')
    (binstub / "dnf").write_text((binstub / "apt-get").read_text())
    for name, body in (
        ("systemctl", 'case "$1" in is-active) exit 1 ;; *) exit 0 ;; esac'),
        ("mysql", "exit 0"), ("su", "exit 0"), ("ss", "echo ''"),
        ("firewall-cmd", "exit 0"), ("postgresql-setup", "exit 0"),
        ("journalctl", "exit 0"), ("rpm", "echo 9"),
    ):
        (binstub / name).write_text(f"#!/bin/sh\n{body}\n")
    for f in binstub.iterdir():
        f.chmod(0o755)

    # PostgreSQL's config has to exist for the listen-address edit to be exercised.
    pg = tmp_path / "etc" / "postgresql" / "16" / "main"
    pg.mkdir(parents=True, exist_ok=True)
    (pg / "postgresql.conf").write_text("#listen_addresses = 'localhost'\n")
    (pg / "pg_hba.conf").write_text("local all all peer\n")
    mycnf = tmp_path / "etc" / "mysql" / "mariadb.conf.d"
    mycnf.mkdir(parents=True, exist_ok=True)

    body = script(engine, allow)
    # Point the absolute paths at the sandbox. Declared, not hidden: the alternative is a
    # container per case, and what is under test is the firewall logic, not path strings.
    body = body.replace("/etc/postgresql /var/lib/pgsql", str(tmp_path / "etc" / "postgresql"))
    body = body.replace("/etc/mysql/mariadb.conf.d", str(mycnf))
    # Point the script at a FAKE /etc/os-release instead of the machine's own.
    #
    # These tests fake the OS with `ID=debian` in the environment, which works only where
    # /etc/os-release does not exist — a Mac. On any Linux (the CI runner included) the
    # script sources the real file and OVERWRITES that variable, so a "Debian refuses MySQL"
    # test silently became "Ubuntu installs MySQL" and passed as a success. Substituting the
    # path keeps the fake OS true wherever the test runs.
    osr = tmp_path / "os-release"
    osr.write_text(f'ID={os_id}\nID_LIKE=debian\nPRETTY_NAME="{os_id} (test)"\n')
    body = body.replace("/etc/os-release", str(osr))
    assert "/etc/os-release" not in body, (
        "the script still reads the machine's own os-release, so the fake OS above is a "
        "decoration — on Linux it would be overwritten and the test would pass for the "
        "wrong reason")

    src = tmp_path / "s.sh"
    src.write_text(body)
    proc = subprocess.run(
        ["bash", str(src)], capture_output=True, text=True,
        env={"PATH": f"{binstub}:/usr/bin:/bin:/usr/sbin:/sbin",
             "ID": os_id, "ID_LIKE": "debian", "HOME": str(tmp_path)})
    rules = fw.read_text().splitlines() if fw.exists() else []
    return proc.returncode, rules, (pkgs.read_text().split() if pkgs.exists() else []), \
        proc.stdout + proc.stderr


# ── The property the whole feature rests on ──────────────────────────────────

@pytest.mark.parametrize("engine", ["mariadb", "mysql", "postgres"])
def test_the_port_is_never_opened_to_everyone(tmp_path, engine):
    """`ufw allow 3306/tcp` — with no source — is the accident this feature could cause.
    Every rule it writes must name an address."""
    _code, rules, _pkgs, _out = run(tmp_path, engine, "10.0.0.5")
    assert rules, "no firewall rule was written at all"
    for rule in rules:
        assert " from " in rule, f"this rule opens the port to the internet: {rule!r}"


def test_only_the_addresses_given_are_allowed(tmp_path):
    code, rules, _p, out = run(tmp_path, "mariadb", "10.0.0.5, 10.0.0.6")
    assert code == 0, out
    allowed = {m.group(1) for r in rules if (m := re.search(r"from (\S+)", r))}
    assert allowed == {"10.0.0.5", "10.0.0.6"}, rules
    assert all("3306" in r for r in rules), rules


def test_with_nobody_named_the_port_stays_shut(tmp_path):
    """A customer with one server. The safe outcome is a closed port and a sentence saying
    so — never "we opened it so it would work"."""
    code, rules, _p, out = run(tmp_path, "mariadb", "")
    assert code == 0, out
    assert rules == [], f"it opened the port with nobody to open it for: {rules}"
    assert "closed to everyone" in out
    assert "deliberate" in out


def test_a_hostname_is_skipped_rather_than_allowed(tmp_path):
    """A hostname in a firewall rule resolves once, when written, and then silently stops
    matching. Refusing it beats writing a rule that quietly rots."""
    code, rules, _p, out = run(tmp_path, "mariadb", "db.example.com, 10.0.0.7")
    assert code == 0, out
    allowed = {m.group(1) for r in rules if (m := re.search(r"from (\S+)", r))}
    assert allowed == {"10.0.0.7"}
    assert "db.example.com" in out and "Skipped" in out


def test_postgres_uses_its_own_port_and_writes_its_access_rules(tmp_path):
    code, rules, _p, out = run(tmp_path, "postgres", "10.0.0.5")
    assert code == 0, out
    assert all("5432" in r for r in rules), rules
    hba = (tmp_path / "etc" / "postgresql" / "16" / "main" / "pg_hba.conf").read_text()
    assert "10.0.0.5/32" in hba, "PostgreSQL would refuse the connection the firewall allows"
    assert "scram-sha-256" in hba, "no password would be required"


def test_postgres_actually_listens_on_the_network(tmp_path):
    """Without this the firewall is open onto a database that is not there."""
    run(tmp_path, "postgres", "10.0.0.5")
    conf = (tmp_path / "etc" / "postgresql" / "16" / "main" / "postgresql.conf").read_text()
    assert "listen_addresses = '*'" in conf
    assert not re.search(r"^\s*#?listen_addresses = 'localhost'", conf, re.M)


def test_mysql_bind_is_a_dropin_not_an_edit(tmp_path):
    """A package upgrade rewrites the main file. A change made there is reverted weeks
    later and the database quietly leaves the network."""
    run(tmp_path, "mariadb", "10.0.0.5")
    dropin = tmp_path / "etc" / "mysql" / "mariadb.conf.d" / "99-serverally.cnf"
    assert dropin.exists() and "bind-address = 0.0.0.0" in dropin.read_text()


# ── Refusals ─────────────────────────────────────────────────────────────────

def test_a_database_server_with_no_database_is_refused(tmp_path):
    code, rules, pkgs, out = run(tmp_path, "none", "10.0.0.5")
    assert code != 0
    assert rules == [] and pkgs == []
    assert "needs a database" in out


def test_mysql_on_debian_is_refused_here_too(tmp_path):
    code, rules, pkgs, out = run(tmp_path, "mysql", "10.0.0.5", os_id="debian")
    assert code != 0
    assert "mariadb-server" not in pkgs, "it substituted MariaDB"
    assert rules == [], "it opened a port for a database it did not install"


@pytest.mark.parametrize("evil", ["10.0.0.5; rm -rf /", "$(id)", "`id`", "10.0.0.5 --anywhere"])
def test_a_crafted_address_never_becomes_a_firewall_rule(tmp_path, evil):
    """ALLOW_FROM is assembled by us from the customer's own servers, but it lands in a
    command, so it is validated rather than trusted."""
    code, rules, _p, out = run(tmp_path, "mariadb", evil)
    assert code == 0, out
    assert rules == [], f"a crafted address produced a rule: {rules}"


# ── It is offered the same way everywhere ────────────────────────────────────

def test_the_setup_offers_it_with_a_real_engine():
    recipe = s.build_recipe("database", ssh_port=22, db_engine="postgres")
    step = next(st for st in recipe.steps if st.slug == "database-server")
    assert step.variables["DB_ENGINE"] == "postgres"


def test_a_database_server_cannot_be_set_up_with_no_database():
    with pytest.raises(s.SetupRefused):
        s.check_choices("default", "none", purpose="database")


# ── Found by mutation testing, not by inspection ─────────────────────────────
# Changing the empty-entry guard to `IP=0.0.0.0` opened the port to the entire internet
# and all seventeen tests above still passed — because every one of them fed either a
# clean list or a completely empty one, and the guard only runs on an empty ELEMENT.

@pytest.mark.parametrize("allow", [
    "10.0.0.5,,10.0.0.6",     # a doubled comma
    "10.0.0.5,",              # a trailing comma
    ",10.0.0.5",              # a leading one
    " , , ",                  # nothing but separators
    ",,,",
])
def test_an_empty_entry_never_becomes_a_rule(tmp_path, allow):
    code, rules, _p, out = run(tmp_path, "mariadb", allow)
    assert code == 0, out
    for rule in rules:
        assert " from " in rule and "0.0.0.0" not in rule, f"opened to everyone: {rule!r}"


def test_the_everyone_address_is_refused_by_name(tmp_path):
    """Belt and braces. Nothing upstream produces 0.0.0.0 today — but this script is the
    last thing standing between a customer's data and the internet, so it does not rely
    on that staying true."""
    code, rules, _p, out = run(tmp_path, "mariadb", "0.0.0.0")
    assert code == 0, out
    assert rules == [], f"it opened the database to everyone: {rules}"
    assert "Skipped" in out


def test_no_rule_anywhere_ever_means_everyone(tmp_path):
    """One assertion covering every input the other tests use, stated as the property
    rather than as a list of cases.

    Checks the SOURCE specifically. A ufw rule reads `allow from <ip> to any port 3306`,
    so a naive search for "any" matches the destination — which is legitimate, and which
    is exactly how a security assertion ends up passing for the wrong reason.
    """
    for allow in ("10.0.0.5", "10.0.0.5,10.0.0.6", "", "0.0.0.0", "host.example.com",
                  "10.0.0.5,,", "255.255.255.255"):
        _code, rules, _pkgs, _out = run(tmp_path, "mariadb", allow)
        for rule in rules:
            source = re.search(r"from (\S+)", rule)
            assert source, f"a rule with no source at all: {rule!r}"
            assert re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", source.group(1)), \
                f"{allow!r} produced a non-address source: {rule!r}"
            assert source.group(1) != "0.0.0.0", f"{allow!r} opened it to everyone"
