"""Laravel, the registry's second entry — and deliberately not shaped like the first.

WordPress is content you administer. Laravel is a codebase you deploy, so what matters is
the CONDITION of the deployment. Two findings justify the whole screen, because neither is
visible from outside and both are common:

- debug mode left on in production, which prints the database password to any visitor who
  can make the site throw an error;
- no scheduler entry in cron, after which nothing scheduled ever runs and nothing anywhere
  reports a failure.
"""
from __future__ import annotations

import json
import re
import subprocess

import pytest

from app.services import app_registry, laravel_service as lv

S = "___SM_LARAVEL___"


def _out(**fields) -> str:
    return "\n".join(f"{S}|{k}|{v}" for k, v in fields.items())


def _healthy(**over) -> dict:
    base = dict(path="/var/www/acme", owner="acme", php="8.3.6",
                version="Laravel Framework 11.9.2",
                about=json.dumps({
                    "environment": {"laravel_version": "11.9.2", "php_version": "8.3.6",
                                    "environment": "production", "debug_mode": False,
                                    "maintenance_mode": False},
                    "cache": {"config": "CACHED", "routes": "CACHED", "events": "NOT CACHED"},
                }),
                env="production", debug="false",
                cache_config="yes", cache_routes="yes", cache_events="no",
                maintenance="no", storage_link="yes",
                migrations="  Ran ~  Ran ~", queue="yes", scheduler="yes")
    base.update(over)
    return lv.parse_probe(_out(**base))


# ── The registry ─────────────────────────────────────────────────────────────

def test_laravel_is_in_the_registry_and_named_after_itself():
    spec = app_registry.app_for("laravel")
    assert spec is not None and spec.label == "Laravel"


# ── Reading changes nothing ──────────────────────────────────────────────────

def test_the_probe_contains_no_mutating_verb():
    cmd = lv.build_probe_command("/var/www/acme/public")
    mutators = ("rm", "rmdir", "mv", "cp", "dd", "chmod", "chown", "truncate", "tee",
                "apt", "yum", "systemctl", "service", "kill", "reboot", "curl", "wget",
                "mysql", "useradd")
    found = [m for m in mutators
             if re.search(r"(?<![\w-])" + re.escape(m) + r"(?![\w-])", cmd)]
    assert not found, f"mutating verb(s) in a read: {found}"
    # Precisely the WRITE forms. `migrate:status` is a read and belongs here — asserting on
    # "$ART migrate" alone would reject it, which is a test that misunderstands the code.
    for verb in ("migrate --force", "optimize", "optimize:clear", "config:cache",
                 "down", "up", "storage:link", "queue:restart"):
        assert f"$ART {verb}" not in cmd, f"the read probe runs `artisan {verb}`"
    assert "$ART migrate:status" in cmd, "reading the migration list IS a read"


def test_the_probe_never_reads_the_whole_env_file():
    """`.env` holds the database password. Two named non-secret lines are extracted; the
    file itself is never read, the same rule the discovery probe follows for wp-config."""
    cmd = lv.build_probe_command("/var/www/acme")
    # Anchored to the start of a line and to one named key, so it can only ever match the
    # variable it was asked for.
    assert 'grep -m1 "^$1="' in cmd
    assert "_envval APP_ENV" in cmd and "_envval APP_DEBUG" in cmd
    for secret in ("DB_PASSWORD", "cat \"$APP_PATH/.env\"", "DB_USERNAME", "APP_KEY"):
        assert secret not in cmd


def test_the_probe_and_every_action_are_valid_shell():
    assert subprocess.run(["bash", "-n"], text=True, capture_output=True,
                          input=lv.build_probe_command("/var/www/a")).returncode == 0
    for action in lv.ACTIONS:
        r = subprocess.run(["bash", "-n"], text=True, capture_output=True,
                           input=lv.build_action_command(action, "/var/www/a"))
        assert r.returncode == 0, f"{action}: {r.stderr}"


def test_a_path_with_shell_characters_cannot_become_a_second_command():
    """The document root is the one piece of stored input reaching this shell.

    Parsed back the way a shell would rather than checked for absence — quoting keeps the
    text and removes its power, so "is it missing" is the wrong question.
    """
    import shlex
    payload = "/var/www/x; touch /tmp/pwned"
    line = next(l for l in lv.build_probe_command(payload).splitlines()
                if l.startswith("for d in "))
    argv = shlex.split(line[len("for d in "):].rsplit(";", 1)[0])
    assert payload in argv, f"the path did not survive as one argument: {argv}"
    assert "touch" not in argv, f"the payload became its own command: {argv}"


# ── The two findings the screen exists for ───────────────────────────────────

def test_debug_left_on_in_production_is_reported_as_such():
    p = _healthy(about=json.dumps({
        "environment": {"environment": "production", "debug_mode": True},
        "cache": {"config": "CACHED"}}))
    assert p["debug"] is True
    assert p["debug_in_production"] is True


def test_debug_on_while_developing_is_not_the_same_finding():
    p = _healthy(about=json.dumps({
        "environment": {"environment": "local", "debug_mode": True}, "cache": {}}))
    assert p["debug"] is True
    assert p["debug_in_production"] is False


def test_the_running_configuration_beats_the_env_file():
    """The correctness point. After `artisan config:cache`, Laravel stops reading .env — so
    a .env saying APP_DEBUG=false can sit above a live site running with debug ON. Reading
    the file would report the reassuring value and be wrong exactly when it matters."""
    p = _healthy(
        debug="false",                       # what .env claims
        about=json.dumps({"environment": {"environment": "production", "debug_mode": True},
                          "cache": {"config": "CACHED"}}))
    assert p["debug"] is True, "the cached config is what the site is actually running"
    assert p["debug_in_production"] is True


def test_a_laravel_too_old_for_about_falls_back_to_the_env_file():
    p = _healthy(about="", debug="true", env="production")
    assert p["debug"] is True and p["debug_in_production"] is True


def test_a_missing_scheduler_entry_is_visible():
    assert _healthy(scheduler="no")["scheduler"] is False
    assert _healthy(scheduler="yes")["scheduler"] is True


# ── Honest about what it could not learn ─────────────────────────────────────

def test_a_migration_check_that_could_not_run_is_not_reported_as_none_pending():
    """Reaching the database can fail. "0 waiting" would be a reassuring guess."""
    p = _healthy(migrations="")
    assert p["migrations_known"] is False
    assert p["pending_migrations"] == 0, "the count is meaningless, and the flag says so"


def test_pending_migrations_are_counted():
    p = _healthy(migrations="  Pending ~  Ran ~  Pending ~  Pending ~")
    assert p["migrations_known"] is True and p["pending_migrations"] == 3


def test_an_app_whose_artisan_never_started_says_so_rather_than_looking_healthy():
    """Every call redirects stderr so a warning cannot corrupt what it captures — which makes
    a failure silent, and silence renders as a healthy app with nothing to report."""
    p = lv.parse_probe(_out(path="/var/www/a", owner="acme", version=""))
    assert p["ok"] is False and "artisan could not start" in p["reason"]


@pytest.mark.parametrize("marker,fragment", [
    ("noapp", "artisan file"), ("nophp", "PHP is not installed"),
    ("novendor", "vendor folder"), ("nosudo", "owns this site"),
])
def test_each_reason_we_cannot_manage_a_site_is_named(marker, fragment):
    p = lv.parse_probe(f"{S}|error|{marker}")
    assert p["ok"] is False and fragment in p["reason"]


def test_a_missing_vendor_folder_is_named_specifically():
    """The most common broken state — a clone that never had composer install run — and the
    fix is obvious once it is named, rather than "artisan could not start"."""
    assert "composer install" in lv.parse_probe(f"{S}|error|novendor")["reason"]


def test_broken_output_never_crashes_the_screen():
    for junk in ("", "bash: php: not found", f"{S}|about|not json",
                 f"{S}|version|x\n{S}|about|[1,2]", f"{S}|truncated"):
        lv.parse_probe(junk)


# ── Actions are named, never composed ────────────────────────────────────────

def test_an_action_we_do_not_offer_is_refused():
    for bogus in ("db:wipe", "tinker", "migrate:fresh", ""):
        with pytest.raises(lv.LaravelError):
            lv.build_action_command(bogus, "/var/www/a")


def test_no_action_takes_customer_input_at_all():
    """There is no target parameter, so no customer text reaches any of these command lines.
    Locked here so adding one later has to be a deliberate decision."""
    import inspect
    sig = inspect.signature(lv.build_action_command)
    assert list(sig.parameters) == ["action", "doc_root"]


def test_migrations_run_unattended_and_are_marked_as_the_destructive_one():
    cmd = lv.build_action_command("migrate", "/var/www/a")
    # artisan refuses to migrate in production without this, and nobody is at a terminal.
    assert "--force" in cmd
    assert "migrate" in lv.DESTRUCTIVE
    assert lv.DESTRUCTIVE == {"migrate"}, "only the one that can lose data"


# ── Three bugs found by pointing this at a real production Laravel ────────────
#
# Every one of them read as reassurance. None was visible from the code.

def test_a_commented_env_line_does_not_hide_debug_being_on():
    """A real .env carried:

        APP_DEBUG=false     # MUST be false in production

    Everything after the "=" was taken, comment included. Harmless for "false" — but
    reverse it and the value stops equalling "true", so debug reads OFF on a site that has
    it ON. A false negative on the most important finding on the screen.

    Exercised by running the generated helper against a real file, because the bug lives in
    the shell, not in Python.
    """
    import os
    import subprocess
    import tempfile

    cmd = lv.build_probe_command("/var/www/a/public")
    start = cmd.index("_envval() {")
    helper = cmd[start:cmd.index("\n", cmd.index("; }", start))]

    d = tempfile.mkdtemp()
    with open(os.path.join(d, ".env"), "w") as fh:
        fh.write('APP_ENV=production   # do not change\n'
                 'APP_DEBUG=true                   # turn off before launch\n'
                 'DB_PASSWORD=super-secret\n')
    r = subprocess.run(
        ["bash"], text=True, capture_output=True,
        input=f'APP_PATH={d}\n{helper}\necho "[$(_envval APP_ENV)][$(_envval APP_DEBUG)]"')
    assert r.stdout.strip() == "[production][true]", r.stdout + r.stderr


def test_a_commented_env_line_still_parses_when_it_is_quoted():
    import os
    import subprocess
    import tempfile

    cmd = lv.build_probe_command("/var/www/a")
    start = cmd.index("_envval() {")
    helper = cmd[start:cmd.index("\n", cmd.index("; }", start))]
    d = tempfile.mkdtemp()
    with open(os.path.join(d, ".env"), "w") as fh:
        fh.write('APP_ENV="local"\nAPP_DEBUG=false\n')
    r = subprocess.run(["bash"], text=True, capture_output=True,
                       input=f'APP_PATH={d}\n{helper}\necho "[$(_envval APP_ENV)]"')
    assert r.stdout.strip() == "[local]"


def test_the_cache_state_is_read_whether_it_is_a_boolean_or_a_word():
    """Laravel 11/12 report `"config": true`; older ones report `"config": "CACHED"`.

    Reading only the string form called a fully cached production application uncached —
    found on a real Laravel 12 app whose caches were all warm.
    """
    modern = _healthy(about=json.dumps({
        "environment": {"environment": "production", "debug_mode": False},
        "cache": {"config": True, "routes": True, "events": False}}))
    assert modern["cache_config"] is True
    assert modern["cache_routes"] is True
    assert modern["cache_events"] is False

    older = _healthy(about=json.dumps({
        "environment": {"environment": "production", "debug_mode": False},
        "cache": {"config": "CACHED", "routes": "NOT CACHED", "events": "NOT CACHED"}}))
    assert older["cache_config"] is True
    assert older["cache_routes"] is False


def test_the_queue_check_cannot_count_the_shell_that_is_running_it():
    """`pgrep -f` matches on the whole command line, and our own shell's arguments contain
    this pattern's text. It happens not to match today only because the parentheses are
    regex syntax — luck, and a self-matching grep is a mistake made here before."""
    cmd = lv.build_probe_command("/var/www/a")
    queue_line = next(l for l in cmd.splitlines() if "pgrep -f" in l)
    assert '"$$"' in queue_line and '"$PPID"' in queue_line, \
        "the probe must exclude its own process and its parent"
