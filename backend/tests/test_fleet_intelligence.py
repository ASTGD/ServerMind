"""Proactive fleet intelligence — scoring + findings + actions.

Pure (no DB, no API): drives ``_analyze_server`` with mock signals and asserts the
health score, the ranked findings it produces, and each finding's one-click action.
"""
from __future__ import annotations

from types import SimpleNamespace as N

import pytest

from app.services import fleet_service as f


def _srv(**kw):
    return N(id=kw.get("id", "s1"), name=kw.get("name", "TS"),
             connection_type=kw.get("connection_type", "ssh"), status=kw.get("status", "online"))


def _metric(cpu=20, ram=30, disk=40, disk_used=40, disk_total=100):
    return N(cpu_percent=cpu, ram_percent=ram, disk_percent=disk,
             disk_used_gb=disk_used, disk_total_gb=disk_total)


def _ids(h):
    return {x.id for x in h.findings}


# ── grade thresholds ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,grade", [(100, "A"), (90, "A"), (89, "B"), (75, "B"),
                                         (74, "C"), (60, "C"), (59, "D"), (40, "D"), (39, "F"), (0, "F")])
def test_grade_bands(score, grade):
    assert f._grade(score) == grade


# ── individual findings ───────────────────────────────────────────────────────

_A_GRADE = N(grade="A", score=95, critical_count=0, high_count=0)  # so "never scanned" doesn't fire


def test_healthy_server_has_no_findings():
    h = f._analyze_server(_srv(), _metric(), _A_GRADE, N(verdict="clean", critical_count=0, high_count=0),
                          [], has_installed=False)
    assert h.findings == [] and h.score == 100 and h.grade == "A" and h.headline == "All good"


def test_disk_almost_full_is_a_high_finding_with_chat_action():
    h = f._analyze_server(_srv(), _metric(disk=94, disk_used=94, disk_total=100), _A_GRADE, None, [], False)
    df = next(x for x in h.findings if x.id == "disk-critical")
    assert df.severity == "high" and df.action["kind"] == "chat" and "clean" in df.action["seed"].lower()
    assert h.score == 75  # 100 - 25


def test_compromised_is_critical_and_tanks_the_score():
    h = f._analyze_server(_srv(), _metric(), None, N(verdict="compromised", critical_count=3, high_count=1),
                          [], False)
    tf = next(x for x in h.findings if x.id == "threat-compromised")
    assert tf.severity == "critical" and tf.action["kind"] == "page" and "/security" in tf.action["path"]
    assert h.grade == "F"  # a critical finding caps the grade at F


def test_offline_flags_and_skips_stale_resource_checks():
    # A server that's offline with a stale "disk 99%" metric → offline finding, but NOT
    # a disk finding (the number is meaningless while it's down).
    h = f._analyze_server(_srv(status="offline"), _metric(disk=99), None, None, [], False)
    assert "offline" in _ids(h) and "disk-critical" not in _ids(h)


def test_security_grade_maps_to_severity():
    for grade, fid, sev in [("F", "security-f", "high"), ("D", "security-d", "medium"), ("C", "security-c", "low")]:
        h = f._analyze_server(_srv(), _metric(), N(grade=grade, score=50, critical_count=0, high_count=0),
                              None, [], False)
        got = next(x for x in h.findings if x.id == fid)
        assert got.severity == sev and got.action["kind"] == "page"
    # A/B → no security finding.
    hb = f._analyze_server(_srv(), _metric(), N(grade="A", score=95, critical_count=0, high_count=0), None, [], False)
    assert not any(x.id.startswith("security-") for x in hb.findings)


def test_backups_only_nag_when_theres_something_to_protect():
    # No installed software → no backup nag even with no backups.
    none_installed = f._analyze_server(_srv(), _metric(), None, None, [], has_installed=False)
    assert "backups-none" not in _ids(none_installed)
    # Installed + no backups → nag.
    installed = f._analyze_server(_srv(), _metric(), None, None, [], has_installed=True)
    assert "backups-none" in _ids(installed)
    # A failed backup run → a different finding.
    failed = f._analyze_server(_srv(), _metric(), None, None,
                               [N(is_active=True, last_status="failed")], has_installed=True)
    assert "backups-failed" in _ids(failed)


def test_hosting_server_skips_ssh_only_findings():
    # Hosting (panel) servers can't run security scans / backups the same way.
    h = f._analyze_server(_srv(connection_type="hosting"), None,
                          N(grade="F", score=10, critical_count=0, high_count=0), None, [], has_installed=True)
    assert not any(x.id.startswith("security-") or x.id.startswith("backups-") for x in h.findings)
    assert h.status == "hosting"


# ── findings are ranked worst-first ───────────────────────────────────────────

def test_findings_sorted_by_severity_then_penalty():
    h = f._analyze_server(_srv(), _metric(disk=85, ram=93), N(grade="D", score=45, critical_count=0, high_count=0),
                          N(verdict="compromised", critical_count=1, high_count=0), [], has_installed=True)
    sevs = [x.severity for x in h.findings]
    ranks = [f._SEV_RANK[s] for s in sevs]
    assert ranks == sorted(ranks, reverse=True)  # non-increasing severity
    assert h.findings[0].id == "threat-compromised"  # the critical one leads


# ── summary + to_dict ─────────────────────────────────────────────────────────

def test_to_dict_needs_attention_and_summary():
    bad = f._analyze_server(_srv(id="a", name="A"), _metric(disk=95), None, None, [], False)   # high → attention
    ok = f._analyze_server(_srv(id="b", name="B"), _metric(), None, None, [], False)            # clean
    assert f.to_dict(bad)["needs_attention"] is True
    assert f.to_dict(ok)["needs_attention"] is False
    s = f.summarize([bad, ok])
    assert s["total"] == 2 and s["needs_attention"] == 1
