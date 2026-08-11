"""Editing wp-config.php — Ploi's WordPress → Configuration.

The file every WordPress owner is told to edit and never does, because getting it wrong takes
the site down completely: it is PHP, loaded before anything else, and a missing semicolon
produces a blank page with no message anywhere a customer would look.

The apply command is RUN against a real `php -l` and a real web server, because "is this
valid PHP" and "does the site still load" are not questions a string can answer.
"""
import shutil
import subprocess

import pytest

from app.services import wp_config_service as wc


GOOD = """<?php
define( 'DB_NAME', 'wp' );
define( 'DB_USER', 'wpuser' );
define( 'DB_PASSWORD', 'sekrit' );
define( 'DB_HOST', 'localhost' );
$table_prefix = 'wp_';
/* That's all, stop editing! Happy publishing. */
require_once ABSPATH . 'wp-settings.php';
"""


# ── Refused before the server is touched ─────────────────────────────────────

def test_an_empty_file_is_refused_and_says_why():
    """It would take the site down completely, and it is what a select-all-delete produces.

    The `<?php` check below would refuse this too, so what this guard actually provides is
    the MESSAGE — "empty" rather than "has to start with <?php", which is not useful advice
    for somebody who just deleted the whole file. So that is what is asserted; a mutation run
    proved the alternative version of this test could not tell the two apart."""
    for blank in ("", "   \n "):
        with pytest.raises(wc.WpConfigError) as exc:
            wc.check_content(blank)
        assert "empty" in str(exc.value).lower(), str(exc.value)


def test_something_that_is_not_php_is_refused():
    with pytest.raises(wc.WpConfigError) as exc:
        wc.check_content("DB_NAME=wp\nDB_USER=x\n")
    assert "<?php" in str(exc.value)


@pytest.mark.parametrize("missing", ["DB_NAME", "DB_USER"])
def test_losing_a_constant_wordpress_cannot_start_without_is_refused(missing):
    """The classic paste-over-the-top accident, and it produces the same blank page as a
    syntax error — with nothing in the file to hint at what happened."""
    broken = GOOD.replace(f"'{missing}'", "'SOMETHING_ELSE'")
    with pytest.raises(wc.WpConfigError) as exc:
        wc.check_content(broken)
    assert missing in str(exc.value)


def test_a_good_file_is_accepted_and_ends_with_a_newline():
    out = wc.check_content(GOOD.rstrip("\n"))
    assert out.endswith(b"\n")


# ── The warning that saves the most confusion ────────────────────────────────

def test_a_define_below_the_stop_editing_line_is_flagged():
    """WordPress loads the rest of itself there and never reads what follows. The setting is
    plainly in the file and has no effect — the most confusing outcome this screen can
    produce, so it is said rather than silently allowed."""
    text = GOOD + "define( 'WP_MEMORY_LIMIT', '256M' );\n"
    warned = wc.warnings(text)
    assert any("below the" in w for w in warned)


def test_a_define_above_that_line_is_not_flagged():
    text = GOOD.replace("/* That's all",
                        "define( 'WP_MEMORY_LIMIT', '256M' );\n/* That's all")
    assert not any("below the" in w for w in wc.warnings(text))


def test_a_file_that_never_loads_wordpress_is_flagged():
    assert any("wp-settings" in w for w in wc.warnings("<?php\ndefine('DB_NAME','x');\n"))


def test_debug_without_display_off_is_flagged():
    """WP_DEBUG alone prints PHP errors into the page for every visitor."""
    text = GOOD.replace("$table_prefix", "define( 'WP_DEBUG', true );\n$table_prefix")
    assert any("WP_DEBUG_DISPLAY" in w for w in wc.warnings(text))


# ── Showing it back ──────────────────────────────────────────────────────────

def test_the_password_and_salts_are_masked_for_display():
    masked, hidden = wc.redact(GOOD + "define('AUTH_KEY', 'abc123');\n")
    assert "sekrit" not in masked and "abc123" not in masked
    assert hidden == 2
    assert "DB_NAME" in masked and "'wp'" in masked, "structure stays readable"


def test_the_editable_content_is_not_the_masked_one():
    """A masked value saved back would write the mask into the file. The browser already
    holds the real values because that is what editing means — the split is deliberate."""
    import inspect

    from app.routers import sites

    src = inspect.getsource(sites.read_wp_config)
    assert '"content": text' in src, "the editor must get the real file"
    assert '_masked' in src, "the mask is computed only to COUNT what is secret"


# ── Nothing secret goes near a command line ──────────────────────────────────

def test_the_command_never_carries_the_file():
    cmd = wc.build_apply_command("/var/www/shop", "shop.com")
    assert "DB_PASSWORD" not in cmd and "sekrit" not in cmd
    assert wc.TMP_NAME in cmd, "the content arrives over SFTP, beside the real file"


def test_the_discard_command_only_ever_removes_our_own_file():
    cmd = wc.build_discard_command("/var/www/shop")
    assert wc.TMP_NAME in cmd
    assert "wp-config.php" not in cmd.replace(wc.TMP_NAME, "")


# ── Run it ───────────────────────────────────────────────────────────────────

php = pytest.mark.skipif(shutil.which("php") is None, reason="needs php for -l")


def _run(tmp_path, content: str, *, existing: str = GOOD, code: str = "200",
         body: str = "SITE", before: str = "200"):
    """Execute the real generated command with a stubbed web server."""
    binstub = tmp_path / "bin"
    binstub.mkdir(exist_ok=True)
    # A `for a in "$@"` loop cannot consume the value after -o — `shift` does not move the
    # loop's own cursor — so this walks the arguments properly. My first version silently
    # wrote the body to /dev/null, which made every run look like a broken site.
    (binstub / "curl").write_text(
        "#!/bin/sh\n"
        'if [ -f /tmp/.sa_wpseen ]; then C="' + code + '"; else C="' + before + '"; '
        "touch /tmp/.sa_wpseen; fi\n"
        'OUT=/dev/null\n'
        'while [ $# -gt 0 ]; do case "$1" in -o) OUT="$2"; shift 2;; *) shift;; esac; done\n'
        'printf "%s" "' + body + '" > "$OUT"\n'
        'printf "%s" "$C"\n')
    (binstub / "curl").chmod(0o755)

    root = tmp_path / "site"
    root.mkdir(exist_ok=True)
    (root / "wp-config.php").write_text(existing)
    (root / wc.TMP_NAME).write_text(content)

    cmd = wc.build_apply_command(str(root), "shop.com", php_bin=shutil.which("php") or "php")
    proc = subprocess.run(
        ["bash", "-c", f'rm -f /tmp/.sa_wpseen; export PATH="{binstub}:$PATH"; {cmd}'],
        capture_output=True, text=True)
    return proc.returncode, (root / "wp-config.php").read_text(), proc.stdout + proc.stderr


@php
def test_a_good_file_is_saved(tmp_path):
    new = GOOD.replace("'wp'", "'wordpress'")
    code, on_disk, out = _run(tmp_path, new)
    assert code == 0, out
    assert on_disk == new
    assert wc.explain(code, out)[0] is True


@php
def test_invalid_php_never_replaces_the_real_file(tmp_path):
    """The order is the safety: parse the NEW file first. Replacing and checking after leaves
    a window where every visitor gets a blank page."""
    code, on_disk, out = _run(tmp_path, "<?php\ndefine('DB_NAME' 'wp');\ndefine('DB_USER','u');\n")
    assert code == 6, out
    assert on_disk == GOOD, "the live file must be untouched"
    ok, message = wc.explain(code, out)
    assert ok is False and "not valid PHP" in message


@php
def test_the_temporary_copy_never_survives_a_refusal(tmp_path):
    """It sits beside the real file and holds the same credentials."""
    root = tmp_path / "site"
    _code, _disk, _out = _run(tmp_path, "<?php bad bad\n")
    assert not (root / wc.TMP_NAME).exists()


@php
def test_a_site_that_stops_loading_gets_its_old_file_back(tmp_path):
    code, on_disk, out = _run(tmp_path, GOOD.replace("'wp'", "'other'"), code="500", body="")
    assert code == 5, out
    assert on_disk == GOOD
    assert "put back" in wc.explain(code, out)[1]


@php
def test_a_blank_200_counts_as_broken(tmp_path):
    """A broken wp-config produces an empty 200 as often as it produces a 500."""
    code, on_disk, _out = _run(tmp_path, GOOD.replace("'wp'", "'other'"), code="200", body="")
    assert code == 5
    assert on_disk == GOOD


@php
def test_a_site_that_was_already_down_keeps_the_change(tmp_path):
    """Reverting on a pre-existing outage leaves somebody unable to edit the file at exactly
    the moment they are trying to fix the site with it."""
    new = GOOD.replace("'wp'", "'other'")
    code, on_disk, out = _run(tmp_path, new, before="500", code="500", body="")
    assert code == 0, out
    assert on_disk == new
    assert "already not loading" in wc.explain(code, out)[1]


@php
def test_the_file_keeps_its_permissions(tmp_path):
    import os
    import stat

    root = tmp_path / "site"
    root.mkdir(exist_ok=True)
    (root / "wp-config.php").write_text(GOOD)
    os.chmod(root / "wp-config.php", 0o640)
    _run(tmp_path, GOOD.replace("'wp'", "'x'"), existing=GOOD)
    assert stat.S_IMODE(os.stat(root / "wp-config.php").st_mode) == 0o640, (
        "a wp-config the web server cannot read makes every page a 500")
