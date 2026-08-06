"""Laravel queue workers.

Nine numbers, and each decides a failure mode. The one worth most of these tests is
`--timeout` against `retry_after`, because it is the only one whose failure is silent AND
damaging: a job handed to a second worker while the first is still running gets done twice,
and nothing anywhere reports an error.
"""
import pytest

from app.services import queue_worker_service as q


# ── The check that stops a job being processed twice ─────────────────────────

def test_a_worker_allowed_longer_than_retry_after_is_refused():
    """The queue puts a job back after `retry_after` seconds, assuming the worker died. A
    worker allowed to run longer gets its job handed to a second worker while it is STILL
    RUNNING — the customer is charged twice and nothing reports an error."""
    with pytest.raises(q.QueueError) as exc:
        q.check_timeout(120, 90)
    msg = str(exc.value)
    assert "done twice" in msg
    assert "charging a customer twice" in msg
    # and it says both numbers, so the fix is obvious
    assert "120 seconds" in msg and "90 seconds" in msg


def test_equal_is_also_refused():
    """Equal is not safe — the job is returned at the same moment the worker is still
    finishing it."""
    with pytest.raises(q.QueueError):
        q.check_timeout(90, 90)


def test_a_worker_comfortably_inside_the_window_is_allowed():
    q.check_timeout(60, 90)


def test_an_unknown_retry_after_skips_the_check_rather_than_inventing_one():
    """None is a real answer. Guessing a number and enforcing it would refuse a perfectly
    good worker on a site we simply could not read."""
    q.check_timeout(3600, None)


def test_retry_after_is_read_per_connection():
    conns = [
        {"name": "database", "retry_after": 90},
        {"name": "redis", "retry_after": 300},
        {"name": "sqs", "retry_after": None},
    ]
    assert q.retry_after_for(conns, "database") == 90
    assert q.retry_after_for(conns, "redis") == 300
    assert q.retry_after_for(conns, "sqs") is None
    assert q.retry_after_for(conns, "nonexistent") is None


def test_a_nonsense_retry_after_is_unknown_not_zero():
    """Zero would refuse every worker. Unknown skips the check, which is the honest
    behaviour when the application gave us something we cannot read."""
    assert q.retry_after_for([{"name": "x", "retry_after": "soon"}], "x") is None


# ── The command ──────────────────────────────────────────────────────────────

def test_every_number_reaches_the_command():
    cmd = q.build_command(php="/usr/bin/php8.3", connection="redis", queue="emails",
                          timeout=60, sleep=3, tries=3, backoff=10, memory=256)
    for flag in ("--timeout=60", "--sleep=3", "--tries=3", "--backoff=10", "--memory=256"):
        assert flag in cmd
    assert "queue:work redis" in cmd and "--queue=emails" in cmd


def test_the_environment_is_only_passed_when_given():
    assert "--env=" not in q.build_command(
        php="php", connection="database", queue="default", timeout=60, sleep=3,
        tries=3, backoff=0, memory=128)
    assert "--env=staging" in q.build_command(
        php="php", connection="database", queue="default", timeout=60, sleep=3,
        tries=3, backoff=0, memory=128, environment="staging")


@pytest.mark.parametrize("bad", [
    "emails; rm -rf /", "emails && curl evil", "../../etc", "", "a" * 60, "emails|x",
])
def test_a_queue_name_that_is_not_a_name_is_refused(bad):
    """It reaches a shell command and a systemd unit name."""
    with pytest.raises(q.QueueError):
        q.valid_name(bad, what="queue name")


@pytest.mark.parametrize("field,bad", [
    ("timeout", 1), ("timeout", 999_999), ("processes", 0), ("processes", 50),
    ("memory", 8), ("tries", -1), ("sleep", 9999),
])
def test_a_number_outside_what_can_sensibly_go_in_a_unit_is_refused(field, bad):
    with pytest.raises(q.QueueError):
        q.check_number(bad, field)


def test_a_number_that_is_not_a_number_is_refused():
    with pytest.raises(q.QueueError):
        q.check_number("many", "processes")


# ── Several processes means several units ────────────────────────────────────

def test_each_process_is_its_own_unit():
    """One dying must not take the others with it, which a single unit running N children
    cannot promise."""
    units = q.plan(domain="shop.example.com", queue="emails", processes=3,
                   php="php", connection="redis", timeout=60, sleep=3, tries=3,
                   backoff=0, memory=128)
    assert [u["name"] for u in units] == ["queue-emails-1", "queue-emails-2",
                                          "queue-emails-3"]
    assert len({u["command"] for u in units}) == 1, "all run the same command"


def test_the_units_are_written_by_the_daemon_machinery_not_a_second_copy():
    """That module carries the two lessons systemd punishes for — StartLimit* in [Unit],
    and `exec` so stopping does not orphan the worker. A second module writing units is a
    second one that has to remember them."""
    built = q.build_units(domain="shop.example.com", working_dir="/var/www/shop",
                          run_as="www-data", queue="emails", processes=2,
                          php="php", connection="redis", timeout=60, sleep=3,
                          tries=3, backoff=0, memory=128)
    assert len(built) == 2
    for unit, content, script in built:
        assert unit.endswith(".service")
        assert "[Unit]" in content and "StartLimitBurst" in content
        # in [Unit], where systemd actually reads it
        assert content.index("StartLimitBurst") < content.index("[Service]")
        assert "User=www-data" in content
        assert "exec " in script


def test_two_sites_can_both_have_a_queue_worker_of_the_same_name():
    a = q.build_units(domain="shop.example.com", working_dir="/a", run_as="www-data",
                      queue="emails", processes=1, php="php", connection="redis",
                      timeout=60, sleep=3, tries=3, backoff=0, memory=128)[0][0]
    b = q.build_units(domain="other.example.com", working_dir="/b", run_as="www-data",
                      queue="emails", processes=1, php="php", connection="redis",
                      timeout=60, sleep=3, tries=3, backoff=0, memory=128)[0][0]
    assert a != b


# ── Reading the application ──────────────────────────────────────────────────

SAMPLE = "\n".join([
    "___SM_QUEUE___|php|/usr/bin/php8.3",
    "___SM_QUEUE___|path|/var/www/shop",
    '___SM_QUEUE___|connections|{"database":{"driver":"database","queue":"default",'
    '"retry_after":90},"redis":{"driver":"redis","queue":"default","retry_after":300}}',
    "___SM_QUEUE___|default|redis",
])


def test_the_connections_come_from_the_booted_application():
    """`retry_after` is usually `env('QUEUE_RETRY_AFTER', 90)` in the file, so reading the
    file gives the default and is wrong exactly where it matters."""
    r = q.parse_probe(SAMPLE)
    assert r["ok"] is True
    assert r["default"] == "redis"
    names = {c["name"]: c for c in r["connections"]}
    assert names["database"]["retry_after"] == 90
    assert names["redis"]["retry_after"] == 300


def test_the_probe_reads_from_the_app_and_writes_nothing():
    cmd = q.build_probe_command("/var/www/shop/public")
    import re
    body = re.sub(r"\d?>\s*/dev/null", "", cmd)
    for verb in ("rm ", "mv ", "chmod", "chown", "config set", "queue:work",
                 "systemctl", "tee "):
        assert verb not in body


def test_output_the_application_mangled_degrades_to_not_knowing(monkeypatch):
    """A broken value must not take the page down — and "we do not know" then SKIPS the
    timeout guard rather than inventing a number to enforce."""
    r = q.parse_probe("___SM_QUEUE___|php|/usr/bin/php\n"
                      "___SM_QUEUE___|connections|Warning: something went wrong")
    assert r["ok"] is True
    assert r["connections"] == []
    assert q.retry_after_for(r["connections"], "database") is None


def test_a_site_that_is_not_laravel_says_so():
    r = q.parse_probe("___SM_QUEUE___|error|noapp")
    assert r["ok"] is False and "Laravel" in r["reason"]


# ── After a deploy ───────────────────────────────────────────────────────────

def test_workers_are_told_to_pick_up_new_code():
    """Without this a deploy changes the site and the queue carries on running the previous
    release for hours — the classic "I deployed and the emails still say the old thing"."""
    cmd = q.restart_after_deploy_command("/usr/bin/php", "/var/www/shop", "www-data")
    assert "queue:restart" in cmd
    assert "www-data" in cmd


def test_two_queues_on_one_site_do_not_collide():
    """The domain separation comes from the daemon machinery. What `worker_name` itself has
    to provide is that `emails` and `invoices` on the SAME site are different units —
    without it, creating the second silently replaces the first and the emails queue stops
    being processed with nothing to show for it."""
    common = dict(domain="shop.example.com", working_dir="/a", run_as="www-data",
                  processes=2, php="php", connection="redis", timeout=60, sleep=3,
                  tries=3, backoff=0, memory=128)
    emails = {u for u, _c, _s in q.build_units(queue="emails", **common)}
    invoices = {u for u, _c, _s in q.build_units(queue="invoices", **common)}
    assert len(emails) == 2 and len(invoices) == 2
    assert not (emails & invoices), "one queue's workers must never replace another's"
