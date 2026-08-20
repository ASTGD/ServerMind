"""Two of the three writers of a threat scan silently dropped how much it could see.

Found by reading a scan the 5-minute sweep had just recorded on a real server:

    "verdict": "clean", "privilege": null, "skipped": []

`privilege` and `skipped` exist for one reason — so a scan that saw everything can be told
apart from one that could not look. A scan running as a non-root cloud account cannot read
site folders, and a `find` that is denied prints nothing, which every checker reads as
"pass". The verdict itself stayed honest (`_summarize` refuses to say clean while blind),
but the REASON was lost, so the page showed "unknown" with nothing to explain it.

Three places built the row by hand — the button, the sweep, and the MCP tool — and only the
button set those two fields. A guard each caller has to remember is a guard that gets
missed, so now there is nothing to remember: one function builds the row and a structural
test refuses any other module that builds one.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from app.services import privilege, threat_service


def result(**over) -> dict:
    base = {
        "verdict": "clean", "status": "completed", "error": None, "duration_ms": 220,
        "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "pass": 6, "info": 1},
        "findings": [{"severity": "pass", "title": "x"}],
        "privilege": privilege.ROOT, "skipped": [],
    }
    base.update(over)
    return base


# ── the fields that were being dropped ───────────────────────────────────────

def test_the_row_records_how_much_the_scan_could_see():
    row = threat_service.scan_row(result(), server_id="s", user_id="u")
    assert row.privilege == privilege.ROOT
    assert json.loads(row.skipped) == []


def test_a_blind_scan_records_what_it_could_not_check():
    """The case the columns exist for. Without this the customer sees "unknown" and is
    given no reason for it."""
    row = threat_service.scan_row(
        result(verdict="unknown", privilege=privilege.NONE,
               skipped=["webshells", "uploads_php"]),
        server_id="s", user_id="u")
    assert row.privilege == privilege.NONE
    assert json.loads(row.skipped) == ["webshells", "uploads_php"]
    assert row.verdict == "unknown"


def test_the_counts_and_findings_still_come_across():
    row = threat_service.scan_row(result(), server_id="s", user_id="u")
    assert row.pass_count == 6 and row.info_count == 1
    assert json.loads(row.findings)[0]["title"] == "x"


def test_a_result_missing_the_fields_does_not_crash():
    """An older code path, or a partial result, must degrade rather than raise — recording
    something is better than recording nothing."""
    row = threat_service.scan_row(
        {"verdict": "clean", "status": "completed"}, server_id="s", user_id="u")
    assert row.privilege is None
    assert json.loads(row.skipped) == []
    assert json.loads(row.findings) == []


# ── nothing else may build one ───────────────────────────────────────────────

def test_only_one_place_builds_a_scan_row():
    """The bug was three hand-built constructions and two of them forgetting. Parsed
    rather than grepped, so a mention in a comment or an import does not count.
    """
    root = pathlib.Path(__file__).resolve().parents[1] / "app"
    allowed = {"services/threat_service.py"}
    offenders = []
    for f in root.rglob("*.py"):
        rel = str(f.relative_to(root))
        if rel in allowed or rel.startswith("models/"):
            continue
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("ThreatScan"):
                offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], (
        "these build a threat-scan row themselves instead of using "
        f"`threat_service.scan_row`, which is how two of them dropped `privilege` and "
        f"`skipped`: {offenders}")


@pytest.mark.parametrize("module", [
    "app.workers.threat_worker", "app.routers.security", "app.mcp.server",
])
def test_every_writer_goes_through_it(module):
    import importlib
    import inspect

    src = inspect.getsource(importlib.import_module(module))
    assert "scan_row(" in src, f"{module} no longer records scans through the shared row"


# ── and the verdict itself is still honest ───────────────────────────────────

def test_a_scan_that_could_not_look_never_reads_as_clean():
    """The rule the columns explain. Bad news may be reported while blind; good news may
    not — finding malware with half the disk unreadable is still finding malware, but
    finding NOTHING while blind is not a result."""
    assert not privilege.may_report_clean(privilege.NONE, skipped=["webshells"])
    assert privilege.may_report_clean(privilege.ROOT, skipped=[])


# ── the same class of bug, one screen along ──────────────────────────────────
#
# The site scan reported `privilege: none` on a server we connect to as ROOT. The probe was
# right — it printed `…|privilege|root||no` — but that value was smuggled through
# `parse_discovery`, which filters every line whose names are not real domains, and `root`
# is not one. The line was dropped before anything could read it.
#
# The consequence was not the label. A scan that cannot read everything is deliberately not
# allowed to conclude a site is gone, so with the level stuck at `none` discovery became
# **add-only**: a site genuinely removed from a server was never marked missing and its
# uptime monitor was never paused.

def test_the_site_scan_reads_the_privilege_the_probe_reported():
    from app.services import site_service

    raw = ("___SM_SITE___|privilege|root||no\n"
           "___SM_SITE___|nginx|shop.com|/var/www/shop|no")
    assert site_service.parse_privilege(raw) == privilege.ROOT


@pytest.mark.parametrize("value,expected", [
    ("root", privilege.ROOT), ("sudo", privilege.SUDO), ("none", privilege.NONE),
    ("banana", privilege.NONE), ("", privilege.NONE),
])
def test_only_a_level_we_recognise_is_believed(value, expected):
    from app.services import site_service

    assert site_service.parse_privilege(
        f"___SM_SITE___|privilege|{value}||no") == expected


def test_no_privilege_line_means_we_could_not_tell():
    """Fails closed: an unreadable answer must never become "we saw everything"."""
    from app.services import site_service

    assert site_service.parse_privilege(
        "___SM_SITE___|nginx|shop.com|/var/www/shop|no") == privilege.NONE


def test_the_privilege_line_is_never_counted_as_a_website():
    from app.services import site_service

    raw = ("___SM_SITE___|privilege|root||no\n"
           "___SM_SITE___|nginx|shop.com|/var/www/shop|no")
    sites, _truncated = site_service.parse_discovery(raw)
    assert [s.domain for s in sites] == ["shop.com"]


def test_a_root_scan_is_allowed_to_conclude_a_site_is_gone():
    """The property the whole bug turned on. `complete` is what lets `sync` mark a site
    missing; stuck at `none` it never could, so discovery only ever added."""
    assert privilege.can_read_everything(privilege.ROOT) is True
    assert privilege.can_read_everything(privilege.SUDO) is True
    assert privilege.can_read_everything(privilege.NONE) is False


def test_discover_actually_uses_it(monkeypatch):
    """The wiring, not just the parser.

    Written after mutation testing: replacing `discover`'s call with the OLD broken code —
    routing the value back through the site parser — left every test above green, because
    they all exercised `parse_privilege` in isolation. A test that does not run the caller
    proves nothing about the caller.

    Also covers the defensive filter: whatever the probe emits, the privilege line must
    never appear in the site inventory.
    """
    import asyncio
    from types import SimpleNamespace

    from app.services import site_service

    raw = ("___SM_SITE___|privilege|root||no\n"
           "___SM_SITE___|nginx|shop.com|/var/www/shop|no\n")

    async def fake_execute(server, command):
        return raw, "", 0

    monkeypatch.setattr(site_service.connection_manager, "execute", fake_execute)
    server = SimpleNamespace(id="s", name="box", connection_type="ssh")

    found, truncated, error, level = asyncio.run(site_service.discover(server))
    assert error == ""
    assert level == privilege.ROOT, "discover did not read the level the probe reported"
    assert [s.domain for s in found] == ["shop.com"], "the privilege line reached the inventory"


def test_discover_reports_a_limited_account_honestly(monkeypatch):
    """The case the flag exists for — and the one that must still work."""
    import asyncio
    from types import SimpleNamespace

    from app.services import site_service

    async def fake_execute(server, command):
        return "___SM_SITE___|privilege|none||no\n", "", 0

    monkeypatch.setattr(site_service.connection_manager, "execute", fake_execute)
    _f, _t, _e, level = asyncio.run(
        site_service.discover(SimpleNamespace(id="s", name="box", connection_type="ssh")))
    assert level == privilege.NONE
