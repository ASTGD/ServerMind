"""The server's own crontab.

The expensive failure here is not a bad schedule — it is a lost job. A crontab is a
shared file that installers and people over SSH both write to, and editing it means
reading the whole thing and writing it back. Anything added in between disappears with
nothing said, and what disappears is usually a backup job nobody misses until they need
it.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

import pytest

from app.services import cron_service as cron


# --- Nothing we did not write is ever lost ---------------------------------------------

REAL_CRONTAB = """\
# Edited by hand, do not remove
PATH=/usr/local/bin:/usr/bin:/bin
MAILTO=ops@example.com

# nightly database dump
0 2 * * * /usr/local/bin/backup.sh --full

*/5 * * * * cd /var/www/shop && php artisan schedule:run >> /dev/null 2>&1
@reboot /usr/local/bin/warm-cache.sh
"""


def test_adding_a_job_keeps_every_existing_line():
    """The whole file is rewritten, so everything already in it has to survive."""
    result = cron.compose_add(REAL_CRONTAB, "0 4 * * *", "/usr/bin/certbot renew")
    for line in REAL_CRONTAB.splitlines():
        if line.strip():
            assert line in result, f"lost: {line}"
    assert "0 4 * * * /usr/bin/certbot renew" in result


def test_removing_a_job_takes_exactly_one_line():
    jobs = cron.parse_crontab(REAL_CRONTAB)
    target = next(j for j in jobs if "artisan" in j["command"])
    result = cron.compose_remove(REAL_CRONTAB, target["raw"])

    assert "artisan" not in result
    # Everything else is untouched, including the environment lines and the human's note.
    assert "/usr/local/bin/backup.sh --full" in result
    assert "MAILTO=ops@example.com" in result
    assert "# Edited by hand, do not remove" in result
    assert "warm-cache.sh" in result


def test_two_jobs_differing_only_by_schedule_do_not_confuse_the_removal():
    """Matching on the command alone would take out the wrong one.

    Removing the SECOND is the case that catches it: a loose match finds the first line
    containing that command, so deleting the first would pass a test that only ever
    deletes the first. Mutation testing is what showed that — the original version of
    this test removed job one and survived a deliberately broken matcher.
    """
    crontab = (
        "0 1 * * * /usr/local/bin/sync.sh\n"
        "0 13 * * * /usr/local/bin/sync.sh\n"
    )
    result = cron.compose_remove(crontab, "0 13 * * * /usr/local/bin/sync.sh")
    assert "0 1 * * * /usr/local/bin/sync.sh" in result, "took out the wrong job"
    assert "0 13 * * *" not in result

    # And the other direction, so neither ordering is special.
    result = cron.compose_remove(crontab, "0 1 * * * /usr/local/bin/sync.sh")
    assert "0 13 * * * /usr/local/bin/sync.sh" in result
    assert "0 1 * * *" not in result


def test_a_job_whose_command_is_a_prefix_of_another_is_not_confused():
    """`/backup.sh` appears inside `/backup.sh --full`; removing one must not take both."""
    crontab = (
        "0 2 * * * /usr/local/bin/backup.sh\n"
        "0 3 * * * /usr/local/bin/backup.sh --full\n"
    )
    result = cron.compose_remove(crontab, "0 2 * * * /usr/local/bin/backup.sh")
    assert "/usr/local/bin/backup.sh --full" in result
    assert result.count("backup.sh") == 1


def test_removing_a_line_that_is_gone_is_refused_rather_than_guessed():
    """If the file moved on, doing nothing quietly would report success on a job that is
    still scheduled."""
    with pytest.raises(cron.CronError) as exc:
        cron.compose_remove(REAL_CRONTAB, "0 9 * * * /something/else.sh")
    assert "no longer" in str(exc.value)


def test_our_own_comment_is_removed_with_its_job_but_a_human_note_is_not():
    crontab = (
        "# ServerAlly — renew certificates\n"
        "0 4 * * * /usr/bin/certbot renew\n"
        "# my own note about the next one\n"
        "0 5 * * * /usr/local/bin/thing.sh\n"
    )
    result = cron.compose_remove(crontab, "0 4 * * * /usr/bin/certbot renew")
    assert "# ServerAlly" not in result          # ours goes with its job
    assert "# my own note about the next one" in result   # theirs stays


# --- A write over a changed file is refused --------------------------------------------

def test_a_crontab_that_changed_since_it_was_read_is_not_overwritten():
    """This is the whole point: an entry added between the page loading and the button
    being pressed must not vanish."""
    read_at_load = REAL_CRONTAB
    stamp = cron.fingerprint(read_at_load)

    changed = read_at_load + "0 6 * * * /opt/installer/added-me.sh\n"
    with pytest.raises(cron.CronError) as exc:
        cron._check_unchanged(changed, stamp)
    message = str(exc.value)
    assert "changed" in message and "not applied" in message


def test_an_unchanged_crontab_writes_normally():
    cron._check_unchanged(REAL_CRONTAB, cron.fingerprint(REAL_CRONTAB))


def test_no_fingerprint_means_no_check():
    """A caller that did not read first (Ally, the API) is not forced through it."""
    cron._check_unchanged(REAL_CRONTAB, None)


def test_whitespace_alone_does_not_count_as_a_change():
    """A fingerprint that flapped on trailing whitespace would train people to ignore
    the warning."""
    assert cron.fingerprint("0 2 * * * x\n") == cron.fingerprint("0 2 * * * x\n")
    assert cron.fingerprint("0 2 * * * x\n") != cron.fingerprint("0 3 * * * x\n")


# --- Reading tells the truth about what is there ----------------------------------------

def test_environment_lines_are_not_listed_as_jobs():
    """PATH= and MAILTO= are settings, and offering to delete one as if it were a job
    would break every job below it."""
    jobs = cron.parse_crontab(REAL_CRONTAB)
    commands = [j["command"] for j in jobs]
    assert not any(c.startswith("PATH=") or c.startswith("MAILTO=") for c in commands)
    assert len(jobs) == 3


def test_a_line_we_cannot_parse_is_still_shown():
    """A job we do not understand is still a job the customer has, and hiding it would
    make the screen a lie."""
    jobs = cron.parse_crontab("something unparseable here\n")
    assert len(jobs) == 1
    assert jobs[0]["parsed"] is False
    assert jobs[0]["command"] == "something unparseable here"


def test_a_comment_above_a_job_is_kept_with_it():
    jobs = cron.parse_crontab(REAL_CRONTAB)
    backup = next(j for j in jobs if "backup.sh" in j["command"])
    assert backup["note"] == "nightly database dump"


def test_special_schedules_are_understood():
    jobs = cron.parse_crontab("@reboot /usr/local/bin/warm-cache.sh\n")
    assert jobs[0]["schedule"] == "@reboot"
    assert jobs[0]["command"] == "/usr/local/bin/warm-cache.sh"
    assert jobs[0]["description"] == "When the server starts"


def test_a_command_containing_spaces_and_redirects_survives_intact():
    """Splitting on the wrong field would silently change what runs."""
    line = "*/5 * * * * cd /var/www/shop && php artisan schedule:run >> /dev/null 2>&1"
    jobs = cron.parse_crontab(line + "\n")
    assert jobs[0]["command"] == "cd /var/www/shop && php artisan schedule:run >> /dev/null 2>&1"
    assert jobs[0]["schedule"] == "*/5 * * * *"


# --- Schedules are judged by a real parser ----------------------------------------------

@pytest.mark.parametrize("expression", [
    "* * * * *", "0 2 * * *", "*/15 * * * *", "0 9 * * 1-5",
    "30 4 1,15 * *", "0 0 * * SUN", "@daily", "@reboot",
])
def test_a_valid_schedule_is_accepted(expression):
    assert cron.validate_schedule(expression)


@pytest.mark.parametrize("expression", [
    "0 2 * *",            # four fields — the classic mistake
    "0 2 * * * *",        # six
    "",                   # nothing
    "@sometimes",         # not a real shorthand
    "99 * * * *",         # minute 99 does not exist
    "0 25 * * *",         # hour 25 does not exist
    "banana",             # a word
])
def test_an_invalid_schedule_is_refused(expression):
    """A wrong expression either never runs or runs constantly, and both look the same in
    a listing — so it is caught when it is typed, not discovered later."""
    with pytest.raises(cron.CronError):
        cron.validate_schedule(expression)


def test_the_five_field_message_says_how_many_were_given():
    with pytest.raises(cron.CronError) as exc:
        cron.validate_schedule("0 2 * *")
    assert "five parts" in str(exc.value) and "has 4" in str(exc.value)


# --- Descriptions are honest ------------------------------------------------------------

@pytest.mark.parametrize("expression,expected", [
    ("* * * * *", "Every minute"),
    ("*/5 * * * *", "Every 5 minutes"),
    ("0 2 * * *", "Every day at 2:00 am"),
    ("30 14 * * *", "Every day at 2:30 pm"),
    ("0 0 * * *", "Every day at midnight"),
    ("15 9 * * 1", "Every Monday at 9:15 am"),
    ("@reboot", "When the server starts"),
])
def test_a_common_schedule_is_described_in_words(expression, expected):
    assert cron.describe(expression) == expected


def test_an_unusual_schedule_is_shown_rather_than_described_badly():
    """A wrong description of when a job runs is worse than none, because it is believed."""
    for expression in ("0 9 1-5 * 2,4", "*/7 3-6 * * *", "0 0 29 2 *"):
        assert cron.describe(expression) == expression


# --- What goes into a crontab is still checked -------------------------------------------

def test_a_destructive_command_is_refused():
    """A scheduled job runs unattended, so a blocked command matters more here, not less."""
    with pytest.raises(cron.CronError) as exc:
        cron.validate_command("rm -rf /")
    assert "refused" in str(exc.value)


def test_a_multi_line_command_is_refused():
    """A crontab treats each line as its own job, so a second line would become a job
    nobody asked for — with the first line's schedule missing."""
    with pytest.raises(cron.CronError) as exc:
        cron.validate_command("echo one\nrm -rf /home")
    assert "single line" in str(exc.value)


def test_an_ordinary_command_is_allowed():
    """A false refusal here means a customer cannot schedule normal work."""
    for command in [
        "cd /var/www/shop && php artisan schedule:run >> /dev/null 2>&1",
        "/usr/bin/certbot renew --quiet",
        "mysqldump shop > /backups/shop.sql",
        "curl -s https://example.com/cron/run",
    ]:
        assert cron.validate_command(command)


@pytest.mark.parametrize("user", ["root; rm -rf /", "../etc", "user name", "", "-x"])
def test_a_user_name_is_validated_not_escaped(user):
    with pytest.raises(cron.CronError):
        cron.validate_user(user)


# --- Reading the server is read-only -----------------------------------------------------

def test_the_read_commands_only_read():
    for command in (cron.build_user_list_command(),
                    cron.build_read_command("root"),
                    cron.build_list_command(["root", "www-data"])):
        for mutating in (" rm ", "crontab -r", "crontab -e", " > /etc", "chmod", "chown"):
            assert mutating not in command, f"{mutating} in a read-only command"


def test_the_read_commands_are_valid_shell():
    for command in (cron.build_user_list_command(),
                    cron.build_read_command("root"),
                    cron.build_write_command("root", "/tmp/x")):
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
            fh.write("#!/bin/bash\n" + command + "\n")
            path = fh.name
        try:
            result = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
            assert result.returncode == 0, f"{command}\n{result.stderr}"
        finally:
            os.unlink(path)


def test_the_uploaded_crontab_is_removed_even_if_installing_it_fails():
    command = cron.build_write_command("root", "/tmp/.serverally-cron-abc")
    assert command.index("_rc=$?") < command.index("rm -f")
    assert "exit $_rc" in command


# --- The presets are the two jobs a site does not work without ---------------------------

def test_the_presets_are_usable_as_written():
    ids = {p["id"] for p in cron.PRESETS}
    assert {"laravel", "wp-cron"} <= ids
    for preset in cron.PRESETS:
        # The schedule has to be one the server will accept, or the one-click is a
        # one-click error.
        assert cron.validate_schedule(preset["schedule"])
        # And the command must survive the safety check once its path is filled in.
        filled = preset["command"].format(path="/var/www/shop.example.com")
        assert cron.validate_command(filled)


def test_a_note_survives_the_round_trip_intact():
    """Found live: the marker we write uses an em dash, and the parser did not strip it,
    so a note came back as "— nightly backup"."""
    crontab = cron.compose_add("", "0 2 * * *", "/usr/local/bin/backup.sh", "nightly backup")
    job = cron.parse_crontab(crontab)[0]
    assert job["note"] == "nightly backup"
    assert job["schedule"] == "0 2 * * *"
    assert job["command"] == "/usr/local/bin/backup.sh"


def test_a_job_added_without_a_note_has_none():
    job = cron.parse_crontab(cron.compose_add("", "0 2 * * *", "/bin/true"))[0]
    assert job["note"] is None


# --- One site's scheduled jobs ------------------------------------------------------------

SITE_CRONTAB = [
    {"user": "root", "fingerprint": "abc", "jobs": [
        {"raw": "* * * * * cd /var/www/shop.example.com && php artisan schedule:run",
         "schedule": "* * * * *", "command": "cd /var/www/shop.example.com && php artisan schedule:run",
         "description": "Every minute", "note": None, "parsed": True},
        {"raw": "*/5 * * * * cd /var/www/other.example.com && php -q wp-cron.php",
         "schedule": "*/5 * * * *", "command": "cd /var/www/other.example.com && php -q wp-cron.php",
         "description": "Every 5 minutes", "note": None, "parsed": True},
        {"raw": "0 2 * * * /usr/local/bin/backup.sh --all",
         "schedule": "0 2 * * *", "command": "/usr/local/bin/backup.sh --all",
         "description": "Every day at 2:00 am", "note": None, "parsed": True},
    ]},
]


def test_only_this_site_s_jobs_are_shown():
    jobs = cron.jobs_for_site(SITE_CRONTAB, "shop.example.com",
                              "/var/www/shop.example.com/public")
    assert len(jobs) == 1
    assert "shop.example.com" in jobs[0]["command"]


def test_a_neighbouring_site_s_job_is_not_claimed():
    """Two sites on one server, both with a Laravel scheduler. Showing the wrong one under
    the wrong site is how someone deletes a job that was keeping another site alive."""
    jobs = cron.jobs_for_site(SITE_CRONTAB, "other.example.com",
                              "/var/www/other.example.com")
    assert len(jobs) == 1
    assert "other.example.com" in jobs[0]["command"]


def test_a_server_wide_job_belongs_to_no_site():
    """The nightly backup is the machine's, not any one site's."""
    for domain, root in (("shop.example.com", "/var/www/shop.example.com"),
                         ("other.example.com", "/var/www/other.example.com")):
        assert not any("backup.sh" in j["command"]
                       for j in cron.jobs_for_site(SITE_CRONTAB, domain, root))


def test_a_public_docroot_still_matches_the_site_folder():
    """Laravel serves from public/, but its cron job names the folder above it."""
    jobs = cron.jobs_for_site(SITE_CRONTAB, "shop.example.com",
                              "/var/www/shop.example.com/public")
    assert jobs, "the site's own scheduler job was not found"


def test_a_job_that_only_mentions_the_domain_still_counts():
    """Not every job is written with a path — a health check is written with a URL."""
    crontab = [{"user": "root", "fingerprint": "x", "jobs": [
        {"raw": "*/5 * * * * curl -s https://shop.example.com/health",
         "schedule": "*/5 * * * *", "command": "curl -s https://shop.example.com/health",
         "description": "", "note": None, "parsed": True}]}]
    assert len(cron.jobs_for_site(crontab, "shop.example.com", None)) == 1


def test_a_site_with_nothing_scheduled_gets_an_empty_list_not_everything():
    assert cron.jobs_for_site(SITE_CRONTAB, "unrelated.example.com",
                              "/var/www/unrelated.example.com") == []
