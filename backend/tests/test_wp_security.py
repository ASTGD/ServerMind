"""The two WordPress security switches.

The debug one has a trap Ploi's own description does not mention, and it is the reason most
of these tests exist: `WP_DEBUG = true` on its own prints PHP errors INTO THE PAGE for every
visitor. Turning debugging on without also turning display off does not help somebody debug
a site — it leaks the site's internals to the public while they do it.
"""
import os
import re
import subprocess

import pytest

from app.services import wp_security_service as s
from app.services import wp_security_service as s_mod


# ── Where the debug log is allowed to live ───────────────────────────────────

def test_the_log_goes_beside_the_site_never_inside_it():
    """WordPress's own default is `wp-content/debug.log` — inside the folder the web server
    serves, under a name every scanner already knows."""
    path = s.log_path_for("/home/shop.example.com/public_html")
    assert path == "/home/shop.example.com/serverally-logs/wp-debug.log"
    assert not path.startswith("/home/shop.example.com/public_html")


@pytest.mark.parametrize("shared", [
    "/var/www/html", "/var/www", "/srv/site", "/home/x", "/opt/app",
])
def test_debugging_is_refused_rather_than_leaked_when_there_is_nowhere_safe(shared):
    """The promise on the screen is that the log can never be fetched from the web. If that
    cannot be kept, the switch must refuse — a debug log anyone can download is worse than
    no debug log, and a promise we cannot keep is worse than both."""
    with pytest.raises(s.WpSecurityError) as exc:
        s.log_path_for(shared)
    assert "shared with other sites" in str(exc.value)


def test_the_whole_server_gets_an_accurate_refusal_not_a_vague_one():
    """"/" strips to an empty string, so the naive check reports "we do not know where this
    site lives" — which is not what is wrong with it. The most dangerous input deserves the
    most accurate refusal."""
    with pytest.raises(s.WpSecurityError) as exc:
        s.log_path_for("/")
    assert "the whole server" in str(exc.value)


def test_a_site_in_its_own_folder_is_fine():
    assert s.log_dir_for("/var/www/shop.example.com/public") \
        == "/var/www/shop.example.com/serverally-logs"


# ── The trap ─────────────────────────────────────────────────────────────────

def test_turning_debugging_on_always_turns_display_off():
    """The one that matters. Without it, every visitor sees PHP errors on a live site."""
    cmd = s.build_debug_command("/home/shop.example.com/public_html",
                                "/home/shop.example.com/public_html", enable=True)
    assert "WP_DEBUG_DISPLAY false" in cmd
    # and it must be set in the same breath as WP_DEBUG, not left to a later step
    assert cmd.index("WP_DEBUG true") < cmd.index("WP_DEBUG_DISPLAY false")


def test_turning_it_on_points_the_log_outside_the_web_root():
    cmd = s.build_debug_command("/home/shop.example.com/public_html",
                                "/home/shop.example.com/public_html", enable=True)
    assert "/home/shop.example.com/serverally-logs/wp-debug.log" in cmd
    assert "wp-content/debug.log" not in cmd


def test_a_site_already_leaking_errors_is_reported_as_such():
    """WP_DEBUG on with display not explicitly off. Invisible from the site itself until a
    visitor happens to trigger an error, which is why it is worth saying out loud."""
    state = s.parse_state("\n".join([
        "___SM_WPSEC___|path|/home/x/public_html",
        "___SM_WPSEC___|WP_DEBUG|true",
        "___SM_WPSEC___|WP_DEBUG_DISPLAY|",
    ]))
    assert state["debug"] is True
    assert state["leaking_errors"] is True


def test_debug_on_with_display_explicitly_off_is_not_leaking():
    state = s.parse_state("\n".join([
        "___SM_WPSEC___|path|/home/x/public_html",
        "___SM_WPSEC___|WP_DEBUG|true",
        "___SM_WPSEC___|WP_DEBUG_DISPLAY|false",
    ]))
    assert state["leaking_errors"] is False


def test_debug_off_is_never_reported_as_leaking():
    state = s.parse_state("___SM_WPSEC___|WP_DEBUG|false")
    assert state["debug"] is False and state["leaking_errors"] is False


def test_a_log_left_at_wordpress_default_is_flagged():
    state = s.parse_state("\n".join([
        "___SM_WPSEC___|WP_DEBUG|true",
        "___SM_WPSEC___|WP_DEBUG_DISPLAY|false",
        "___SM_WPSEC___|WP_DEBUG_LOG|/home/x/public_html/wp-content/debug.log",
    ]))
    assert state["log_in_web_root"] is True


def test_our_own_log_location_is_not_flagged():
    state = s.parse_state("\n".join([
        "___SM_WPSEC___|WP_DEBUG|true",
        "___SM_WPSEC___|WP_DEBUG_LOG|/home/x/serverally-logs/wp-debug.log",
    ]))
    assert state["log_in_web_root"] is False


# ── wp-config.php is not something to be careless with ───────────────────────

def test_the_config_is_backed_up_and_proved_to_still_load():
    """A wp-config.php that no longer parses takes the whole site down. It holds the
    database password too, so it is never read out to us — only kept and put back."""
    cmd = s.build_debug_command("/home/x/public_html", "/home/x/public_html", enable=True)
    assert "cp -p \"$CFG\" \"$BK\"" in cmd
    assert "php -l" in cmd
    # the LAST one — the earlier occurrences are inside the two failure branches, which
    # restore the backup before removing it
    assert cmd.index("php -l") < cmd.rindex('rm -f "$BK"')


def test_the_config_contents_never_leave_the_server():
    """It holds the database password. Nothing here reads it back to us or puts it on a
    command line — the edit happens in place, by wp-cli."""
    cmd = s.build_debug_command("/home/x/public_html", "/home/x/public_html", enable=True)
    for leak in ("cat \"$CFG\"", "base64", "grep -v", "tee "):
        assert leak not in cmd


def test_wp_cli_writes_the_constants_rather_than_a_hand_rolled_edit():
    """wp-cli knows where a constant belongs. An edit that lands after wp-config's
    "stop editing" line is ignored by WordPress while looking perfectly correct in the
    file."""
    cmd = s.build_debug_command("/home/x/public_html", "/home/x/public_html", enable=True)
    assert "config set" in cmd
    assert "sed -i" not in cmd


def test_turning_it_off_stops_the_logging():
    cmd = s.build_debug_command("/home/x/public_html", "/home/x/public_html", enable=False)
    assert "WP_DEBUG false" in cmd and "WP_DEBUG_LOG false" in cmd


# ── XML-RPC ──────────────────────────────────────────────────────────────────

def test_the_block_is_an_exact_location_so_php_cannot_win_the_race():
    """`location = /xmlrpc.php` outranks the regex `\\.php$` location. A prefix location
    would lose that race, hand the request to PHP, and the block would do nothing while
    reading correctly in the file."""
    cmd = s.build_xmlrpc_command("/etc/nginx/sites-available/x", "x.com",
                                 block=True, apache=False)
    assert "location = /xmlrpc.php" in cmd
    assert "deny all" in cmd


def test_apache_gets_apache_syntax():
    cmd = s.build_xmlrpc_command("/etc/apache2/sites-available/x.conf", "x.com",
                                 block=True, apache=True)
    assert "<Files \"xmlrpc.php\">" in cmd and "Require all denied" in cmd
    assert "location =" not in cmd


def test_unblocking_writes_an_empty_block_rather_than_a_second_code_path():
    """Adding, changing and removing are one operation. A separate delete path is a second
    thing to get wrong, and with nothing left the file is what it was before."""
    cmd = s.build_xmlrpc_command("/etc/nginx/sites-available/x", "x.com",
                                 block=False, apache=False)
    assert "deny all" not in cmd
    assert s.BEGIN in cmd  # the markers are still there, to find and remove the old block


def test_a_refused_config_is_put_back(tmp_path):
    """RUN it, against a real file, with a web server that refuses.

    The previous version of this test asserted that `cp -p "$BK" "$CFG"` appeared in the
    command — and passed happily when the restore was deleted, because the same line also
    appears in the OTHER rollback branch. A test that cannot fail is not protecting
    anything.
    """
    cfg = tmp_path / "site.conf"
    original = "server {\n    server_name x.com;\n    root /var/www/x;\n}\n"
    cfg.write_text(original)

    b = tmp_path / "bin"
    b.mkdir()
    (b / "nginx").write_text("#!/bin/bash\nexit 1\n")          # refuses every config
    (b / "apachectl").write_text("#!/bin/bash\nexit 1\n")
    (b / "systemctl").write_text("#!/bin/bash\nexit 0\n")
    (b / "curl").write_text("#!/bin/bash\nprintf 200\n")
    for f in ("nginx", "apachectl", "systemctl", "curl"):
        os.chmod(b / f, 0o755)

    cmd = s_mod.build_xmlrpc_command(str(cfg), "x.com", block=True, apache=False)
    r = subprocess.run(["bash", "-c", f'export PATH="{b}:$PATH"; {cmd}'],
                       capture_output=True, text=True)

    assert r.returncode == 4
    assert cfg.read_text() == original, "the refused config must be put back exactly"
    assert not list(tmp_path.glob("*.bak")), "and the backup cleaned up"
    assert not list(tmp_path.glob("*.tmp"))
    ok, message = s_mod.explain_xmlrpc(r.returncode, r.stdout, block=True)
    assert ok is False and "unaffected" in message


def test_the_block_really_lands_in_the_config_when_the_web_server_accepts_it(tmp_path):
    cfg = tmp_path / "site.conf"
    cfg.write_text("server {\n    server_name x.com;\n    root /var/www/x;\n}\n")

    b = tmp_path / "bin"
    b.mkdir()
    for name in ("nginx", "systemctl"):
        (b / name).write_text("#!/bin/bash\nexit 0\n")
    (b / "curl").write_text(
        "#!/bin/bash\nout=''\n"
        'while [ $# -gt 0 ]; do case "$1" in -o) out="$2"; shift 2;; *) shift;; esac; done\n'
        "[ -n \"$out\" ] && printf 'the real page' > \"$out\"\nprintf 200\n")
    for f in ("nginx", "systemctl", "curl"):
        os.chmod(b / f, 0o755)

    cmd = s_mod.build_xmlrpc_command(str(cfg), "x.com", block=True, apache=False)
    r = subprocess.run(["bash", "-c", f'export PATH="{b}:$PATH"; {cmd}'],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    body = cfg.read_text()
    assert "location = /xmlrpc.php" in body and "deny all" in body
    # and removing it leaves the file exactly as it started
    cmd = s_mod.build_xmlrpc_command(str(cfg), "x.com", block=False, apache=False)
    subprocess.run(["bash", "-c", f'export PATH="{b}:$PATH"; {cmd}'], capture_output=True)
    assert cfg.read_text() == "server {\n    server_name x.com;\n    root /var/www/x;\n}\n"


def test_the_state_reads_the_block_out_of_the_real_config():
    assert s.parse_state("___SM_WPSEC___|WP_DEBUG|false",
                         config_block=f"server {{\n{s.BEGIN}\nx\n{s.END}\n}}")["xmlrpc_blocked"]
    assert not s.parse_state("___SM_WPSEC___|WP_DEBUG|false",
                             config_block="server { }")["xmlrpc_blocked"]


def test_what_blocking_costs_is_named():
    """These are real tools people use. Finding out by breaking one is a bad way to learn."""
    assert "Jetpack" in s.XMLRPC_BREAKS
    assert any("mobile app" in item for item in s.XMLRPC_BREAKS)


# ── Reading and reporting ────────────────────────────────────────────────────

def test_the_state_probe_changes_nothing():
    cmd = s.build_state_command("/home/x/public_html")
    body = re.sub(r"\d?>\s*/dev/null", "", cmd)
    for verb in ("rm ", "mv ", "chmod", "chown", "config set", "sed -i", "tee "):
        assert verb not in body


def test_a_site_with_no_wp_config_says_so():
    r = s.parse_state("___SM_WPSEC___|error|noconfig")
    assert r["ok"] is False and "no wp-config.php" in r["reason"]


def test_a_broken_config_is_reported_as_put_back():
    ok, message = s.explain_debug("___SM_WPSEC___|error|broken", enable=True)
    assert ok is False
    assert "put back" in message and "Nothing is changed" in message


def test_success_says_visitors_will_not_see_the_errors():
    ok, message = s.explain_debug("___SM_WPSEC___|ok|on", enable=True)
    assert ok is True
    assert "visitors will never see them" in message
    assert "cannot be downloaded" in message


def test_an_unreadable_result_is_not_reported_as_success():
    """Silence is not success. Saying it worked when we cannot tell is how somebody leaves
    debugging on believing it is off."""
    ok, _ = s.explain_debug("", enable=True)
    assert ok is False


def test_a_site_that_was_already_down_is_not_told_our_change_broke_it(tmp_path):
    """Found when a harness had no PHP running: the feature rolled back and reported "the
    site stopped serving", blaming itself for an outage that was already there — and leaving
    the customer unable to use these switches at exactly the moment they are fixing
    something."""
    cfg = tmp_path / "site.conf"
    cfg.write_text("server {\n    server_name x.com;\n}\n")
    b = tmp_path / "bin"
    b.mkdir()
    for name in ("nginx", "systemctl"):
        (b / name).write_text("#!/bin/bash\nexit 0\n")
    (b / "curl").write_text("#!/bin/bash\nprintf 502\n")     # down before AND after
    for f in ("nginx", "systemctl", "curl"):
        os.chmod(b / f, 0o755)

    cmd = s_mod.build_xmlrpc_command(str(cfg), "x.com", block=True, apache=False)
    r = subprocess.run(["bash", "-c", f'export PATH="{b}:$PATH"; {cmd}'],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "location = /xmlrpc.php" in cfg.read_text(), "the change is kept"
    ok, message = s_mod.explain_xmlrpc(r.returncode, r.stdout, block=True)
    assert ok is True
    assert "already not serving before the change" in message
    assert not list(tmp_path.glob("*.bak"))


def test_the_reload_falls_back_when_there_is_no_systemd():
    """Without this the change is written, never loaded, and reported as applied — because
    the verify request then passes against the OLD config. Caught in a container with no
    systemd, and equally true of a minimal install."""
    cmd = s_mod.build_xmlrpc_command("/etc/nginx/conf.d/x", "x.com",
                                     block=True, apache=False)
    assert "nginx -s reload" in cmd
    assert cmd.index("systemctl reload nginx") < cmd.index("nginx -s reload")
