"""Model ladder — right-sized brain per task (docs/AI-MODEL-LADDER.md).

Pure: the tier→model resolution in llm_service and the mission-step escalation
heuristic in ai_service. No network, no DB.
"""
from __future__ import annotations

import pytest

from app.config import settings
from app.services import ai_service, llm_service


@pytest.fixture(autouse=True)
def _reset_ladder():
    """Each test controls the ladder flag / overrides; restore afterwards."""
    saved = (settings.ENABLE_MODEL_LADDER, settings.AI_MODEL_LOW, settings.AI_MODEL_HIGH,
             llm_service._runtime_config)
    settings.ENABLE_MODEL_LADDER = True
    settings.AI_MODEL_LOW = ""
    settings.AI_MODEL_HIGH = ""
    llm_service._runtime_config = None
    yield
    (settings.ENABLE_MODEL_LADDER, settings.AI_MODEL_LOW, settings.AI_MODEL_HIGH,
     llm_service._runtime_config) = saved


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
