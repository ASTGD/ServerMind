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
