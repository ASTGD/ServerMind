"""Choosing the PHP version and the database engine.

Until now the setup silently installed PHP 8.3 and MariaDB for every customer. If that was
wrong for a client's site they found out afterwards — when the fix is rebuilding the
machine, because a control panel wants a clean one. Ploi asks; now so do we.

The screen and the endpoint read ONE catalogue, so an option cannot be offered that the
backend then refuses. And the scripts are exercised rather than read: a `case` statement
contains every branch whether it is taken or not, so asserting that "postgresql" appears
in the generated text proves nothing at all.
"""
import subprocess

import pytest

from app.services import playbook_service as pb
from app.services import setup_service as s


def lemp() -> dict:
    for item in pb.OFFICIAL_PLAYBOOKS:
        if item["slug"] == "lemp-stack":
            return item
    raise AssertionError("lemp-stack is gone")


def script(php: str, db: str) -> str:
    return pb.substitute_variables(
        lemp()["script_bash"],
        {"MYSQL_ROOT_PASS": "", "PHP_VERSION": php, "DB_ENGINE": db})


# ── Nothing changes for anyone who does not choose ───────────────────────────

def test_the_defaults_are_exactly_what_it_did_before():
    """The single most important property here. Every existing customer, and the library
    playbook, must keep building the identical server."""
    step = next(st for st in s.build_recipe("websites", ssh_port=22).steps
                if st.slug == "lemp-stack")
    assert step.variables == {"PHP_VERSION": "default", "DB_ENGINE": "mariadb"}


def test_the_playbook_still_runs_straight_from_the_library():
    """Run with no variables at all — the path someone takes from the Playbooks page."""
    defaults = pb.declared_defaults(type("P", (), {"variables": lemp()["variables"]})())
    assert defaults["DB_ENGINE"] == "mariadb"
    assert defaults["PHP_VERSION"] == "default"
    pb.substitute_variables(lemp()["script_bash"], defaults)   # refuses on an unfilled slot


def test_a_choice_reaches_the_step():
    step = next(st for st in s.build_recipe(
        "websites", ssh_port=22, php_version="8.1", db_engine="postgres").steps
        if st.slug == "lemp-stack")
    assert step.variables == {"PHP_VERSION": "8.1", "DB_ENGINE": "postgres"}


# ── The catalogue and the script cannot disagree ─────────────────────────────

@pytest.mark.parametrize("choice", [c["value"] for c in s.DB_CHOICES])
def test_every_offered_database_is_one_the_script_handles(choice):
    """A dropdown entry the installer rejects is worse than a missing one: the customer
    picks it, waits, and the step fails on something they were invited to do."""
    body = script("default", choice)
    assert f"\n  {choice})" in body, f"the script has no branch for {choice}"


@pytest.mark.parametrize("choice", [c["value"] for c in s.PHP_CHOICES])
def test_every_offered_php_version_survives_substitution(choice):
    body = script(choice, "mariadb")
    assert f'PHP_VERSION="{choice}"' in body


@pytest.mark.parametrize("php", [c["value"] for c in s.PHP_CHOICES])
@pytest.mark.parametrize("db", [c["value"] for c in s.DB_CHOICES])
def test_every_combination_is_valid_shell(php, db, tmp_path):
    """28 combinations through a real bash parser. A quoting mistake in one branch would
    otherwise only surface on the customer's server, mid-install."""
    f = tmp_path / "s.sh"
    f.write_text(script(php, db))
    proc = subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


# ── Refused at the moment of choosing, not halfway through an install ────────

def test_mysql_is_refused_on_debian():
    """Debian packages MariaDB only. Installing MariaDB and calling it MySQL is the exact
    lie that was on this screen for months."""
    with pytest.raises(s.SetupRefused) as exc:
        s.check_choices("default", "mysql", os_type="debian")
    assert "MariaDB" in str(exc.value)


def test_mysql_is_allowed_on_ubuntu():
    s.check_choices("default", "mysql", os_type="ubuntu")


@pytest.mark.parametrize("bad", ["9.9", "8", "latest", "'; rm -rf /", ""])
def test_a_php_version_we_do_not_offer_is_refused(bad):
    with pytest.raises(s.SetupRefused):
        s.check_choices(bad, "mariadb")


@pytest.mark.parametrize("bad", ["oracle", "sqlite", "", "mariadb; reboot"])
def test_a_database_we_do_not_offer_is_refused(bad):
    with pytest.raises(s.SetupRefused):
        s.check_choices("default", bad)


# ── Honesty about old versions ───────────────────────────────────────────────

def test_versions_past_security_support_say_so():
    """An agency keeps a client on an old PHP for real reasons, so it is offered — but the
    one moment anybody is thinking about it is while choosing, so that is when it must be
    said."""
    eol = {c["value"] for c in s.PHP_CHOICES if c["eol"]}
    assert {"7.4", "8.0", "8.1"} <= eol
    assert "8.3" not in eol and "default" not in eol
    for c in s.PHP_CHOICES:
        if c["eol"]:
            assert "security" in c["note"].lower(), f"{c['value']} is EOL and does not say so"


def test_postgres_brings_its_own_php_driver():
    """Without it a PHP app cannot reach PostgreSQL at all — it fails on the first query
    with a driver-not-found error, which reads like a bug in the customer's application."""
    assert "php-pgsql" in script("default", "postgres")
    assert "php${PHP_VERSION}-pgsql" in script("8.3", "postgres")


def test_the_shared_php_layer_is_used_by_both_playbooks():
    """The apt_wait lesson: the same rule written in two scripts is how one of them ends
    up missing it."""
    versioned = next(i for i in pb.OFFICIAL_PLAYBOOKS if i["slug"] == "php-version")
    for body in (versioned["script_bash"], lemp()["script_bash"]):
        assert "php_archive_add" in body and "php_install_version" in body
    # And exactly one definition of it, not two copies.
    assert pb._PHP_ARCHIVE.count("php_archive_add()") == 1


# ── What it REALLY installs ──────────────────────────────────────────────────
# The tests above read the script. These run it, with the package manager replaced by a
# recorder, because a `case` statement contains every branch whether it is taken or not —
# so "postgresql appears in the text" is true even when MariaDB is what gets installed.
#
# The multi-distro layer reads /etc/os-release, which does not exist off Linux; it falls
# back to $ID, so the operating system can be named from the environment and every branch
# exercised on any machine.

def run_script(tmp_path, php: str, db: str, os_id: str = "ubuntu") -> tuple[int, list[str], str]:
    binstub = tmp_path / "bin"
    binstub.mkdir(exist_ok=True)
    log = tmp_path / "installed.txt"
    (binstub / "apt-get").write_text(
        f'#!/bin/sh\n[ "$1" = install ] && shift && for a in "$@"; do\n'
        f'  case "$a" in -*) ;; *) echo "$a" >> "{log}" ;; esac\ndone\nexit 0\n')
    (binstub / "dnf").write_text((binstub / "apt-get").read_text())
    for name, body in (
        ("systemctl", "exit 0"), ("add-apt-repository", "exit 0"),
        ("nginx", "echo 'nginx version: 1.24.0'"), ("php", "echo 'PHP 8.3.6'"),
        ("mysql", "exit 0"), ("rpm", "echo 9"), ("postgresql-setup", "exit 0"),
    ):
        (binstub / name).write_text(f"#!/bin/sh\n{body}\n")
    for f in binstub.iterdir():
        f.chmod(0o755)

    src = tmp_path / "s.sh"
    src.write_text(script(php, db))
    like = "debian" if os_id in ("ubuntu", "debian") else "rhel"
    proc = subprocess.run(
        ["bash", str(src)], capture_output=True, text=True,
        env={"PATH": f"{binstub}:/usr/bin:/bin:/usr/sbin:/sbin",
             "ID": os_id, "ID_LIKE": like, "HOME": str(tmp_path)})
    pkgs = log.read_text().split() if log.exists() else []
    return proc.returncode, pkgs, proc.stdout + proc.stderr


def test_the_default_build_installs_mariadb_and_the_system_php(tmp_path):
    code, pkgs, out = run_script(tmp_path, "default", "mariadb")
    assert code == 0, out
    assert "mariadb-server" in pkgs
    assert "php-fpm" in pkgs                      # the distro's version
    assert not any(p.startswith("php8.") for p in pkgs), pkgs
    assert not any("postgres" in p or "mysql-server" == p for p in pkgs), pkgs


def test_choosing_postgres_installs_postgres_and_NOT_mariadb(tmp_path):
    """The whole point of asking. Before this, every customer got MariaDB."""
    code, pkgs, out = run_script(tmp_path, "default", "postgres")
    assert code == 0, out
    assert "postgresql" in pkgs
    assert "mariadb-server" not in pkgs, "it installed MariaDB anyway"
    assert "php-pgsql" in pkgs, "PHP could not talk to the database it just installed"


def test_choosing_mysql_installs_real_mysql_not_mariadb(tmp_path):
    code, pkgs, out = run_script(tmp_path, "default", "mysql")
    assert code == 0, out
    assert "mysql-server" in pkgs
    assert "mariadb-server" not in pkgs, "it substituted MariaDB — the original bug"


def test_choosing_no_database_installs_none(tmp_path):
    code, pkgs, out = run_script(tmp_path, "default", "none")
    assert code == 0, out
    for db in ("mariadb-server", "mysql-server", "postgresql"):
        assert db not in pkgs, f"{db} was installed after choosing no database"
    assert "nginx" in pkgs and "php-fpm" in pkgs   # still a web server


def test_choosing_a_php_version_installs_that_version_only(tmp_path):
    code, pkgs, out = run_script(tmp_path, "8.1", "mariadb")
    assert code == 0, out
    assert "php8.1-fpm" in pkgs and "php8.1-mysql" in pkgs
    assert "php-fpm" not in pkgs, "it installed the distro PHP as well as the chosen one"


def test_mysql_on_debian_refuses_instead_of_substituting(tmp_path):
    """The refusal must live in the SCRIPT too. The API check protects our own screen;
    this protects anyone running the playbook straight from the library."""
    code, pkgs, out = run_script(tmp_path, "default", "mysql", os_id="debian")
    assert code != 0, "Debian has no mysql-server package, so this must not report success"
    assert "mariadb-server" not in pkgs, "it quietly installed MariaDB instead"
    assert "MariaDB" in out and "Ubuntu" in out, out


def test_an_invented_database_changes_nothing(tmp_path):
    code, pkgs, out = run_script(tmp_path, "default", "oracle")
    assert code != 0
    assert not any(p in pkgs for p in ("mariadb-server", "mysql-server", "postgresql"))
