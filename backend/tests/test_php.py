"""PHP versions — reading them safely, and switching a site without breaking it.

Which PHP a server runs is not cosmetic: current Laravel needs 8.3+, and the older Laravel
that would run on Ubuntu 22.04's PHP 8.1 has security advisories Composer refuses to
install. So this decides whether a customer can host their application at all.

Reading is free. Installing is additive. Switching one site is the only operation here that
can take a live website down, so most of these tests are about that.
"""
from __future__ import annotations

import shlex

import pytest

from app.services import php_service as p


# ── the probe ────────────────────────────────────────────────────────────────
def test_the_probe_only_ever_reads():
    """Same rule as the metrics, security, log and site probes: a fixed bundle authored
    here, never assembled from anything a user typed, and it must not change the server."""
    cmd = p.build_probe()
    for mutator in ("rm ", "mv ", " > /etc", "tee ", "sed -i", "chmod ", "chown ",
                    "systemctl restart", "systemctl reload", "apt-get", "dnf "):
        assert mutator not in cmd, f"the read probe must not contain {mutator!r}"


def test_the_probe_is_bounded():
    """ssh_service reads with a 60s channel timeout, so an unbounded command on a busy box
    surfaces as a mystery hang rather than a slow answer."""
    assert "timeout" in p.build_probe()


def test_a_missing_timeout_binary_fails_open():
    """Failing closed would be worse than slow here: an empty probe reads as "no PHP
    installed", which is a confident wrong answer."""
    cmd = p.build_probe()
    assert "command -v timeout" in cmd and "else" in cmd


def test_it_reads_versions_fpm_state_and_each_site():
    out = "\n".join([
        f"{p._SENTINEL}|version|8.1",
        f"{p._SENTINEL}|version|8.3",
        f"{p._SENTINEL}|fpm|8.1|dead",
        f"{p._SENTINEL}|fpm|8.3|running",
        f"{p._SENTINEL}|cli|8.3",
        f"{p._SENTINEL}|site|/etc/nginx/sites-available/shop.com|/run/php/php8.1-fpm.sock",
        f"{p._SENTINEL}|site|/etc/nginx/sites-available/app.com|/run/php/php8.3-fpm.sock",
        f"{p._SENTINEL}|done|",
    ])
    got = p.parse_probe(out)
    assert got["versions"] == ["8.1", "8.3"]
    assert got["running"] == ["8.3"]
    assert got["cli_default"] == "8.3"
    assert [s["version"] for s in got["sites"]] == ["8.3", "8.1"]  # sorted by path
    assert got["sites"][0]["name"] == "app.com"


def test_versions_are_sorted_as_numbers_not_text():
    """Otherwise 8.10 sorts before 8.9 and the newest version is not the last one."""
    out = "\n".join(f"{p._SENTINEL}|version|{v}" for v in ("8.9", "8.10", "8.1"))
    assert p.parse_probe(out)["versions"] == ["8.1", "8.9", "8.10"]


def test_junk_lines_are_ignored_rather_than_shown_as_versions():
    out = "\n".join([
        "some unrelated output",
        f"{p._SENTINEL}|version|",
        f"{p._SENTINEL}|version|not-a-version",
        f"{p._SENTINEL}|version|/usr/bin/php",
        f"{p._SENTINEL}|version|8.3",
    ])
    assert p.parse_probe(out)["versions"] == ["8.3"]


def test_a_site_path_outside_etc_is_ignored():
    """The switch endpoint allowlists against these paths, so nothing else may enter."""
    out = f"{p._SENTINEL}|site|/tmp/evil.conf|/run/php/php8.3-fpm.sock"
    assert p.parse_probe(out)["sites"] == []


def test_an_empty_probe_is_empty_not_an_error():
    got = p.parse_probe("")
    assert got == {"versions": [], "running": [], "cli_default": None, "sites": []}


# ── the version itself ───────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["", "8", "eight", "8.3.1", "8.3; rm -rf /", "../8.3", "8.3 "])
def test_a_version_is_validated_not_escaped(bad):
    """It lands in a filesystem path, a service name and a config file. Refusing anything
    that is not a version is more reliable than escaping it correctly in three places."""
    if bad == "8.3 ":
        assert p.valid_version(bad) == "8.3"   # trimmed, not rejected
        return
    with pytest.raises(ValueError):
        p.valid_version(bad)


def test_a_real_version_passes():
    assert p.valid_version("8.3") == "8.3"
    assert p.valid_version(" 8.10 ") == "8.10"


# ── switching, which is the dangerous part ───────────────────────────────────
def test_the_switch_keeps_a_copy_before_touching_anything():
    cmd = p.build_switch_command("/etc/nginx/sites-available/shop.com", "8.3", "shop.com")
    assert 'cp -p "$CFG" "$BK"' in cmd
    assert cmd.index('cp -p "$CFG" "$BK"') < cmd.index("sed -i")


def test_the_switch_refuses_if_the_target_php_is_not_running():
    """Pointing a site at a socket that does not exist is an immediate 502 for every visitor."""
    cmd = p.build_switch_command("/etc/nginx/x", "8.3", "x.com")
    assert '[ ! -S "$SOCK" ]' in cmd
    assert cmd.index('[ ! -S "$SOCK" ]') < cmd.index("sed -i")


def test_the_config_is_tested_before_the_reload():
    """Reloading a config that does not parse takes down every site on the server."""
    cmd = p.build_switch_command("/etc/nginx/x", "8.3", "x.com")
    assert cmd.index("nginx -t") < cmd.index("systemctl reload")


def test_a_site_that_breaks_is_put_back_on_the_version_it_had():
    """The whole risk of this feature: an app written for an older PHP can throw a fatal
    error on a newer one and the site goes white the moment the config reloads."""
    cmd = p.build_switch_command("/etc/nginx/x", "8.3", "x.com")
    after_check = cmd[cmd.index('if [ "$OK" != yes ]'):]
    assert 'cp -p "$BK" "$CFG"' in after_check, "the old config must be restored"
    assert "systemctl reload" in after_check, "and the restore must be applied"
    assert "exit 5" in after_check


def test_success_is_judged_on_the_BODY_not_only_the_status():
    """A broken PHP app very often returns 200 with a blank or error body, so a status code
    alone would call a dead site healthy."""
    cmd = p.build_switch_command("/etc/nginx/x", "8.3", "x.com")
    assert '[ -n "$B" ]' in cmd, "an empty body must not count as working"


def test_the_check_retries_rather_than_racing_the_reload():
    """reload returns before the workers have swapped, so an immediate request can still be
    answered by the old configuration — the same trap that produced a false warning in the
    site installers."""
    assert "for i in 1 2 3 4 5 6" in p.build_switch_command("/etc/nginx/x", "8.3", "x.com")


def test_the_path_and_domain_are_quoted():
    """They come from a request. The path is also allowlisted in the router, but quoting is
    the layer that does not depend on that check being right."""
    cmd = p.build_switch_command("/etc/nginx/sites-available/a b.com", "8.3", "a b.com")
    assert shlex.quote("/etc/nginx/sites-available/a b.com") in cmd
    assert shlex.quote("a b.com") in cmd


def test_only_the_socket_line_is_rewritten():
    """Everything else in a customer's vhost — rewrites, headers, tuning — must survive."""
    cmd = p.build_switch_command("/etc/nginx/x", "8.3", "x.com")
    assert "fpm" in cmd and ".sock" in cmd
    assert "server_name" not in cmd and "root " not in cmd


# ── what the owner is told ───────────────────────────────────────────────────
@pytest.mark.parametrize("code,expect_ok,contains", [
    (0, True, "now running"),
    (3, False, "not running on this server"),
    (4, False, "refused the new configuration"),
    (5, False, "put back on the version it had"),
    (1, False, "could not be made"),
])
def test_each_outcome_is_explained_in_plain_words(code, expect_ok, contains):
    ok, msg = p.explain_switch(code, "shop.com is now running on PHP 8.3.")
    assert ok is expect_ok
    assert contains in msg.lower(), f"code {code} said: {msg}"


def test_no_failure_ever_carries_a_success_sounding_message():
    """The trap: if the script prints its success line and then fails on the step after,
    echoing that line back tells the owner their site moved to PHP 8.3 when it did not. So
    the message for every failure is ours, and the output is only appended as detail."""
    for code in (1, 3, 4, 5):
        ok, msg = p.explain_switch(code, "shop.com is now running on PHP 8.3.")
        assert ok is False
        assert not msg.startswith("shop.com is now running"), f"code {code} led with success"


def test_a_refusal_never_reads_as_success():
    for code in (1, 3, 4, 5):
        ok, _ = p.explain_switch(code, "")
        assert ok is False


# ── what running it against a real two-version box exposed ───────────────────
def test_commented_out_config_lines_are_not_read_as_live_state():
    """nginx's own default vhost carries a commented `fastcgi_pass ... php7.4-fpm.sock`.
    Reading it reported PHP 7.4 as a site's live version on a server where 7.4 was not even
    installed — and that is the state a switch would be judged against."""
    assert 's/#.*$//' in p.build_probe(), "comments must be stripped before matching"


def test_the_switch_actually_exercises_php_not_just_the_homepage():
    """Found live: most sites serve a static index.html at "/", so nginx answers happily even
    when the FPM socket it was just pointed at is dead. A homepage check alone let a switch
    onto a broken socket report success."""
    cmd = p.build_switch_command("/etc/nginx/x", "8.3", "x.com")
    assert "serverally-phpcheck" in cmd, "a throwaway PHP file must prove PHP executes"
    assert "SMPHPOK:$V" in cmd, "and that it is the version we asked for"


def test_the_php_check_file_is_always_removed():
    cmd = p.build_switch_command("/etc/nginx/x", "8.3", "x.com")
    assert 'rm -f "$PP"' in cmd
    # Removed before the pass/fail decision, so a failure cannot leave it behind either.
    assert cmd.index('rm -f "$PP"') < cmd.index('if [ "$OK" != yes ]')


def test_a_failed_php_check_forces_the_rollback():
    """Verified live with a socket that existed but did not answer: exit 6, the config was
    restored, and the site was working again afterwards."""
    cmd = p.build_switch_command("/etc/nginx/x", "8.3", "x.com")
    assert '[ "$PHP_OK" = no ] && OK=no' in cmd
    assert "exit 6" in cmd


def test_php_not_running_and_the_site_breaking_are_told_apart():
    """They need different advice: a missing extension versus an application that is not
    ready for the version."""
    _ok6, m6 = p.explain_switch(6, "")
    _ok5, m5 = p.explain_switch(5, "")
    assert "extension" in m6
    assert "not ready" in m5
    assert m5 != m6


def test_the_docroot_is_read_from_the_config_not_guessed():
    """It must be the root this site is actually served from, or the PHP check writes its
    probe file somewhere the site does not serve and always reports failure."""
    cmd = p.build_switch_command("/etc/nginx/x", "8.3", "x.com")
    assert "DocumentRoot" in cmd and "root" in cmd
    assert cmd.index("DOCROOT=") < cmd.index("serverally-phpcheck")
