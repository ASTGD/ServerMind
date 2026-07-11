"""Dev Door Phase 4 — the LLM judge (deterministic, mocked) + the Activity ledger view.

Live judge calibration (real model calls) lives in test_ally_judge_evals_live.py (opt-in).
"""
from __future__ import annotations

from app.services import ai_service, dev_service, llm_service


# ── judge() — parses the verdict, injection-safe, degrades on bad JSON ─────────

async def test_judge_returns_pass(monkeypatch):
    async def fake(*a, **k):
        return '{"pass": true, "reason": "it ran df -h itself"}'

    monkeypatch.setattr(llm_service, "complete", fake)
    r = await ai_service.judge("I'll run df -h now.", "Did the assistant run a command itself?")
    assert r["pass"] is True and "df" in r["reason"]


async def test_judge_returns_fail(monkeypatch):
    async def fake(*a, **k):
        return '{"pass": false, "reason": "it told the user to run it"}'

    monkeypatch.setattr(llm_service, "complete", fake)
    r = await ai_service.judge("Please run df -h and paste it back.", "Did the assistant run it itself?")
    assert r["pass"] is False


async def test_judge_bad_json_is_a_fail(monkeypatch):
    async def fake(*a, **k):
        return "the model rambled, no json"

    monkeypatch.setattr(llm_service, "complete", fake)
    r = await ai_service.judge("x", "y")
    assert r["pass"] is False


def test_judge_prompt_frames_output_as_data():
    """Injection defence: the judged output must be framed as data, never instructions."""
    p = ai_service._JUDGE_SYSTEM.lower()
    assert "data" in p and "never instructions" in p


# ── activity() — shape holds on an empty ledger ───────────────────────────────

class _ActResult:
    def all(self):
        return []

    def one(self):
        return (0, 0, 0)


class _ActSession:
    async def execute(self, _stmt):
        return _ActResult()


async def test_activity_empty_shape():
    out = await dev_service.activity(_ActSession())
    assert out["summary"] == {"cost_usd": 0.0, "actions": 0, "calls": 0}
    assert out["by_feature"] == []
    assert out["daily"] == []
    assert out["recent"] == []
    assert isinstance(out["period_start"], str)
