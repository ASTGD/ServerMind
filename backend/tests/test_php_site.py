"""The PHP section: what a site actually runs under.

Two properties matter, and both are about honesty rather than features.

**The values must come from the SITE, not from a shell.** ``php -i`` at the command line
reports the CLI's settings, which are almost always more generous than the web ones — so a
site that rejects a 2 MB upload would be shown a comfortable 64 MB limit, and the one number
somebody came here for would be a lie.

**The probe must leave nothing behind.** It writes a PHP file into a customer's web root to
ask the question. A forgotten file that reports a server's configuration is exactly what
somebody scanning for weaknesses is looking for.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile

from app.services import app_registry, php_site_service as ps

S = "___SM_PHPSITE___"


def test_php_is_in_the_registry():
    assert app_registry.app_for("php") is not None


def test_the_probe_is_valid_shell():
    r = subprocess.run(["bash", "-n"], text=True, capture_output=True,
                       input=ps.build_probe_command("/var/www/x"))
    assert r.returncode == 0, r.stderr


def test_it_asks_the_site_rather_than_the_command_line():
    """The whole point. The CLI's limits are not the site's, and showing them would answer
    "why did my upload fail" with a number that has nothing to do with it."""
    cmd = ps.build_probe_command("/var/www/shop/public")
    assert "http://127.0.0.1/" in cmd, "the values come from a real request to the site"
    assert 'Host: $SM_DOMAIN' in cmd, "…through the site's own vhost, and therefore its pool"


def test_a_path_with_shell_characters_cannot_become_a_second_command():
    import shlex
    payload = "/var/www/x; touch /tmp/pwned"
    line = next(l for l in ps.build_probe_command(payload).splitlines()
                if l.startswith("ROOT="))
    argv = shlex.split(line[len("ROOT="):])
    assert argv == [payload]
    assert "touch" not in argv


def test_the_probe_removes_its_own_file_however_it_exits():
    """Asserted by RUNNING it, not by reading it: a trap that is present but wrong still
    leaves the file, and that is the failure that matters."""
    with tempfile.TemporaryDirectory() as root:
        open(os.path.join(root, "index.html"), "w").write("hi")
        before = set(os.listdir(root))
        script = f"SM_DOMAIN=shop.example.com\n" + ps.build_probe_command(root)
        # curl will find nothing on 127.0.0.1 here, so this exercises the FAILURE path —
        # which is the one where a forgotten file would actually be left behind.
        subprocess.run(["bash"], input=script, text=True, capture_output=True, timeout=60)
        assert set(os.listdir(root)) == before, "the probe left a file in the web root"


def test_the_file_it_writes_is_not_left_world_writable_or_named_predictably():
    cmd = ps.build_probe_command("/var/www/x")
    assert "/dev/urandom" in cmd, "a predictable name is one somebody can fetch on purpose"
    assert "chmod 644" in cmd


def test_it_reads_the_settings_that_answer_real_questions():
    payload = {"version": "8.3.6", "sapi": "fpm-fcgi",
               "settings": {"upload_max_filesize": "2M", "post_max_size": "8M",
                            "memory_limit": "128M", "max_execution_time": "30",
                            "max_input_vars": "1000", "display_errors": ""},
               "extensions": ["curl", "mbstring", "pdo_mysql"]}
    p = ps.parse_probe(f"{S}|web|{json.dumps(payload)}\n{S}|cli|8.3.6")
    assert p["ok"] is True and p["version"] == "8.3.6" and p["sapi"] == "fpm-fcgi"
    values = {s["name"]: s["value"] for s in p["settings"]}
    assert values["upload_max_filesize"] == "2M"
    assert values["memory_limit"] == "128M"
    # Every setting is shown even when empty, so a missing one is visible rather than absent.
    assert values["display_errors"] == "—"
    assert p["extensions"] == ["curl", "mbstring", "pdo_mysql"]


def test_a_site_that_did_not_answer_says_so_instead_of_showing_the_command_line():
    """The comforting lie this module exists to avoid."""
    p = ps.parse_probe(f"{S}|web|\n{S}|cli|8.3.6")
    assert p["ok"] is False
    assert "did not answer" in p["reason"]
    assert "8.3.6" not in json.dumps(p), "the CLI version must not stand in for the site's"


def test_a_missing_folder_is_named():
    assert ps.parse_probe(f"{S}|error|noroot")["ok"] is False


def test_broken_output_never_crashes_the_screen():
    for junk in ("", "bash: curl: not found", f"{S}|web|<html>404</html>",
                 f"{S}|web|{{not json", f"{S}|web|[1,2,3]", f"{S}|truncated"):
        assert ps.parse_probe(junk)["ok"] is False


def test_there_is_no_way_to_change_anything_from_here():
    """A pool limit is shared by every site using it, so changing one belongs to the
    server's PHP screen. Locked so an action cannot be added here without a decision."""
    assert not hasattr(ps, "ACTIONS")
    assert not hasattr(ps, "act")
    assert not hasattr(ps, "build_action_command")
