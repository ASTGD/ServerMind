"""Model ladder — right-sized brain per task (docs/AI-MODEL-LADDER.md).

Pure: the tier→model resolution in llm_service and the mission-step escalation
heuristic in ai_service. No network, no DB.
"""
from __future__ import annotations

from types import SimpleNamespace as N

import pytest

from app.config import settings
from app.services import ai_service, llm_service


def _srv(**kw):
    return N(name=kw.get("name", "s1"), os_type=kw.get("os_type", "ubuntu"),
             os_version="22.04", connection_type="ssh", shell="bash", arch="amd64",
             panel_type=None)


@pytest.fixture(autouse=True)
def _reset_ladder():
    """Each test controls the ladder flag / overrides; restore afterwards."""
    saved = (settings.ENABLE_MODEL_LADDER, settings.AI_MODEL_LOW, settings.AI_MODEL_HIGH,
             settings.ANTHROPIC_MODEL, llm_service._runtime_config)
    settings.ENABLE_MODEL_LADDER = True
    settings.AI_MODEL_LOW = ""
    settings.AI_MODEL_HIGH = ""
    # Pin the default model so these ladder-LOGIC tests don't depend on the operator's
    # runtime .env choice (e.g. ANTHROPIC_MODEL=claude-opus-4-8 for a high-stakes run,
    # which would collapse the default==high tier and is a supported, legitimate setting).
    settings.ANTHROPIC_MODEL = "claude-sonnet-5"
    llm_service._runtime_config = None
    yield
    (settings.ENABLE_MODEL_LADDER, settings.AI_MODEL_LOW, settings.AI_MODEL_HIGH,
     settings.ANTHROPIC_MODEL, llm_service._runtime_config) = saved


# ── tier → model (anthropic default provider) ─────────────────────────────────

def test_default_tier_is_the_resolved_model():
    assert llm_service.model_for_tier("default") == "claude-sonnet-5"


def test_low_and_high_swap_to_the_ladder_models():
    assert llm_service.model_for_tier("low") == "claude-haiku-4-5-20251001"
    assert llm_service.model_for_tier("high") == "claude-opus-4-8"


def test_env_overrides_win():
    settings.AI_MODEL_HIGH = "claude-fable-5"
    settings.AI_MODEL_LOW = "claude-haiku-4-5-20251001"
    assert llm_service.model_for_tier("high") == "claude-fable-5"


def test_flag_off_pins_everything_to_default():
    settings.ENABLE_MODEL_LADDER = False
    assert llm_service.model_for_tier("low") == "claude-sonnet-5"
    assert llm_service.model_for_tier("high") == "claude-sonnet-5"


def test_tier_is_ignored_for_non_anthropic_providers():
    # A bring-your-own-key user on another provider keeps their one configured model.
    llm_service._runtime_config = {
        "provider": "openai", "api_key": "sk-x", "model": "gpt-4o", "base_url": ""
    }
    assert llm_service._tier_model("openai", "high") is None
    assert llm_service.model_for_tier("high") == "gpt-4o"
    assert llm_service.model_for_tier("low") == "gpt-4o"


def test_unknown_tier_falls_back_to_default_model():
    assert llm_service._tier_model("anthropic", "medium") is None
    assert llm_service.model_for_tier("medium") == "claude-sonnet-5"


# ── mission-step escalation heuristic ─────────────────────────────────────────

def test_escalates_after_a_verifier_bounce():
    assert ai_service.mission_step_tier([], verify_attempts=1) == "high"


def test_clean_run_stays_default():
    assert ai_service.mission_step_tier([{"cmd": "ls", "exit_code": 0}], 0) == "default"


def test_two_consecutive_failures_escalate():
    steps = [{"cmd": "a", "exit_code": 1}, {"cmd": "b", "exit_code": 1}]
    assert ai_service.mission_step_tier(steps, 0) == "high"


def test_a_single_failure_does_not_escalate():
    steps = [{"cmd": "a", "exit_code": 0}, {"cmd": "b", "exit_code": 1}]
    assert ai_service.mission_step_tier(steps, 0) == "default"


def test_synthetic_steps_are_ignored_when_judging_failures():
    # (resumed) / (verification) markers aren't real command failures.
    steps = [{"cmd": "(verification)", "exit_code": 1}, {"cmd": "(resumed)", "exit_code": 1}]
    assert ai_service.mission_step_tier(steps, 0) == "default"


# ── proactive self-escalation (Ally asks for a stronger model up front) ───────

def test_has_stronger_tier_true_on_anthropic_with_ladder_on():
    assert llm_service.has_stronger_tier() is True


def test_has_stronger_tier_false_when_flag_off():
    settings.ENABLE_MODEL_LADDER = False
    assert llm_service.has_stronger_tier() is False


async def test_plan_commands_reruns_on_high_when_ally_flags_it(monkeypatch):
    """need_stronger:true on the default plan → ONE re-plan on the high tier, and that
    stronger plan (marked escalated) is what's returned."""
    seen: list[str] = []

    async def fake_complete(system, user, *, max_tokens=2048, system_volatile="", tier="default", model=None):
        seen.append(tier)
        if tier == "high":
            return '{"plan_summary": "careful plan", "commands": []}'
        return '{"plan_summary": "quick draft", "commands": [], "need_stronger": true}'

    monkeypatch.setattr(llm_service, "complete", fake_complete)
    plan = await ai_service.plan_commands("do something risky and irreversible", _srv())
    assert seen == ["default", "high"]              # exactly one escalation hop
    assert plan["plan_summary"] == "careful plan"   # the stronger re-plan won
    assert plan.get("escalated") is True


async def test_plan_commands_does_not_escalate_without_a_stronger_tier(monkeypatch):
    """Even if Ally flags need_stronger, no second call when there's no stronger tier
    (ladder off / BYO provider) — we never pay for an identical re-plan."""
    settings.ENABLE_MODEL_LADDER = False
    seen: list[str] = []

    async def fake_complete(system, user, *, max_tokens=2048, system_volatile="", tier="default", model=None):
        seen.append(tier)
        return '{"plan_summary": "draft", "commands": [], "need_stronger": true}'

    monkeypatch.setattr(llm_service, "complete", fake_complete)
    plan = await ai_service.plan_commands("x", _srv())
    assert seen == ["default"]              # no hop
    assert plan.get("escalated") is None


async def test_plan_commands_stays_default_when_not_flagged(monkeypatch):
    seen: list[str] = []

    async def fake_complete(system, user, *, max_tokens=2048, system_volatile="", tier="default", model=None):
        seen.append(tier)
        return '{"plan_summary": "easy", "commands": []}'

    monkeypatch.setattr(llm_service, "complete", fake_complete)
    plan = await ai_service.plan_commands("show me disk usage", _srv())
    assert seen == ["default"]
    assert plan.get("escalated") is None


# ── manual model picker (Ally chat "Auto / Manual" control) ───────────────────

def test_manual_model_maps_friendly_names_to_ids():
    assert llm_service.manual_model("fast") == "claude-haiku-4-5-20251001"
    assert llm_service.manual_model("smart") == "claude-sonnet-5"
    assert llm_service.manual_model("expert") == "claude-opus-4-8"
    assert llm_service.manual_model("genius") == "claude-fable-5"
    assert llm_service.manual_model(None) is None      # Auto
    assert llm_service.manual_model("") is None
    assert llm_service.manual_model("bogus") is None    # unknown → Auto (never crashes)


async def test_plan_commands_pins_manual_model_and_skips_escalation(monkeypatch):
    """A pinned manual model goes straight to complete() AND disables the need_stronger
    escalation hop — the user chose the model, so we don't override it with a re-plan."""
    seen: list[str | None] = []

    async def fake_complete(system, user, *, max_tokens=2048, system_volatile="", tier="default", model=None):
        seen.append(model)
        # Flag need_stronger to prove the pin suppresses the escalation, not the absence of the flag.
        return '{"plan_summary": "draft", "commands": [], "need_stronger": true}'

    monkeypatch.setattr(llm_service, "complete", fake_complete)
    plan = await ai_service.plan_commands("do something risky", _srv(), model="claude-opus-4-8")
    assert seen == ["claude-opus-4-8"]     # the pinned model, exactly once — no high-tier hop
    assert plan.get("escalated") is None
