"""The Application section — the long-running program behind a domain.

Ploi calls theirs "NodeJS" and shows five facts. The reason ours is worth more than a status
line is that **"the service is running" and "the site works" are different questions**, and
the three ways they come apart are each invisible from anywhere else. Those three rules are
pure, so they are tested directly.
"""
import re

import pytest

from app.services import webapp_service as w


HEALTHY = "\n".join([
    "___SM_WEBAPP___|unit|app-shop.example.com",
    "___SM_WEBAPP___|active|active",
    "___SM_WEBAPP___|enabled|enabled",
    "___SM_WEBAPP___|NRestarts|0",
    "___SM_WEBAPP___|MainPID|4242",
    "___SM_WEBAPP___|MemoryCurrent|104857600",
    "___SM_WEBAPP___|SubState|running",
    "___SM_WEBAPP___|cmd|npm run start",
    "___SM_WEBAPP___|user|www-data",
    "___SM_WEBAPP___|dir|/var/www/shop.example.com",
    "___SM_WEBAPP___|port|3000",
    "___SM_WEBAPP___|listening|yes",
    "___SM_WEBAPP___|proxy|proxy_pass http://127.0.0.1:3000",
])


def sample(**overrides) -> str:
    lines = []
    for line in HEALTHY.splitlines():
        key = line.split("|")[1]
        lines.append(f"___SM_WEBAPP___|{key}|{overrides[key]}"
                     if key in overrides else line)
    for key, value in overrides.items():
        if not any(l.split("|")[1] == key for l in lines):
            lines.append(f"___SM_WEBAPP___|{key}|{value}")
    return "\n".join(lines)


# ── The unit name, which becomes a systemctl argument ────────────────────────

def test_the_unit_name_matches_what_the_installer_actually_writes():
    """Two places know this name. If they ever disagree, the section reports "there is no
    program here" for every site that has one — which is exactly the bug this whole feature
    exists to fix, arriving from the other direction."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS, _script_for

    script = next(_script_for(p) for p in OFFICIAL_PLAYBOOKS if p["slug"] == "create-app")
    assert 'UNIT="app-$DOMAIN"' in script
    assert w.unit_for("shop.example.com") == "app-shop.example.com"


@pytest.mark.parametrize("bad", [
    "", "shop", "../etc", "shop.example.com; systemctl stop nginx",
    "shop example.com", "-shop.com", "shop.example.com\nreboot",
])
def test_a_domain_that_is_not_a_domain_never_becomes_a_unit_name(bad):
    with pytest.raises(w.WebAppError):
        w.unit_for(bad)


# ── Read-only ────────────────────────────────────────────────────────────────

def test_the_probe_changes_nothing():
    """Same guarantee the metrics, security and threat probes carry. `2>/dev/null` is a
    redirection, not a mutation — an earlier version of this check matched it and reported a
    read-only probe as dangerous."""
    cmd = w.build_probe_command("shop.example.com")
    body = re.sub(r"\d?>\s*/dev/null", "", cmd)
    for verb in ("rm ", "mv ", "chmod", "chown", "dd ", "mkfs", "tee ",
                 "systemctl start", "systemctl stop", "systemctl restart",
                 "systemctl enable", "systemctl disable", "kill "):
        assert verb not in body, f"the probe must not {verb.strip()!r}"


# ── What kind of program it is ───────────────────────────────────────────────

@pytest.mark.parametrize("command,expected", [
    ("npm run start", "Node.js"),
    ("node server.js", "Node.js"),
    ("/usr/bin/npx next start", "Node.js"),
    ("bun run index.ts", "Node.js"),
    ("gunicorn wsgi:app -b 127.0.0.1:8000", "Python"),
    ("python3 manage.py runserver", "Python"),
    ("uvicorn main:app", "Python"),
    ("bundle exec puma", "Ruby"),
    ("java -jar app.jar", "Java"),
    ("dotnet MyApp.dll", ".NET"),
    ("./my-go-binary", "Program"),
    ("", "Program"),
])
def test_the_runtime_is_read_off_the_command(command, expected):
    """Ours covers what our installer builds, which is any of these — so the screen names
    what it finds rather than claiming everything is Node."""
    assert w.runtime_of(command) == expected


# ── The three ways "running" and "working" come apart ────────────────────────

def test_a_healthy_program_reports_nothing_wrong():
    assert w.problems(True, "3000", "yes", "3000", 0, True) == []


def test_a_program_that_is_up_but_not_listening_is_caught():
    """systemd is perfectly happy. Every visitor gets a 502. Nothing else in the product
    would ever notice."""
    found = w.problems(True, "3000", "no", "3000", 0, True)
    assert any(p["level"] == "critical" and "nothing is listening" in p["text"]
               for p in found)


def test_a_proxy_pointing_at_the_wrong_port_is_caught():
    """Both halves are individually correct, so neither screen that shows one of them can
    tell. This is the only place the two are compared."""
    found = w.problems(True, "3000", "yes", "3001", 0, True)
    assert any("forwards to port 3001" in p["text"] and "told to use port 3000" in p["text"]
               for p in found)


def test_a_crash_loop_is_caught_even_though_it_reads_as_active():
    """`Restart=always` means a program that dies every two seconds is "active" most of the
    time. The restart COUNT is the only thing that gives it away without watching."""
    found = w.problems(True, "3000", "yes", "3000", 47, True)
    assert any("restarted 47 times" in p["text"] for p in found)


def test_a_stopped_program_is_the_first_thing_said():
    found = w.problems(False, "3000", None, "3000", 0, True)
    assert found[0]["level"] == "critical"
    assert "not running" in found[0]["text"]


def test_running_but_not_enabled_is_a_warning_not_a_failure():
    """It works today and will not survive a reboot. That is worth saying and is not an
    outage."""
    found = w.problems(True, "3000", "yes", "3000", 0, False)
    assert [p["level"] for p in found] == ["warning"]
    assert "after a reboot" in found[0]["text"]


# ── Reading the probe ────────────────────────────────────────────────────────

def test_a_site_with_no_managed_program_says_so_plainly():
    result = w.parse_probe("___SM_WEBAPP___|error|nounit")
    assert result["ok"] is False
    assert "no ServerAlly-managed program" in result["reason"]


def test_a_healthy_program_is_read_correctly():
    r = w.parse_probe(HEALTHY)
    assert r["ok"] is True
    assert r["runtime"] == "Node.js"
    assert r["active"] is True and r["enabled"] is True
    assert r["port"] == "3000" and r["proxy_port"] == "3000"
    assert r["listening"] is True
    assert r["memory_mb"] == 100.0
    assert r["user"] == "www-data"
    assert r["problems"] == []


def test_the_log_is_only_carried_when_something_is_wrong():
    """On a healthy service the journal is noise; on a dead one it is the only thing that
    matters."""
    assert w.parse_probe(HEALTHY)["log"] == ""
    broken = w.parse_probe(sample(active="failed", listening="no",
                                  log="Error: listen EADDRINUSE~    at Server.setup"))
    assert "EADDRINUSE" in broken["log"]
    assert "\n" in broken["log"], "the journal's line breaks must survive the transport"


def test_a_missing_restart_count_is_zero_not_a_crash():
    assert w.parse_probe(sample(NRestarts=""))["restarts"] == 0


# ── Actions, judged by what happened after ───────────────────────────────────

@pytest.mark.parametrize("bad", ["enable", "delete", "reload", "", "start; rm -rf /"])
def test_only_the_three_named_actions_are_possible(bad):
    with pytest.raises(w.WebAppError):
        w.build_action_command(bad, "shop.example.com")


def test_starting_is_judged_three_seconds_later_not_by_the_exit_code():
    """`systemctl start` returns as soon as it has forked, so a program that dies on startup
    exits 0. Trusting that would report a dead app as started — the exact failure this
    screen exists to catch."""
    cmd = w.build_action_command("start", "shop.example.com")
    assert "sleep 3" in cmd
    assert "is-active" in cmd


def test_a_program_that_did_not_stay_up_is_reported_with_its_own_words():
    ok, message = w.explain_action(
        "start", "state=inactive\nrestarts=3\nError: Cannot find module 'express'")
    assert ok is False
    assert "did not stay running" in message
    assert "Cannot find module" in message


def test_a_program_that_stayed_up_is_reported_as_running():
    ok, message = w.explain_action("start", "state=active\nrestarts=0")
    assert ok is True and "did not crash on start" in message


def test_stopping_is_only_a_success_when_it_actually_stopped():
    ok, _ = w.explain_action("stop", "state=inactive\nrestarts=0")
    assert ok is True
    ok, message = w.explain_action("stop", "state=active\nrestarts=0")
    assert ok is False and "still running" in message


# ── The registry ─────────────────────────────────────────────────────────────

def test_a_web_application_site_now_gets_a_section():
    """It did not before, and the cause was one word: the installer recorded the type as
    "unknown", and the registry deliberately shows nothing for a type it cannot identify."""
    from app.services import app_registry, site_service

    assert site_service.SITE_TYPES["app"]["app_type"] == "app"
    spec = app_registry.app_for("app")
    assert spec is not None and spec.label == "Application"


def test_a_type_we_genuinely_cannot_identify_still_shows_nothing():
    """The rule that made the bug is still the right rule — offering a section for a site we
    could not identify would be guessing at what is on it."""
    from app.services import app_registry

    assert app_registry.app_for("unknown") is None
    assert app_registry.app_for("static") is None


def test_a_crash_loop_in_progress_is_caught_even_when_the_count_still_says_zero():
    """Found against real systemd: a unit sitting in `auto-restart` reported NRestarts=0,
    so relying on the count alone would have called a crash loop "not running" and sent
    somebody looking for a stopped program instead of a broken one."""
    found = w.problems(False, "3000", "no", "3000", 0, True, sub_state="auto-restart")
    assert any("restarted right now" in p["text"] and p["level"] == "critical"
               for p in found)


def test_a_healthy_running_state_is_not_mistaken_for_a_loop():
    assert w.problems(True, "3000", "yes", "3000", 0, True, sub_state="running") == []


def test_systemd_saying_the_memory_is_not_set_is_not_a_crash():
    """`MemoryCurrent` comes back as the literal string "[not set]" for a unit that is not
    running — seen on real systemd, and `int()` on it would take the page down."""
    assert w.parse_probe(sample(MemoryCurrent="[not set]"))["memory_mb"] is None
