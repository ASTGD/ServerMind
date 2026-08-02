"""The background processes that belong to one site.

Two properties of the unit file are load-bearing, and both were learned by running a real
systemd and watching it not do what the file said:

* the crash-loop limit only works in ``[Unit]`` — under ``[Service]`` systemd ignores it
  and the protection looks present while doing nothing;
* ``ExecStart`` has to ``exec``, or bash stays the main process and stopping the service
  orphans the program, which keeps holding its port.

They are asserted here because a reader will not notice either one going missing.
"""
import re
import shutil
import subprocess

import pytest

from app.services import playbook_service as ps
from app.services import site_daemon_service as d


def _unit(**over):
    args = dict(domain="shop.example.com", description="Queue worker",
                command="php artisan queue:work", working_dir="/var/www/shop",
                run_as="www-data", unit="serverally-site-shop-example-com--w.service")
    args.update(over)
    return d.build_unit(**args)


# ── The two things that must be true of the file ─────────────────────────────

def test_the_crash_limit_is_in_the_section_systemd_reads_it_from():
    unit = _unit()
    before_service = unit.split("[Service]")[0]
    assert "StartLimitBurst" in before_service
    assert "StartLimitIntervalSec" in before_service


def test_the_program_becomes_the_main_process():
    """Without exec, stopping the service leaves the program running and holding its port,
    and the next start fails with "address already in use".

    It lives in the script now rather than on the ExecStart line, which is where the
    command moved to — but it is the same requirement, and the same failure without it.
    """
    script = d.build_script("/var/www/shop", "php artisan queue:work")
    assert [ln for ln in script.splitlines() if ln.startswith("exec ")]


def test_a_daemon_never_runs_as_root_by_default():
    """The same rule as this site's scheduled jobs: a worker run as root leaves root-owned
    files inside the site, and it breaks days later."""
    assert "User=www-data" in _unit()
    with pytest.raises(d.DaemonError):
        _unit(run_as="")


def test_a_daemon_runs_in_the_site_it_belongs_to():
    assert "WorkingDirectory=/var/www/shop" in _unit()
    with pytest.raises(d.DaemonError):
        _unit(working_dir="")


def test_an_empty_command_is_refused():
    with pytest.raises(d.DaemonError):
        _unit(command="   ")


@pytest.mark.skipif(not shutil.which("systemd-analyze"),
                    reason="systemd-analyze only exists on Linux")
def test_systemd_itself_accepts_the_file(tmp_path):
    """The check that caught the [Service] mistake in the first place."""
    path = tmp_path / "serverally-site-test.service"
    path.write_text(_unit())
    r = subprocess.run(["systemd-analyze", "verify", str(path)],
                       capture_output=True, text=True)
    assert "Unknown key name" not in (r.stderr + r.stdout), r.stderr


def test_the_installer_and_this_agree_on_both_lessons():
    """The Web application installer writes the same shape in shell. If one of them ever
    loses a lesson the other kept, they have silently become two different products."""
    script = next(p for p in ps.OFFICIAL_PLAYBOOKS
                  if p["slug"] == "create-app")["script_bash"]
    unit = _unit()
    for marker in ("StartLimitBurst", "StartLimitIntervalSec", "Restart=always"):
        assert marker in script and marker in unit
    assert "exec " in script


# ── Whose unit it is ─────────────────────────────────────────────────────────

def test_two_sites_can_both_have_a_queue_worker():
    a = d.unit_name("shop.example.com", "queue-worker")
    b = d.unit_name("blog.example.com", "queue-worker")
    assert a != b, "one site's daemon would quietly replace the other's"


@pytest.mark.parametrize("unit,mine", [
    ("serverally-site-shop-example-com--queue-worker.service", True),
    ("serverally-site-blog-example-com--queue-worker.service", False),
    ("nginx.service", False),
    ("mariadb.service", False),
    ("serverally-site-shop-example-com--queue-worker.service.bak", False),
    # One hyphen is ambiguous: shop.example.com.au is a different site.
    ("serverally-site-shop-example-com-au--queue-worker.service", False),
    ("", False),
    ("../../nginx.service", False),
])
def test_only_this_site_s_own_units_can_be_touched(unit, mine):
    """The guard on every write. Without it the page is a systemd editor reached from a
    site, where a wrong name stops nginx — or the database every other site here uses."""
    assert d.owns(unit, "shop.example.com") is mine


def test_a_site_whose_name_is_a_prefix_of_another_is_not_claimed():
    """`shop.example.com` and `shop.example.com.au` are different sites."""
    unit = d.unit_name("shop.example.com.au", "worker")
    assert d.owns(unit, "shop.example.com") is False


# ── Names ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["queue-worker", "worker2", "a"])
def test_a_plain_name_is_accepted(name):
    assert d.valid_name(name) == name


@pytest.mark.parametrize("name", [
    "", "   ", "../etc/passwd", "worker;rm -rf /", "worker name", "Worker/../x",
    "-leading", "a" * 40,
])
def test_a_name_that_would_need_quoting_is_refused_rather_than_quoted(name):
    """It becomes part of a filename under /etc/systemd. A name that needs escaping to be
    safe there is a name we should not accept at all."""
    with pytest.raises(d.DaemonError):
        d.valid_name(name)


def test_the_command_reaches_the_shell_exactly_as_written(tmp_path):
    """RUN it, because the first version of this asserted the command TEXT appeared in the
    file — which it did, while the daemon ran something else.

    The command was inline on ExecStart wrapped in single quotes, so a command carrying a
    quote of its own closed that wrapping early: systemd handed bash three words instead of
    one and `--queue='high,default'` was silently dropped. Real systemd showed it; the test
    was happy.
    """
    import subprocess

    # A command that reports its own arguments, so what the shell received is visible.
    cmd = """printf '[%s]' one 'two three' "--queue='high,default'" """.strip()
    script = d.build_script(str(tmp_path), cmd).replace("exec ", "", 1)
    path = tmp_path / "run.sh"
    path.write_text(script)

    out = subprocess.run(["bash", str(path)], capture_output=True, text=True).stdout
    assert out == "[one][two three][--queue='high,default']", out


def test_the_script_runs_in_the_site_folder(tmp_path):
    import subprocess

    (tmp_path / "marker").write_text("here")
    script = d.build_script(str(tmp_path), "ls marker").replace("exec ", "", 1)
    path = tmp_path / "run.sh"
    path.write_text(script)
    r = subprocess.run(["bash", str(path)], capture_output=True, text=True, cwd="/")
    assert r.stdout.strip() == "marker", r.stderr


def test_a_folder_that_is_gone_stops_rather_than_running_somewhere_else(tmp_path):
    """Without the guard the command would run in whatever directory systemd started in —
    for a `rm -rf storage/*` style job, somewhere else entirely."""
    import subprocess

    script = d.build_script(str(tmp_path / "missing"), "echo RAN").replace("exec ", "", 1)
    path = tmp_path / "run.sh"
    path.write_text(script)
    r = subprocess.run(["bash", str(path)], capture_output=True, text=True)
    assert r.returncode == 1 and "RAN" not in r.stdout


def test_installing_writes_both_the_unit_and_its_command(tmp_path):
    install = d.build_install_command(
        "serverally-site-x--w.service", _unit(), d.build_script("/var/www/x", "sleep 1"))
    assert "SM_UNIT_EOF" in install and "SM_CMD_EOF" in install
    assert d.SCRIPT_DIR in install


def test_removing_takes_the_command_with_it():
    remove = d.build_remove_command("serverally-site-x--w.service")
    assert "/etc/systemd/system/" in remove and d.SCRIPT_DIR in remove


# ── Reading them back ────────────────────────────────────────────────────────

def test_the_list_reports_what_is_actually_in_the_file():
    line = (f"{d._LIST_SENTINEL}|serverally-site-shop-example-com--queue-worker.service"
            f"|active|enabled|Queue worker|php artisan queue:work")
    got = d.parse_list(line)[0]
    assert got["running"] is True and got["at_boot"] is True
    assert got["command"] == "php artisan queue:work"
    assert got["name"] == "queue-worker"


def test_a_stopped_daemon_is_not_reported_as_running():
    line = f"{d._LIST_SENTINEL}|serverally-site-x--w.service|failed|enabled|W|cmd"
    got = d.parse_list(line)[0]
    assert got["running"] is False and got["state"] == "failed"


def test_junk_does_not_become_a_daemon():
    assert d.parse_list("") == []
    assert d.parse_list("some unrelated output\n") == []
    assert d.parse_list(f"{d._LIST_SENTINEL}|only|two") == []


def test_only_this_site_s_units_are_even_looked_for():
    cmd = d.build_list_command("shop.example.com")
    assert "serverally-site-shop-example-com--" in cmd
    assert re.search(r"/etc/systemd/system/[^ ]*\*\.service", cmd)


# ── What the application needs ───────────────────────────────────────────────

def test_laravel_is_offered_its_queue_worker():
    s = d.suggested("laravel", "/var/www/shop")
    assert s and "queue:work" in s["command"]


def test_an_app_that_already_has_its_own_service_is_not_offered_a_second():
    """A Node, Python or Go site installed as a Web application already has a service; a
    second copy would give the site two processes fighting over one port."""
    for app_type in ["php", "wordpress", "static", "unknown"]:
        assert d.suggested(app_type, "/var/www/x") is None


def test_no_folder_means_no_suggestion():
    assert d.suggested("laravel", "") is None
