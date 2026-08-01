"""Which database a site uses, and whether it can reach it.

Two properties carry this, and the first is the reason the screen is worth having.

**The connection test is the feature.** "The site is down" is very often "the site cannot
reach its database", and without this there is no way to tell that apart from a bug in the
application except by opening a terminal.

**A password must never leave the server.** The probe reads one — it has to, to attempt the
connection — and everything after that is arranged so it cannot escape: the value goes to
the client through ``MYSQL_PWD`` rather than the argument list, every stream the client
might print on is discarded, and the probe emits one word. These tests assert that by
running the real thing against a real database and searching the whole output.
"""
from __future__ import annotations

import re
import subprocess

import pytest

from app.services import site_database_service as sdb

S = "___SM_SITEDB___"

_WP = """<?php
define( 'DB_NAME', 'shop_wp' );
define( 'DB_USER', 'shopuser' );
define( 'DB_PASSWORD', 'SUPER-SECRET-DO-NOT-LEAK' );
define( 'DB_HOST', 'localhost' );
"""

_ENV = """APP_NAME=Acme
DB_CONNECTION=mysql
DB_HOST=127.0.0.1:3306
DB_DATABASE=acme_prod   # the live one
DB_USERNAME=acme
DB_PASSWORD="ANOTHER-SECRET-VALUE"
"""

_DOCKER = subprocess.run(["docker", "image", "inspect", "ubuntu:22.04"],
                         capture_output=True).returncode == 0


# ── Reading changes nothing ──────────────────────────────────────────────────

def test_the_probe_cannot_change_anything():
    """It reads two config values and runs one SELECT."""
    cmd = sdb.build_probe_command("wordpress", "/var/www/shop")
    for statement in ("DROP ", "DELETE ", "TRUNCATE", "INSERT ", "UPDATE ", "ALTER ",
                      "CREATE ", "GRANT "):
        assert statement not in cmd.upper(), f"the probe contains {statement.strip()}"
    for verb in ("rm", "mv", "chmod", "chown", "systemctl", "apt", "dd", "tee"):
        assert not re.search(r"(?<![\w-])" + verb + r"(?![\w-])", cmd), \
            f"the probe contains {verb}"


def test_the_probe_is_valid_shell():
    for app in ("wordpress", "laravel", "php", ""):
        r = subprocess.run(["bash", "-n"], text=True, capture_output=True,
                           input=sdb.build_probe_command(app, "/var/www/x"))
        assert r.returncode == 0, r.stderr


def test_the_password_never_reaches_the_argument_list():
    """Anything on a command line is visible to every user on the server through `ps`. The
    backup service established this rule; this follows it."""
    cmd = sdb.build_probe_command("wordpress", "/var/www/shop")
    assert 'MYSQL_PWD="$DB_PASS"' in cmd
    assert "-p$DB_PASS" not in cmd and '--password' not in cmd


def test_the_client_output_is_discarded_so_it_cannot_carry_a_credential():
    cmd = sdb.build_probe_command("wordpress", "/var/www/shop")
    connect = cmd[cmd.index('MYSQL_PWD="$DB_PASS" _t 15'):]
    assert ">/dev/null 2>&1" in connect.split("\n")[1], \
        "the connection attempt must print nothing at all"


def test_a_path_with_shell_characters_cannot_become_a_second_command():
    import shlex
    payload = "/var/www/x; touch /tmp/pwned"
    line = next(l for l in sdb.build_probe_command("wordpress", payload).splitlines()
                if l.startswith("for d in "))
    argv = shlex.split(line[len("for d in "):].rsplit(";", 1)[0])
    assert payload in argv
    assert "touch" not in argv


# ── Reading it out of a real config file ─────────────────────────────────────

def _run(config_name: str, config_text: str, image: str = "ubuntu:22.04") -> str:
    """Run the real probe against a real file, on real Linux."""
    import os
    import tempfile
    d = tempfile.mkdtemp()
    with open(os.path.join(d, config_name), "w") as fh:
        fh.write(config_text)
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{d}:/site", image, "bash", "-c",
         sdb.build_probe_command("wordpress", "/site")],
        capture_output=True, text=True, timeout=180)
    return r.stdout


@pytest.mark.skipif(not _DOCKER, reason="needs Linux")
def test_it_reads_wordpress_php_defines():
    out = _run("wp-config.php", _WP)
    p = sdb.parse_probe(out)
    assert p["ok"] and p["name"] == "shop_wp" and p["user"] == "shopuser"
    assert p["host"] == "localhost"


@pytest.mark.skipif(not _DOCKER, reason="needs Linux")
def test_it_reads_a_dotenv_and_strips_a_trailing_comment():
    """A real .env carries comments after values — the lesson the Laravel screen learned."""
    p = sdb.parse_probe(_run(".env", _ENV))
    assert p["ok"] and p["name"] == "acme_prod", "the comment must not become part of the name"
    assert p["user"] == "acme" and p["host"] == "127.0.0.1:3306"


@pytest.mark.skipif(not _DOCKER, reason="needs Linux")
@pytest.mark.parametrize("name,text,secret", [
    ("wp-config.php", _WP, "SUPER-SECRET-DO-NOT-LEAK"),
    (".env", _ENV, "ANOTHER-SECRET-VALUE"),
])
def test_the_password_appears_nowhere_in_what_the_probe_returns(name, text, secret):
    """Run the real probe over a real file holding a real password, and search everything
    that comes back. Asserting on the code would only prove what I believe it does."""
    out = _run(name, text)
    assert secret not in out, "the password reached the probe's output"
    assert secret not in str(sdb.parse_probe(out)), "the password reached the parsed result"


# ── Honest about what it could not learn ─────────────────────────────────────

def test_a_site_with_no_recognisable_config_says_so():
    p = sdb.parse_probe(f"{S}|error|noconfig")
    assert p["ok"] is False and "which database" in p["reason"]


def test_a_config_that_names_no_database_is_not_an_error_worth_alarming_about():
    p = sdb.parse_probe(f"{S}|error|nodb")
    assert p["ok"] is False and "does not use one" in p["reason"]


def test_no_client_to_test_with_is_not_the_same_as_a_failed_connection():
    """Only one of these is bad news, and showing a red cross for the other would train
    somebody to ignore the real one."""
    untested = sdb.parse_probe(f"{S}|name|x\n{S}|reach|noclient")
    assert untested["tested"] is False and untested["reachable"] is False

    failed = sdb.parse_probe(f"{S}|name|x\n{S}|reach|no")
    assert failed["tested"] is True and failed["reachable"] is False


def test_a_working_connection_reports_what_the_site_itself_can_see():
    p = sdb.parse_probe(f"{S}|name|shop_wp\n{S}|user|u\n{S}|reach|yes\n"
                        f"{S}|tables|12\n{S}|size_mb|4.5")
    assert p["reachable"] is True and p["tested"] is True
    assert p["tables"] == 12 and p["size_mb"] == 4.5


def test_broken_output_never_crashes_the_screen():
    for junk in ("", "bash: mysql: not found", f"{S}|tables|not-a-number",
                 f"{S}|size_mb|\n{S}|reach|yes", f"{S}|truncated"):
        sdb.parse_probe(junk)


def test_the_probe_accepts_either_client_name():
    """MariaDB 11 renamed its client to `mariadb` and no longer always ships a `mysql`
    symlink. Looking only for the old name reported "could not test" on every modern
    MariaDB server — found by running this against a real one."""
    cmd = sdb.build_probe_command("wordpress", "/var/www/x")
    assert "for c in mysql mariadb" in cmd
    assert '"$CLIENT"' in cmd


def test_the_client_ignores_option_files_so_an_admin_config_cannot_hijack_it():
    """The client reads option files BEFORE anything we pass, and a control-panel server
    has /root/.my.cnf holding the administrator's credentials — which silently replace the
    site's and are refused.

    The result was a red "this site cannot reach its database" on a perfectly healthy site,
    which is the worst thing this screen could do: a false alarm here teaches somebody to
    ignore the real one. Found on a real CyberPanel server, where --no-defaults turned a
    refusal into a connection.
    """
    cmd = sdb.build_probe_command("laravel", "/var/www/app/public")
    # Only the lines that actually RUN the client — a line merely naming the variable is
    # not an invocation and has nothing to ignore option files for.
    calls = [l for l in cmd.splitlines() if 'MYSQL_PWD=' in l and '"$CLIENT"' in l]
    assert calls, "no client invocation found at all"
    for call in calls:
        assert "--no-defaults" in call, \
            f"a client call reads option files: {call.strip()}"
