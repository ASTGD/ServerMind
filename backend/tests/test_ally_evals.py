"""Deterministic Ally evals — skill routing + safety invariants.

Zero cost, no API, runs in CI. This is the regression net that catches a
skill/trigger or blocklist change breaking Ally's routing or safety. See
tests/ally_eval_corpus.py for the cases and tests/test_ally_evals_live.py for
the model-backed behavioral evals.
"""
from __future__ import annotations

import pytest

from app.services import safety_service, skill_service
from tests import ally_eval_corpus as corpus


# ── Skill routing ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fresh_skill_cache():
    """Load skills from disk fresh (the cache may be warm from another test)."""
    skill_service.reset_cache()
    yield
    skill_service.reset_cache()


@pytest.mark.parametrize("message,os_type,expected", corpus.SKILL_ROUTING,
                         ids=[c[0][:40] for c in corpus.SKILL_ROUTING])
def test_skill_routing(message, os_type, expected):
    match = skill_service.match(message, os_type)
    got = match.slug if match else None
    assert got == expected, f"{message!r} routed to {got!r}, expected {expected!r}"


def test_every_skill_is_loadable_and_wellformed():
    """Every shipped skill parses with the fields the engine needs — a malformed
    skill silently disappears from routing, so guard the whole library."""
    skills = skill_service.load_skills()
    assert skills, "no skills loaded"
    slugs = [s.slug for s in skills]
    assert len(slugs) == len(set(slugs)), f"duplicate skill slugs: {slugs}"
    for s in skills:
        assert s.triggers, f"{s.slug} has no triggers"
        assert s.body.strip(), f"{s.slug} has no body"
        assert s.os_family in ("linux", "windows", "any"), f"{s.slug} bad os: {s.os_family}"
        assert s.mode in ("knowledge", "mission"), f"{s.slug} bad mode: {s.mode}"


def test_mission_skills_offer_not_inject():
    """A mission-mode skill must NOT inject into normal chat (it only OFFERS a
    mission); a knowledge skill must inject. Regression guard for skill_block."""
    for s in skill_service.load_skills():
        block = skill_service.skill_block(s)
        if s.mode == "mission":
            assert block == "", f"mission skill {s.slug} leaked into chat planning"
        else:
            assert s.title in block, f"knowledge skill {s.slug} did not inject"


def _skill_body(slug: str) -> str:
    """The lowercased body of a shipped skill, whitespace-collapsed so a line-wrap
    in the markdown can't hide a phrase we assert on."""
    match = next((s for s in skill_service.load_skills() if s.slug == slug), None)
    assert match is not None, f"skill {slug!r} is not loaded"
    return " ".join(match.body.lower().split())


def test_incident_response_requires_live_containment():
    """Regression guard for the gap found live (2026-07-05): the incident-response
    mission quarantined the webshell but left the live /etc/cron.d backdoor running,
    then wrongly reported 'no rogue cron entries'. The fix is prompt-level, so lock
    the exact rules into the skill so a future edit can't silently drop them:
      - evidence-copy is NOT containment (the live artifact must still be neutralized)
      - every flagged finding must be resolved
      - never call the server clean while a flagged indicator is still live
    """
    body = _skill_body("security-incident-response")
    # Copying an artifact to the evidence folder must be called out as NOT containment.
    assert "not the same as containing" in body
    # The LIVE persistence must be neutralized, not just copied.
    assert "still be neutralized" in body
    # Must not declare the server clean while an indicator is still live.
    assert "never report the server clean while a flagged indicator is still live" in body
    # Every flagged finding must be addressed (no silent skips).
    assert "address every flagged finding" in body


def test_incident_response_is_reversible_and_evidence_first():
    """The runbook's safety spine: preserve evidence before changing anything, and
    contain by MOVING to quarantine (reversible) rather than deleting."""
    body = _skill_body("security-incident-response")
    assert "quarantine" in body
    assert "never `rm`" in body or "never rm" in body  # reversible over destructive
    # Injection defence: attacker-controlled server text is data, never instructions.
    assert "injection" in body


def test_incident_response_recognizes_own_session():
    """Regression guard for the false positive found live (2026-07-05): the mission
    flagged ServerAlly's OWN SSH session + failed brute-force noise as an 'active
    intrusion'. The skill must teach self-recognition so it doesn't alarm on itself."""
    body = _skill_body("security-incident-response")
    # Establish its own management connection before judging any session.
    assert "$ssh_connection" in body or "ssh_connection" in body
    assert "your own management" in body
    # Its own session/IP is not an intruder.
    assert "not an intruder" in body
    # Failed brute-force attempts are noise, not a compromise — only a SUCCESSFUL,
    # unattributable login counts.
    assert "failed brute-force" in body or "failed password" in body


# ── Safety invariants ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("cmd,osf", corpus.SAFETY_MUST_BLOCK,
                         ids=[c[0][:40] for c in corpus.SAFETY_MUST_BLOCK])
def test_safety_must_block(cmd, osf):
    assert safety_service.validate_command(cmd, osf).status == "blocked", \
        f"DANGEROUS command not blocked: {cmd!r}"


@pytest.mark.parametrize("cmd,osf", corpus.SAFETY_MUST_CONFIRM,
                         ids=[c[0][:40] for c in corpus.SAFETY_MUST_CONFIRM])
def test_safety_must_confirm(cmd, osf):
    assert safety_service.validate_command(cmd, osf).status == "confirm", \
        f"risky command did not require confirmation: {cmd!r}"


@pytest.mark.parametrize("cmd,osf", corpus.SAFETY_MUST_ALLOW,
                         ids=[c[0][:40] for c in corpus.SAFETY_MUST_ALLOW])
def test_safety_must_allow(cmd, osf):
    # A false block/confirm here silently breaks a real feature (e.g. H1 hosting).
    assert safety_service.validate_command(cmd, osf).status == "ok", \
        f"legitimate command wrongly flagged: {cmd!r}"


def test_plan_blocked_wins_over_confirm_and_ok():
    """validate_plan: one blocked command blocks the whole plan, even mixed with
    ok/confirm ones (a plan is only as safe as its worst command)."""
    plan = [
        {"cmd": "apt-get install -y nginx"},   # ok
        {"cmd": "systemctl stop nginx"},        # confirm
        {"cmd": "rm -rf /"},                    # blocked
    ]
    assert safety_service.validate_plan(plan, "linux").status == "blocked"


def test_plan_confirm_when_any_command_confirms():
    plan = [{"cmd": "df -h"}, {"cmd": "apt-get purge nginx"}]
    assert safety_service.validate_plan(plan, "linux").status == "confirm"


# ── Read-only guard (mission verification) ────────────────────────────────────

@pytest.mark.parametrize("cmd", corpus.READONLY_ALLOW, ids=[c[:40] for c in corpus.READONLY_ALLOW])
def test_verification_allows_read_only(cmd):
    # A real verification check wrongly rejected → the mission can't confirm success
    # (annoying but safe). Guard against over-rejection breaking verification.
    assert safety_service.is_read_only_command(cmd), f"read-only check wrongly rejected: {cmd!r}"


@pytest.mark.parametrize("cmd", corpus.READONLY_DENY, ids=[c[:40] for c in corpus.READONLY_DENY])
def test_verification_denies_mutations(cmd):
    # SECURITY-CRITICAL: a mutating command wrongly accepted would let a "verification"
    # step change/delete data. This must never happen.
    assert not safety_service.is_read_only_command(cmd), f"MUTATING command passed read-only guard: {cmd!r}"


def test_verification_rejects_blank():
    assert not safety_service.is_read_only_command("")
    assert not safety_service.is_read_only_command("   ")


# ── Per-skill mission budget ──────────────────────────────────────────────────

def test_mission_budget_parse_and_clamp():
    """A skill's declared budget is clamped to the safe range; junk → None (default)."""
    assert skill_service._parse_budget("30") == 30
    assert skill_service._parse_budget("5") == skill_service.MISSION_BUDGET_MIN     # clamped up
    assert skill_service._parse_budget("999") == skill_service.MISSION_BUDGET_MAX   # clamped down
    assert skill_service._parse_budget("") is None
    assert skill_service._parse_budget(None) is None
    assert skill_service._parse_budget("abc") is None


def test_mission_budget_resolution():
    """Ad-hoc missions get the default; a skill that declares a budget gets its own."""
    assert skill_service.resolve_mission_budget(None) == skill_service.MISSION_BUDGET_DEFAULT
    ir = skill_service.get("security-incident-response")
    assert ir is not None and ir.budget == 30
    assert skill_service.resolve_mission_budget(ir) == 30


def test_mission_skills_declare_sane_budgets():
    """No shipped skill can declare a budget outside the safe clamp range — the bound
    is never removed, just raised within limits."""
    for s in skill_service.load_skills():
        if s.budget is not None:
            assert skill_service.MISSION_BUDGET_MIN <= s.budget <= skill_service.MISSION_BUDGET_MAX, \
                f"{s.slug} budget {s.budget} out of range"
            assert s.mode == "mission", f"{s.slug} declares a budget but isn't a mission skill"
