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


def test_security_incident_scan_excludes_framework_noise():
    """Regression guard for the live-found scan weakness (2026-07-12, panel2.firevps.net):
    a malware scan's recently-modified-files `find` returned so many Laravel
    storage/framework/views cache .php files that it truncated the real webshell-grep
    results out of Ally's summary. The fix is in the skill — exclude framework/cache/vendor
    noise, and run the signature scan as its OWN command — so lock those rules in."""
    body = _skill_body("security-incident")
    # Exclude the constantly-regenerated noise so it can't bury real webshells.
    assert "exclude" in body
    assert "storage/framework" in body
    # Run the signature grep as its own command so hits aren't drowned in a file listing.
    assert "own command" in body
    # The lesson itself, so a future edit can't quietly drop it.
    assert "bury" in body or "buries" in body
    assert "truncate" in body


def test_security_incident_does_not_flag_vendor_libraries():
    """Regression guard for BUG-002 (2026-07-15, panel2.firevps.net): the first-response
    signature grep matched a bare `base64_decode` token in `vendor/intervention/image`
    (a legit image decoder) + a `.php` that held only SVG markup, and those false hits led
    to 128 legitimate library files being quarantined — taking a live gov site offline.
    Lock the fix into the detection skill: exclude dependency trees from the signature
    scan, and teach that one token is not proof."""
    body = _skill_body("security-incident")
    # The signature grep must skip third-party dependency trees.
    assert "exclude dependency trees" in body
    assert "node_modules" in body
    # One token is not malware; a real shell needs a strong signal.
    assert "a single token" in body
    assert "flowing straight into execution" in body
    # Don't condemn a file because a neighbour matched.
    assert "sibling in the same folder matched" in body
    # Verify against the package manifest instead of hand-removing library files.
    assert "composer.lock" in body


def test_incident_response_protects_vendor_libraries():
    """Regression guard for BUG-002 (2026-07-15): the cleanup mission had no rule stopping
    Ally from quarantining vendored library files on a weak signal. It quarantined the
    whole `intervention/image` package + `symfony/error-handler` assets (128 files, 0
    malicious) and took a live government Laravel site offline for ~a day. Lock the
    safeguards into the mission runbook so a future edit can't drop them:
      - never quarantine a vendor/node_modules file on a signature match
      - verify against the package manifest / restore via composer install, don't hand-remove
      - one file at a time; never move a whole directory because a sibling matched
      - a .php holding only SVG/HTML is not a shell
    """
    body = _skill_body("security-incident-response")
    # Dependency-tree files are library code — not quarantined on a weak signal.
    assert "never quarantine a" in body and "vendor" in body
    # Verify against the manifest / restore cleanly rather than hand-removing.
    assert "composer.lock" in body
    assert "package manifest" in body
    # One artifact at a time; never sweep a whole directory.
    assert "quarantine one file at a time" in body
    assert "never move a whole directory" in body
    # A .php with no PHP logic (SVG/HTML template) is not malware.
    assert "no php logic" in body
    # The lesson itself, so the pitfall can't be silently removed.
    assert "false positives over" in body


def test_incident_skills_record_cleanup_to_memory():
    """Regression guard for BUG-001 (2026-07-15): a cleanup must leave a durable memory
    note (what was quarantined, from which site, the destination path) so a later
    conversation recognises it as Ally's own work. Both the chat first-response skill and
    the cleanup mission must instruct it."""
    chat = _skill_body("security-incident")
    mission = _skill_body("security-incident-response")
    assert "record what you cleaned to memory" in chat
    assert "record this cleanup to memory" in mission
    # Both must capture the quarantine PATH in the note, not just "cleaned".
    assert "quarantine path" in mission or "quarantine-<ts>" in mission
    assert "destination path" in chat


def test_incident_response_confirms_real_page_content():
    """Regression guard for the live gap (Area C / task #1): the cleanup's "site still
    loads" check trusted the HTTP status code, but a 200 can be a blank body or a PHP/
    Laravel error page (the restored index.php that still 500-crashed). The runbook must
    read the page CONTENT after cleaning, not just the status code."""
    body = _skill_body("security-incident-response")
    # The per-site check must look at content, not just the code.
    assert "check the content, not just the status code" in body
    # Working = a good code AND the real site rendered (not blank/error/placeholder).
    assert "a body that is the real site" in body
    # The finish check reinforces it too.
    assert "content check" in body
    """Preparation for the panel2.firevps.net production cleanup (2026-07-12): the two hard
    requirements are (a) the whole box + every site malware-free and (b) NO site broken,
    across WordPress AND Laravel sites. The runbook was WordPress-leaning and never forced a
    per-site backup or a 'does it still load?' check. Lock the new safeguards into the skill
    so a future edit can't silently drop them:
      - the promise: keep every live site working
      - back up each site BEFORE touching its files (per-site instant undo)
      - after cleaning, CONFIRM the site still loads (curl HTTP code) and never leave it broken
      - Laravel-aware cleanup (no core checksums; restore via composer, not hand-edits)
    """
    body = _skill_body("security-incident-response")
    # (a) The explicit promise + per-site backup-first discipline.
    assert "keep every live site working" in body
    assert "back up the site first" in body
    assert "haven't backed up" in body
    # (b) Per-site "still loads" verification + never-leave-broken, with the real check.
    assert "confirm the site still loads" in body
    assert "http_code" in body  # the curl code check is actually present, not just described
    assert "leave a site broken" in body
    assert "confirm every site you touched still loads" in body  # reinforced in the finish check
    # Laravel coverage — the framework the old runbook ignored.
    assert "laravel" in body
    assert "no core checksums" in body  # so it doesn't try WP-style checksums on Laravel
    assert "composer install" in body   # restore framework files the right way


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
    assert ir is not None and ir.budget == 40
    assert skill_service.resolve_mission_budget(ir) == 40


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


def test_chat_prompt_records_its_own_cleanup_actions():
    """Regression guard for BUG-001 (2026-07-15, panel2.firevps.net): Ally cleaned a site
    (quarantined vendor webshells → quarantine_20260714) in chat one day, then the next day
    forgot it was its OWN work — it treated the quarantine folder as an unknown and nearly
    proposed restoring a 10-month-old backup on a live gov site. The chat REMEMBER guidance
    only covered passive facts; it never told Ally to record the lasting CHANGES it makes.
    Pin the fix into the prompt so a future edit can't drop it."""
    p = _chat_prompt_lower()
    # Record a lasting change (esp. a cleanup) with the destination path.
    assert "always record a lasting change" in p
    assert "the exact destination path" in p
    # So a later session recognises its own prior work, not a fresh mystery.
    assert "not an unknown to re-investigate" in p
    # And never rolls a cleaned site back to a stale full backup.
    assert "stale full-backup restore" in p


def test_memories_block_reasons_from_own_prior_work():
    """The injected WHAT-ALLY-REMEMBERS block must tell Ally to reason FROM a note about a
    change it made (a quarantine folder is its own work, not a mystery) — the recall half of
    the BUG-001 fix."""
    m = " ".join(ai_service._MEMORIES_BLOCK.lower().split())
    assert "a note about a change you made" in m
    assert "reason from it" in m
    # Never propose a stale restore for a site a note says was already cleaned.
    assert "a site a note says you already cleaned" in m


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
