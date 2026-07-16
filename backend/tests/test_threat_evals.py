"""Threat-scan evals — verdict logic, finding severity, and the read-only guarantee.

Deterministic (no SSH, no API). Guards the tuning done live: a clean signal must
not escalate the verdict, a real IOC must, and the scan must NEVER contain a
mutating command (it only observes).
"""
from __future__ import annotations

import inspect

import pytest

from app.models.server import Server
from app.services import threat_service as t


# ── Finding severity mapping ──────────────────────────────────────────────────

@pytest.mark.parametrize("evaluator,section_id,bad_input,bad_sev", [
    (t._c_webshell, "webshell", "/var/www/x.php\n/var/www/y.php", "critical"),
    (t._c_uploads, "uploads_php", "/home/s/public_html/wp-content/uploads/shell.php", "critical"),
    (t._c_proc, "proc", "/proc/999/exe -> /tmp/miner", "critical"),
    (t._c_persistence, "persistence", "/etc/cron.d/backdoor", "high"),
    (t._c_accounts, "accounts", "uid0:hacker", "critical"),
    (t._c_suid, "suid", "/tmp/rootme", "high"),
])
def test_ioc_present_flags_expected_severity(evaluator, section_id, bad_input, bad_sev):
    f = evaluator(bad_input)
    assert f["severity"] == bad_sev, f"{section_id}: expected {bad_sev}, got {f['severity']}"
    assert f["evidence"], f"{section_id}: a real finding should carry evidence"


@pytest.mark.parametrize("evaluator", [
    t._c_webshell, t._c_uploads, t._c_proc, t._c_persistence, t._c_accounts, t._c_suid,
])
def test_clean_input_passes(evaluator):
    assert evaluator("")["severity"] == "pass"


def test_wpcore_missing_files_is_not_flagged():
    """The live lesson: 'File doesn't exist' (version drift) must NOT be a threat —
    only ADDED/MODIFIED core files (surfaced as TAMPER by the probe) are, and only
    at LOW severity so a fresh install never reads as compromised."""
    assert t._c_wpcore("OK:/home/a\nOK:/home/b")["severity"] == "pass"
    assert t._c_wpcore("NO_WPCLI")["severity"] == "info"
    tampered = t._c_wpcore("TAMPER:/home/a: should not exist: wp-includes/x.php")
    assert tampered["severity"] == "low"  # worth a look, but never an alarm on its own


# ── Verdict computation ───────────────────────────────────────────────────────

@pytest.mark.parametrize("severities,expected", [
    (["pass", "pass", "low", "info"], "clean"),   # low/info never escalate
    (["pass", "medium"], "suspicious"),
    (["low", "high"], "at_risk"),
    (["high", "critical"], "compromised"),         # worst wins
    ([], "clean"),
])
def test_verdict_reflects_worst_finding(severities, expected):
    findings = [{"severity": s} for s in severities]
    verdict, _counts = t._summarize(findings)
    assert verdict == expected


# ── Read-only guarantee (security-critical) ───────────────────────────────────

# The scan must only OBSERVE. A mutating verb slipping into a probe would let a
# "scan" change or delete data — exactly what this feature must never do.
# Command verbs that change state. (A `>` redirect isn't listed: the only redirects
# in the probes are `2>/dev/null`, which is read-only; `tee`/`rm`/… cover real writes.)
_MUTATORS = (" rm ", " rm -", " dd ", "mkfs", " mv ", " chmod ", " chown ", " tee ",
             " kill ", "systemctl start", "systemctl stop", " apt ", " apt-get ",
             " curl ", " wget ")


def test_every_probe_command_is_read_only():
    for section in t.LINUX_SECTIONS:
        cmd = " " + section.command + " "
        for m in _MUTATORS:
            assert m not in cmd, f"section '{section.id}' contains a mutating token {m!r}: {section.command}"


@pytest.mark.parametrize("ct,shell", [("hosting", "bash"), ("winrm", "powershell")])
async def test_scan_refuses_non_ssh(ct, shell):
    s = Server(name="x", host="h", port=22, username="root", auth_type="password",
               connection_type=ct, panel_type=None, encrypted_cred="x",
               os_type="ubuntu", shell=shell)
    r = await t.run_scan(s)
    assert r["status"] == "failed" and r["verdict"] == "unknown"


def test_recommendations_never_auto_run():
    """Fix hints are display-only text; sanity-check they're strings, not executed."""
    f = t._c_webshell("/var/www/evil.php")
    assert isinstance(f["recommendation"], str) and f["recommendation"]


# ── Scan scope: the whole account home, not just */public_html (task #2) ──────

def test_scan_covers_whole_account_home_not_just_public_html():
    """Regression guard for the live scope gap (panel2.firevps.net): CyberPanel puts each
    child domain at /home/<account>/<domain>/ (e.g. /home/desktopit.net/news.rmp.gov.bd),
    so globbing only `/home/*/public_html` silently MISSED whole infected sites. The scan
    must walk the account homes wholesale."""
    assert "/home" in t._SCAN_ROOTS
    # The old, too-narrow glob must not come back in any probe.
    for section in t.LINUX_SECTIONS:
        assert "/home/*/public_html" not in section.command, \
            f"section '{section.id}' still scopes to */public_html: {section.command}"


def test_scan_prunes_dependency_trees_but_not_cache():
    """Dependency trees are pruned (speed + the BUG-002 vendor false positive), but
    cache/storage are NOT — real webshells hide in bootstrap/cache and
    storage/framework/views, and the signatures are tight enough not to FP there."""
    assert "vendor" in t._PRUNE_DIRS and "node_modules" in t._PRUNE_DIRS
    assert "cache" not in t._PRUNE_DIRS and "storage" not in t._PRUNE_DIRS
    webshell = next(s for s in t.LINUX_SECTIONS if s.id == "webshell")
    assert "--exclude-dir=vendor" in webshell.command
    assert "--exclude-dir=node_modules" in webshell.command


def test_wpcore_cap_is_never_silent():
    """The per-site wp-cli check is capped, so coverage is bounded — that MUST be stated,
    never silently under-reported as a clean bill of health."""
    capped_clean = t._c_wpcore(f"CAPPED:{t._WP_SITES_MAX}\nOK:/home/a/site1.com")
    assert capped_clean["severity"] == "pass"
    assert "not verified" in capped_clean["detail"]
    assert str(t._WP_SITES_MAX) in capped_clean["detail"]
    # Uncapped runs say nothing extra.
    assert "not verified" not in t._c_wpcore("OK:/home/a/site1.com")["detail"]


def test_timeout_helper_fails_open_not_into_a_false_clean():
    """Every silent probe is bounded by `timeout` so the widened walk can't exceed
    ssh_service's 60s channel-read timeout. But if a box lacked coreutils' timeout, a
    bare `timeout ...` would emit NOTHING — and an empty webshell section reads as
    'clean'. The _t helper must run the probe unbounded instead (fail OPEN)."""
    script = t._build_script(t.LINUX_SECTIONS)
    assert "_t()" in script
    # Falls back to running the command (shift drops the seconds), never to silence.
    assert 'else shift; "$@"' in script
    # No probe may call bare `timeout` directly — it must go through _t.
    for section in t.LINUX_SECTIONS:
        assert "timeout " not in section.command, \
            f"section '{section.id}' calls timeout directly instead of _t: {section.command}"
