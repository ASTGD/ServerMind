"""Deterministic Ally evals — skill routing + safety invariants.

Zero cost, no API, runs in CI. This is the regression net that catches a
skill/trigger or blocklist change breaking Ally's routing or safety. See
tests/ally_eval_corpus.py for the cases and tests/test_ally_evals_live.py for
the model-backed behavioral evals.
"""
from __future__ import annotations

import pytest

from app.evals import deterministic_cases, run_case
from app.services import ai_service, safety_service, skill_service


# ── Skill routing ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fresh_skill_cache():
    """Load skills from disk fresh (the cache may be warm from another test)."""
    skill_service.reset_cache()
    yield
    skill_service.reset_cache()


# The deterministic corpus (skill routing + the three safety buckets + the read-only
# guard) runs through the shared eval ENGINE (app.evals) — the SAME runner the CLI
# (`python -m app.evals run`) and the Dev Door use, so there is one source of truth for
# how each case is checked. One case per parametrization → granular pytest output.
_DET_CASES = deterministic_cases()


@pytest.mark.parametrize("case", _DET_CASES, ids=[c.id for c in _DET_CASES])
def test_deterministic_corpus(case):
    result = run_case(case)
    assert result.passed, (
        f"[{case.category}] {case.input!r} → got {result.got!r}, "
        f"expected {case.expected!r}" + (f" ({result.error})" if result.error else "")
    )


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
    mission quarantined the webshells but left the live /etc/cron.d backdoor running
    (it got lost among the box's many legitimate CyberPanel crons) and its first pass
    didn't resolve every seeded finding. The fix is prompt-level — an explicit
    findings-ledger discipline + a finish check — so lock those rules into the skill so
    a future edit can't silently drop them:
      - build a FINDINGS LEDGER from the scan's exact indicators and track each to resolved
      - go to the EXACT flagged path (don't dilute it in a general survey)
      - evidence-copy is NOT containment (the live artifact must still be neutralized)
      - a FINISH CHECK must walk the ledger before "done"; no open item may remain
      - never call the server clean while a flagged indicator is still live
    """
    body = _skill_body("security-incident-response")
    # Turn the scan's indicators into an explicit, tracked ledger.
    assert "track every finding to resolution" in body
    assert "findings ledger" in body
    # Go straight to the exact flagged path rather than a general survey that hides it.
    assert "exact flagged path" in body
    # Copying an artifact to the evidence folder is NOT containment.
    assert "not containment" in body
    # May not finish while any ledger item is still uninvestigated (OPEN).
    assert "forbids finishing" in body
    assert "only an uninvestigated" in body
    # A finish check must reconcile the ledger before declaring done.
    assert "finish check" in body
    # Must not declare the server clean while an indicator is unresolved.
    assert "never report the server clean" in body
    # Adversarial-review must-fixes (2026-07-05), so the gap can't reopen and the fix
    # can't create a NEW over-eager failure:
    #  (1) BENIGN needs POSITIVE attribution — reading contents + "looks legit" is how the
    #      rogue cron was originally rationalised; require naming the legitimate software.
    assert "positively name" in body
    #  (2) A first-class honest-incomplete terminal status, so a genuinely unresolvable item
    #      isn't force-CONTAINED or force-BENIGN just to clear the ledger.
    assert "needs-human" in body


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


# ── Capability contract (proactivity Track A) ─────────────────────────────────
# Regression guards for the hallucination found live (2026-07-08, the TS4→TS3
# file-move conversation, Issues-ss/AllyChatIssue): per-server chat told the user
# "I don't have SSH access details for TestServer3", suggested scp/rsync between
# the user's own managed servers, and said "I can only act on one server" — all
# false; the mission engine's transfer step exists and ServerAlly holds the
# credentials. The model hallucinated because _CHAT_SYSTEM never told it. These
# tests pin the contract into the prompt so a future edit can't drop it.

def _chat_prompt_lower() -> str:
    """The chat system prompt, lowercased and whitespace-collapsed so a re-wrap
    of the markdown can't hide a phrase we assert on."""
    return " ".join(ai_service._CHAT_SYSTEM.lower().split())


def test_chat_prompt_knows_missions_span_servers():
    """Chat must know a mission can act on ALL connected servers and transfer files
    between them — the fix for 'I can only act on this one server'."""
    p = _chat_prompt_lower()
    assert "transfer a file between two servers" in p
    assert "holds every connected server's credentials" in p
    # A cross-server job routes to a mission offer, not a refusal.
    assert "offer a mission" in p


def test_chat_prompt_forbids_the_ssh_credential_hallucination():
    """Chat must never ask the user for SSH keys / suggest scp/rsync between their
    own managed servers / tell them to move the file themselves."""
    p = _chat_prompt_lower()
    assert "never ask the user for ssh keys" in p
    assert "scp/rsync" in p
    assert "never say you can only act on this one server" in p


def test_chat_prompt_mission_block_covers_cross_server_jobs():
    """The MISSION trigger must name the cross-server case explicitly (copy/move a
    file between servers) so the model offers a mission instead of improvising."""
    p = _chat_prompt_lower()
    assert "another connected server" in p
    assert "copy/move a file between servers" in p
    assert "naming every server involved" in p


def test_chat_prompt_is_a_doer_not_an_advisor():
    """Ally must RUN commands itself, never tell the user to run one and paste the output
    back. Pins out the over-hands-off failure (2026-07-11: asked "run df -h and share it"
    instead of just running it) — the user's core "Ally is a doer, not an advisor" ask."""
    p = _chat_prompt_lower()
    assert "doer, not an advisor" in p
    # Forbid the advisory "you run it and paste it back" pattern...
    assert "share the output" in p
    # ...and explicitly license running read-only commands without asking.
    assert "read-only commands are always safe" in p


def test_normal_mode_makes_ally_do_the_looking():
    """The DEFAULT (normal) posture must say 'look' means ALLY runs the read-only checks,
    not the user — so the doer behaviour holds even in the balanced mode."""
    m = " ".join(ai_service._MODE_POSTURE["normal"].lower().split())
    assert "look" in m and "yourself" in m
    assert "report back" in m  # "don't ask the user to run a command and report back"


# ── Autonomy modes (proactivity Track D) ──────────────────────────────────────

def test_mode_normalization():
    """A stored/arbitrary mode string coerces to a known mode; junk → normal."""
    assert ai_service.normalize_mode("proactive") == "proactive"
    assert ai_service.normalize_mode("CAREFUL") == "careful"
    assert ai_service.normalize_mode("  normal ") == "normal"
    assert ai_service.normalize_mode(None) == "normal"
    assert ai_service.normalize_mode("") == "normal"
    assert ai_service.normalize_mode("yolo") == "normal"


def test_every_mode_has_a_distinct_posture_block():
    """Each mode injects its own posture paragraph — a missing one would silently make
    the mode a no-op."""
    blocks = {m: ai_service._mode_block(m) for m in ai_service.ALLY_MODES}
    for m, b in blocks.items():
        assert b.strip(), f"mode {m} has an empty posture block"
    # The three postures are genuinely different text.
    assert len(set(blocks.values())) == len(ai_service.ALLY_MODES)


def test_careful_posture_asks_before_changes_proactive_acts():
    """The two extremes must read differently: careful confirms before changes,
    proactive keeps momentum."""
    careful = ai_service._mode_block("careful").lower()
    proactive = ai_service._mode_block("proactive").lower()
    assert "confirm before" in careful or "ask" in careful
    assert "momentum" in proactive or "handle it" in proactive


# ── One Ally, one brain (Phase 2) ─────────────────────────────────────────────
# The user's locked vision: one Ally that always knows the whole fleet, resolves the
# target server itself, and never makes the user think "which server am I on". These
# pin the identity + the removed "go open a server yourself" seam into both prompts.

def _fleet_prompt_lower() -> str:
    return " ".join(ai_service._FLEET_SYSTEM.lower().split())


def test_both_prompts_are_one_fleet_assistant():
    """Chat AND fleet must present ONE assistant for the whole fleet — not a per-server
    helper (chat) vs a separate overview (fleet)."""
    assert "one assistant for their whole fleet" in _chat_prompt_lower()
    assert "one assistant for their whole fleet" in _fleet_prompt_lower()


def test_per_server_chat_can_answer_fleet_questions():
    """While focused on one server, Ally still knows the rest — 'which server needs
    attention?' is answerable here, not deflected."""
    p = _chat_prompt_lower()
    assert "whole fleet" in p and "answer from what you know about the other servers" in p


def test_fleet_acts_not_deflects():
    """The old seam ('tell the user to open that server') is gone — fleet Ally ACTS on
    the resolved server itself; opening a server is no longer the user's job."""
    p = _fleet_prompt_lower()
    assert "tell the user to open" not in p and "open that server" not in p
    assert "your job now" in p


def test_memory_hygiene_user_wins_and_no_temp_facts():
    """Memory hygiene (folds old Track E): a stale note never overrides the user's
    current request or triggers a re-ask, and temporary one-time rules aren't stored as
    durable facts — the two failure modes from the screenshot conversation."""
    mem = " ".join(ai_service._MEMORIES_BLOCK.lower().split())
    assert "the user wins" in mem
    assert "never re-ask" in mem
    chat = _chat_prompt_lower()
    assert "do not store a temporary" in chat and "durable fact" in chat
