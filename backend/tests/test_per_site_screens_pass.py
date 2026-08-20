"""Three bugs found by walking every per-site screen on a real Laravel and WordPress site.

Each was invisible from the code and obvious the moment a real site was driven through it.

1. **The robots screen always read "not blocked".** Its check ran
   `shlex.quote(domain)[1:-1]` — but `shlex.quote` only ADDS quotes when the string needs
   them, so for an ordinary domain it returns it unchanged and the slice then ate the first
   and last characters: `t-lv.example.com` became `-lv.example.co`. nginx served the default
   site, no header came back, and the screen reported the site as indexable. The write then
   failed its own verification and returned an error over a change that had worked.

2. **A custom scheduled job was orphaned.** The add path wrote the command verbatim while
   the listing and the removal guard both claim a job by its command mentioning the site's
   folder or domain. `php artisan schedule:run` mentions neither, so it was created, ran
   from the wrong directory (silently failing every minute), and could never be seen or
   removed from the site page again.

3. **The WordPress XML-RPC switch could never work on a site we built.** Our own installer
   already wrote `location = /xmlrpc.php { deny all; }` outside the managed markers, so the
   screen read "not blocked" on a site that WAS blocked and then tried to add a second one —
   which nginx refuses outright as a duplicate location.
"""
from __future__ import annotations

import inspect
import re
import shlex

import pytest

from app.services import site_cron_service as sc
from app.services import wp_security_service as wp


def code(text: str) -> str:
    """Executable lines only.

    The comment explaining this very bug contains `[1:-1]`, so a check over the whole file
    fails on its own documentation. That trap has now caught this repo seven times, every
    one of them a search matching prose instead of code.
    """
    return "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("#"))


# ── 1. the domain that lost its first and last letters ───────────────────────

def test_shlex_quote_does_not_add_quotes_to_an_ordinary_domain():
    """The false assumption the bug rested on, stated as a test."""
    assert shlex.quote("t-lv.example.com") == "t-lv.example.com"
    assert shlex.quote("t-lv.example.com")[1:-1] == "-lv.example.co"


def test_the_robots_check_no_longer_strips_characters_off_the_domain():
    from app.routers import sites

    body = code(inspect.getsource(sites.read_robots))
    assert "[1:-1]" not in body, "the slice that ate the domain is back"
    assert "shlex.quote('Host: ' + site.domain)" in body


def test_no_route_anywhere_strips_quotes_it_did_not_add():
    """One occurrence existed and it produced a wrong answer for every site. The pattern
    reads as "quote it, then remove the quotes because it is already inside some" — which
    is only true for a value that needed quoting in the first place."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    bad = [str(f) for f in root.rglob("*.py")
           if re.search(r"shlex\.quote\([^)]*\)\[1:-1\]", code(f.read_text()))]
    assert bad == [], f"quote-then-unquote is back in: {bad}"


# ── 2. the scheduled job nothing could find ──────────────────────────────────

LARAVEL = ("laravel", "/var/www/shop.com/public", "shop.com")
WORDPRESS = ("wordpress", "/var/www/shop.com", "shop.com")


def test_a_bare_command_is_anchored_to_the_site():
    """Two things go wrong without this and only one of them is visible: the job runs in
    the wrong directory AND it belongs to nothing."""
    out = sc.anchor_to_site("php artisan schedule:run", *LARAVEL)
    assert out == "cd /var/www/shop.com && php artisan schedule:run"


def test_an_anchored_command_is_left_exactly_as_written():
    cmd = "cd /var/www/shop.com && php artisan schedule:run >> /dev/null 2>&1"
    assert sc.anchor_to_site(cmd, *LARAVEL) == cmd


def test_a_command_naming_the_domain_is_left_alone():
    """`jobs_for_site` claims it either way, so there is nothing to fix."""
    cmd = "curl -s https://shop.com/cron-ping"
    assert sc.anchor_to_site(cmd, *LARAVEL) == cmd


@pytest.mark.parametrize("spec", [LARAVEL, WORDPRESS])
def test_the_result_is_always_claimable_by_the_site(spec):
    """The property that matters: whatever the customer types, the listing and the removal
    guard must be able to find it afterwards."""
    from app.services import cron_service

    app_type, doc_root, domain = spec
    for typed in ("php artisan schedule:run", "php wp-cron.php", "/usr/bin/backup.sh",
                  "echo hello"):
        command = sc.anchor_to_site(typed, app_type, doc_root, domain)
        users = [{"user": "www-data", "fingerprint": "f",
                  "jobs": [{"command": command, "raw": f"* * * * * {command}"}]}]
        assert cron_service.jobs_for_site(users, domain, doc_root), typed


def test_nothing_is_anchored_when_we_do_not_know_the_folder():
    """Better to leave a command alone than to prefix `cd` with nothing after it."""
    assert sc.anchor_to_site("php -v", "laravel", "", "shop.com") == "php -v"


def test_the_add_path_uses_it():
    from app.routers import sites

    body = inspect.getsource(sites.add_site_cron)
    assert "anchor_to_site(" in body
    assert "command=command" in body, "the anchored command is not the one written"


# ── 3. the switch that could never win ───────────────────────────────────────

MARKED = f"server {{\n{wp.BEGIN}\n  location = /xmlrpc.php {{ deny all; }}\n{wp.END}\n}}"
INSTALLER_LINE = "server {\n  location = /xmlrpc.php { deny all; access_log off; }\n}"
APACHE = 'server\n<Files "xmlrpc.php">\n  Require all denied\n</Files>'
OPEN = "server {\n  location / { try_files $uri /index.php; }\n}"


@pytest.mark.parametrize("config,expected", [
    (MARKED, True), (INSTALLER_LINE, True), (APACHE, True), (OPEN, False), ("", False),
])
def test_a_blocked_site_reads_as_blocked_whoever_wrote_the_block(config, expected):
    """The question this screen asks is whether xmlrpc is reachable, not whether we were
    the one who closed it."""
    assert wp.xmlrpc_is_blocked(config) is expected


def test_a_site_merely_mentioning_xmlrpc_is_not_called_blocked():
    """A comment or a log path naming the file is not a deny."""
    assert wp.xmlrpc_is_blocked("server {\n  # xmlrpc.php is noisy\n}") is False
    assert wp.xmlrpc_is_blocked("access_log /var/log/xmlrpc.php.log;") is False


def test_the_installer_writes_the_block_the_switch_owns():
    """The collision itself: two blocks for the same location is a config nginx refuses to
    load, so the switch failed on every site our own installer had built."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    script = next(p for p in OFFICIAL_PLAYBOOKS
                  if p["slug"] == "wordpress-site")["script_bash"]
    assert wp.BEGIN in script and wp.END in script
    assert script.count("location = /xmlrpc.php") == 1, "two blocks for one location"


def test_the_state_is_read_through_the_shared_rule():
    body = inspect.getsource(wp)
    assert '"xmlrpc_blocked": xmlrpc_is_blocked(' in body
    assert '"xmlrpc_blocked": BEGIN in' not in body, "back to the marker-only check"
