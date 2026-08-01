"""The application section, and its first entry: WordPress.

Two properties carry this, and both were live findings rather than things anyone would
assert from reading the code:

1. **Who runs wp-cli decides whether the site survives it.** Run as root, it leaves
   root-owned files in ``wp-content``; WordPress then runs as the web-server user and can no
   longer write there. Uploads stop, updates fail from inside the admin, and it all happens
   days after the command that caused it.
2. **Silence must never render as good news.** Every wp-cli call redirects stderr so an error
   cannot corrupt the JSON it captures — which means a failure produces empty output, and an
   empty screen is indistinguishable from a genuinely empty site.
"""
from __future__ import annotations

import re
import subprocess

import pytest

from app.services import app_registry, wordpress_service as wp

S = "___SM_WP___"


# ── The registry ─────────────────────────────────────────────────────────────

def test_a_site_running_something_we_support_gets_a_section():
    spec = app_registry.app_for("wordpress")
    assert spec is not None and spec.label == "WordPress"


@pytest.mark.parametrize("app_type", ["php", "static", "unknown", "", None, "laravel"])
def test_a_site_we_have_no_tools_for_gets_no_section(app_type):
    """Absent, not disabled. A dead row implies the feature exists and is switched off — and
    `php`/`static` are not applications at all, they are how a site is served."""
    assert app_registry.app_for(app_type) is None


def test_the_registry_is_case_insensitive_about_what_a_scan_recorded():
    assert app_registry.app_for("WordPress") is not None


# ── Who the command runs as ──────────────────────────────────────────────────

def test_a_site_owned_by_another_account_is_never_touched_as_root():
    """The whole point of the module. Verified on a real server as well: a CyberPanel site
    owned by `aquafwkw` ran as `aquafwkw`."""
    cmd = wp.build_probe_command("/home/shop.example.com/public_html")
    assert 'sudo -n -u $OWNER --' in cmd
    # --allow-root exists, but only reachable when the site is genuinely root-owned.
    assert '[ "$OWNER" = root ] && ROOTFLAG="--allow-root"' in cmd


def test_sudo_never_waits_for_a_password_nobody_is_there_to_type():
    cmd = wp.build_probe_command("/var/www/shop")
    assert "sudo -n" in cmd
    assert "sudo -u" not in cmd.replace("sudo -n -u", "")


def test_wp_is_resolved_to_an_absolute_path_before_it_is_run_as_someone_else():
    """sudo replaces PATH with its own secure_path, so looking wp up as ourselves and then
    running it as another account is how a check passes and the command after it fails."""
    cmd = wp.build_probe_command("/var/www/shop")
    assert "WP_BIN=$(command -v wp" in cmd
    assert "$WP_BIN" in cmd


def test_every_command_says_which_install_it_means():
    """wp-cli finds an install by walking up from the working directory, which over SSH is
    the login's home. Without --path it answers "this is not a WordPress installation" — and
    with stderr redirected, that arrives as silence."""
    assert "--path=$WP_PATH" in wp.build_probe_command("/var/www/shop")
    assert "--path=$WP_PATH" in wp.build_action_command("update_plugin", "/var/www/shop", "akismet")


# ── Reading changes nothing ──────────────────────────────────────────────────

def test_the_probe_contains_no_mutating_verb():
    cmd = wp.build_probe_command("/var/www/shop")
    mutators = ("rm", "rmdir", "mv", "cp", "dd", "mkfs", "chmod", "chown", "truncate",
                "apt", "yum", "dnf", "systemctl", "service", "kill", "reboot", "curl",
                "wget", "mysql", "crontab", "useradd")
    found = [m for m in mutators
             if re.search(r"(?<![\w-])" + re.escape(m) + r"(?![\w-])", cmd)]
    assert not found, f"mutating verb(s) in a read: {found}"
    for verb in ("plugin update", "core update", "user create", "db query", "option update"):
        assert verb not in cmd


@pytest.mark.parametrize("action", sorted(wp.ACTIONS))
def test_every_generated_command_is_valid_shell(action):
    cmd = wp.build_action_command(action, "/var/www/shop", "akismet")
    result = subprocess.run(["bash", "-n"], input=cmd, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_the_probe_is_valid_shell():
    result = subprocess.run(["bash", "-n"], input=wp.build_probe_command("/var/www/shop"),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


# ── Silence is not success ───────────────────────────────────────────────────

def test_a_site_whose_version_could_not_be_read_says_so_rather_than_looking_empty():
    """The live bug. Without --path every call failed, stderr went to /dev/null, and the
    screen rendered a real WordPress site as having no plugins, no admins and no version."""
    out = f"{S}|path|/var/www/shop\n{S}|owner|www-data\n{S}|core|\n{S}|plugins|\n"
    parsed = wp.parse_probe(out)
    assert parsed["ok"] is False
    assert "could not read" in parsed["reason"]


def test_a_real_but_genuinely_bare_install_still_reads_as_working():
    """A brand-new WordPress with no extra plugins is not a failure."""
    out = f"{S}|path|/var/www/shop\n{S}|owner|www-data\n{S}|core|6.9.4\n{S}|plugins|[]\n"
    parsed = wp.parse_probe(out)
    assert parsed["ok"] is True
    assert parsed["core_version"] == "6.9.4"
    assert parsed["plugins"] == []


@pytest.mark.parametrize("marker,fragment", [
    ("nowp", "wp-load.php"), ("nocli", "wp-cli is not installed"), ("nosudo", "owns this site"),
])
def test_each_reason_we_cannot_manage_a_site_is_named(marker, fragment):
    parsed = wp.parse_probe(f"{S}|error|{marker}")
    assert parsed["ok"] is False and fragment in parsed["reason"]


# ── Reading the real output ──────────────────────────────────────────────────

_REAL = (
    # Captured from aquafriendsbd.com on a live CyberPanel server.
    f'{S}|path|/home/aquafriendsbd.com/public_html\n'
    f'{S}|owner|aquafwkw\n'
    f'{S}|cli|WP-CLI 2.11.0\n'
    f'{S}|core|6.9.4\n'
    f'{S}|title|Aqua Friends BD\n'
    f'{S}|siteurl|https://aquafriendsbd.com\n'
    f'{S}|plugins|[{{"name":"woocommerce","title":"WooCommerce","status":"active",'
    f'"version":"8.8.7","update":"available","update_version":"10.9.4"}},'
    f'{{"name":"akismet","title":"Akismet","status":"inactive","version":"5.3",'
    f'"update":"none","update_version":""}}]\n'
    f'{S}|themes|[{{"name":"storefront","status":"active","version":"4.5",'
    f'"update":"none","update_version":""}}]\n'
    f'{S}|admins|[{{"ID":1,"user_login":"realowner","user_email":"a@b.com",'
    f'"display_name":"Owner"}}]\n'
    f'{S}|coreupdate|[{{"version":"6.9.5"}}]\n'
    f'{S}|maintenance|no\n'
    f'{S}|debug|\n'
)


def test_it_reads_versions_updates_and_who_can_sign_in():
    p = wp.parse_probe(_REAL)
    assert p["ok"] and p["core_version"] == "6.9.4" and p["core_update"] == "6.9.5"
    assert p["runs_as"] == "aquafwkw"
    assert p["site_url"] == "https://aquafriendsbd.com"
    woo = next(x for x in p["plugins"] if x["name"] == "woocommerce")
    assert woo["update_available"] and woo["update_version"] == "10.9.4"
    assert next(x for x in p["plugins"] if x["name"] == "akismet")["update_available"] is False
    assert p["admins"][0]["login"] == "realowner"
    # Core + one plugin. The inactive plugin and the current theme are not counted.
    assert p["updates_waiting"] == 2
    assert p["maintenance"] is False and p["debug"] is False


def test_a_failed_update_check_is_not_reported_as_up_to_date():
    """`core check-update` prints `[]` when current and NOTHING when it could not reach
    wordpress.org. Only the first is news; the second must not read as reassurance."""
    current = wp.parse_probe(_REAL.replace('|coreupdate|[{"version":"6.9.5"}]',
                                           "|coreupdate|[]"))
    assert current["core_update"] == "" and current["core_update_known"] is True

    unreachable = wp.parse_probe(_REAL.replace('|coreupdate|[{"version":"6.9.5"}]',
                                               "|coreupdate|"))
    assert unreachable["core_update"] == "" and unreachable["core_update_known"] is False


def test_broken_output_never_crashes_the_screen():
    for junk in ("", "bash: wp: not found", f"{S}|plugins|not json",
                 f"{S}|core|6.9\n{S}|plugins|[1,2,3]", f"{S}|truncated"):
        wp.parse_probe(junk)  # must not raise


# ── Actions are named, never composed ────────────────────────────────────────

def test_an_action_we_do_not_offer_is_refused():
    with pytest.raises(wp.WordPressError):
        wp.build_action_command("db_drop", "/var/www/shop")


@pytest.mark.parametrize("payload", [
    "akismet; rm -rf /", "../../etc/passwd", "$(whoami)", "a b", "plugin&&curl evil",
    "`id`", "'", '"', "..", "PLUGIN",
])
def test_a_plugin_name_that_is_not_a_plugin_name_is_refused_not_escaped(payload):
    """A slug is a small, well-defined shape. Refusing anything else is simpler to be sure
    of than quoting it, and there is no legitimate plugin this rejects."""
    assert wp.valid_slug(payload) is False
    with pytest.raises(wp.WordPressError):
        wp.build_action_command("update_plugin", "/var/www/shop", payload)


@pytest.mark.parametrize("good", ["akismet", "contact-form-7", "woo-variation-swatches",
                                  "wp2fa", "yith_wishlist", "some.plugin"])
def test_real_plugin_names_are_accepted(good):
    assert wp.valid_slug(good) is True


# ── The installer must produce a site this screen can manage ─────────────────

def test_installing_wordpress_also_installs_the_tool_it_is_managed_with():
    """Our own installer produced sites our own WordPress screen could not read.

    Found while wiring the screen up: `wordpress-site` never installed wp-cli, so every
    site ServerAlly created answered "wp-cli is not installed on this server".
    """
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    pb = next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == "wordpress-site")
    script = pb["script_bash"]
    assert "wp-cli.phar" in script
    assert "/usr/local/bin/wp" in script
    # Not installed twice on a server that already has it.
    assert "command -v wp >/dev/null" in script


def test_a_failed_wp_cli_download_does_not_fail_a_working_wordpress():
    """WordPress runs perfectly well without wp-cli. Losing the whole install over a tool
    the site itself does not need would be the wrong trade."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    script = next(p for p in OFFICIAL_PLAYBOOKS
                  if p["slug"] == "wordpress-site")["script_bash"]
    block = script[script.index("wp-cli.phar"):script.index("mysql -e \"CREATE DATABASE")]
    assert "exit 1" not in block, "a missing wp-cli must not abort the install"
    assert "could not be downloaded" in block, "and it must say so rather than go quiet"


def test_files_in_place_but_never_set_up_is_not_reported_as_healthy():
    """Found on production, on a site this product had just installed.

    WordPress's files can be present while nobody has opened install.php, so there is no
    database behind it. Every list then comes back empty and the screen said "0 plugins,
    everything up to date" — reassurance about a site that does not exist yet.
    """
    out = f"{S}|core|7.0.2\n{S}|setup|no\n{S}|plugins|\n{S}|admins|\n"
    p = wp.parse_probe(out)
    assert p["ok"] is True, "the install is readable — it is just unfinished"
    assert p["set_up"] is False


def test_a_finished_site_says_so():
    p = wp.parse_probe(_REAL + f"{S}|setup|yes\n")
    assert p["set_up"] is True


def test_the_probe_asks_whether_setup_was_ever_completed():
    assert "core is-installed" in wp.build_probe_command("/var/www/x")
