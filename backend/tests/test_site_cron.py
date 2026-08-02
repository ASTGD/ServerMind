"""Scheduling a job for one site.

The crontab is the server's, so this is a scoped adapter over cron_service rather than a
second implementation. What it owns is the two things a site owner cannot be expected to
know: which job their application needs, and which account it has to run as.
"""
import shlex

import pytest

from app.services import cron_service, site_cron_service as scs


# ── Which folder the job runs in ─────────────────────────────────────────────

def test_laravel_runs_from_above_the_folder_it_serves():
    """artisan sits one level up from public/. A job that runs in the served folder
    cannot find the thing it is meant to run."""
    assert scs.app_root("laravel", "/var/www/shop/public") == "/var/www/shop"


def test_a_laravel_site_not_serving_public_is_left_alone():
    assert scs.app_root("laravel", "/var/www/shop") == "/var/www/shop"


def test_wordpress_runs_where_it_is_served_from():
    assert scs.app_root("wordpress", "/var/www/blog") == "/var/www/blog"


def test_a_trailing_slash_does_not_change_the_folder():
    assert scs.app_root("laravel", "/var/www/shop/public/") == "/var/www/shop"


# ── What each application actually needs ─────────────────────────────────────

def test_laravel_gets_its_scheduler():
    job = scs.suggested_job("laravel", "/var/www/shop/public")
    assert job and "artisan schedule:run" in job["command"]
    assert job["command"].startswith("cd /var/www/shop &&")
    assert job["schedule"] == "* * * * *"


def test_wordpress_does_not_depend_on_a_tool_that_may_not_be_installed():
    """wp-cli is not on a site we merely discovered, and a suggestion that fails on half
    the sites it is offered for is worse than no suggestion."""
    job = scs.suggested_job("wordpress", "/var/www/blog")
    assert job and "wp-cron.php" in job["command"]
    assert "wp cron" not in job["command"]


def test_a_site_with_no_scheduled_work_is_not_given_invented_work():
    assert scs.suggested_job("php", "/var/www/plain") is None
    assert scs.suggested_job("unknown", "/var/www/plain") is None


def test_no_folder_means_no_suggestion():
    assert scs.suggested_job("laravel", "") is None


@pytest.mark.parametrize("app_type", ["laravel", "wordpress"])
def test_a_suggested_job_is_accepted_by_the_thing_that_installs_it(app_type):
    """The suggestion is not a separate dialect: it goes through the same validation as
    anything typed by hand, so an unrunnable suggestion cannot ship."""
    job = scs.suggested_job(app_type, "/var/www/site/public")
    assert cron_service.validate_schedule(job["schedule"])
    assert cron_service.validate_command(job["command"])


def test_an_awkward_folder_name_cannot_break_out_of_the_command():
    job = scs.suggested_job("laravel", "/var/www/it's here; rm -rf /public")
    root = scs.app_root("laravel", "/var/www/it's here; rm -rf /public")
    # Re-parsed the way a shell would: the whole path must survive as ONE argument, and
    # the `rm` must be part of it rather than a command of its own.
    parts = shlex.split(job["command"].split("&&")[0])
    assert parts == ["cd", root]


# ── Which account runs it ────────────────────────────────────────────────────

def test_the_owner_is_read_from_the_site_folder():
    cmd = scs.build_owner_command("/var/www/shop")
    assert "stat -c %U" in cmd and "/var/www/shop" in cmd


def test_a_folder_name_cannot_smuggle_a_second_command():
    evil = "/var/www/x; rm -rf /"
    cmd = scs.build_owner_command(evil)
    # Re-parsed the way a shell would: the whole path has to survive as ONE argument, so
    # the `rm` is a directory name and never a command.
    parts = shlex.split(cmd.split("||")[0])
    assert evil in parts, "the path was split into more than one argument"
    assert "rm" not in parts


@pytest.mark.parametrize("out,expected", [
    ("www-data\n", "www-data"),
    ("  deploy  \n", "deploy"),
    ("", None),
    ("\n", None),
    ("stat: cannot statx 'x': No such file or directory", None),  # has spaces
    ("a" * 40, None),                                             # not a username
])
def test_an_unreadable_owner_is_never_guessed(out, expected):
    """Falling back to root here is exactly the outcome this prevents: Laravel's scheduler
    run as root leaves root-owned files in storage/, and the site breaks days later."""
    assert scs.parse_owner(out) == expected


# ── Not nagging about a job that is already there ────────────────────────────

def test_a_site_already_running_its_scheduler_is_not_offered_one():
    jobs = [{"command": "cd /var/www/shop && php artisan schedule:run >> /dev/null 2>&1"}]
    assert scs.already_scheduled("laravel", jobs) is True


def test_somebody_elses_way_of_writing_it_still_counts():
    """A flock wrapper, a full path to php, a different redirect — all of these already
    solve the problem, and offering ours again would be nagging about a job sitting in the
    list right above."""
    jobs = [{"command": "flock -n /tmp/l /usr/bin/php8.3 /var/www/shop/artisan schedule:run"}]
    assert scs.already_scheduled("laravel", jobs) is True


def test_an_unrelated_job_does_not_count_as_the_scheduler():
    jobs = [{"command": "cd /var/www/shop && php artisan queue:work"}]
    assert scs.already_scheduled("laravel", jobs) is False


def test_wordpress_counts_only_the_thing_that_actually_runs_its_cron():
    assert scs.already_scheduled(
        "wordpress", [{"command": "php /var/www/blog/wp-cron.php"}]) is True
    assert scs.already_scheduled(
        "wordpress", [{"command": "cd /var/www/blog && wp cron event run --due-now"}]) is True


def test_an_app_we_have_no_suggestion_for_is_never_marked_as_covered():
    assert scs.already_scheduled("php", [{"command": "anything"}]) is False
