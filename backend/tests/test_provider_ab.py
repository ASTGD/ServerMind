"""Dev Door — provider cost A/B (Claude vs OpenAI), re-pricing real ledger tokens.

Pure arithmetic (no DB, no API): given per-(feature,model) token counts, prove the two
cost models and the OpenAI caching economics. This is the number management uses to settle
"OpenAI is 1/3 the price", so the math must be locked.
"""
from __future__ import annotations

from app.services import dev_service, metering_service


# ── model → OpenAI tier mapping (by capability) ───────────────────────────────

def test_oa_tier_mapping():
    assert dev_service._oa_tier("claude-opus-4-8") == "top"
    assert dev_service._oa_tier("claude-fable-5") == "top"
    assert dev_service._oa_tier("claude-sonnet-5") == "mid"
    assert dev_service._oa_tier("claude-haiku-4-5-20251001") == "small"
    assert dev_service._oa_tier("claude-3-5-haiku") == "small"
    assert dev_service._oa_tier("something-unknown") == "mid"  # default tier


# ── corrected Anthropic list prices (the Opus $15/$75 bug is fixed) ───────────

def test_price_per_mtok_current():
    assert metering_service.price_per_mtok("claude-opus-4-8") == (5.0, 25.0)
    assert metering_service.price_per_mtok("claude-sonnet-5") == (3.0, 15.0)
    assert metering_service.price_per_mtok("claude-haiku-4-5-20251001") == (1.0, 5.0)
    assert metering_service.price_per_mtok("claude-3-5-haiku-x") == (0.8, 4.0)
    assert metering_service.price_per_mtok("mystery-model") == (0.0, 0.0)


# ── the two cost models (exact arithmetic) ────────────────────────────────────

def test_claude_cost_uses_reads_0_1_and_writes_2x():
    # sonnet: in $3/M, out $15/M. reads 0.1×, writes 2.0×.
    c = dev_service._claude_cost("claude-sonnet-5", 1000, 100, 2000, 500)
    assert round(c, 6) == round((1000 * 3 + 2000 * 3 * 0.1 + 500 * 3 * 2.0 + 100 * 15) / 1e6, 6)
    assert round(c, 4) == 0.0081


def test_openai_cost_treats_write_as_full_read_as_half():
    tier = {"in": 2.5, "out": 10.0}
    c = dev_service._openai_cost(tier, 1000, 100, 2000, 500)
    # (input + cache_write) at full, cache_read at 0.5×, output at out price. No write premium.
    assert round(c, 6) == round(((1000 + 500) * 2.5 + 2000 * 2.5 * 0.5 + 100 * 10) / 1e6, 6)
    assert round(c, 5) == 0.00725


# ── _price_ab aggregation, totals, delta, hit% ────────────────────────────────

def test_price_ab_aggregates_and_compares():
    rows = [
        {"feature": "chat", "model": "claude-sonnet-5", "input": 1000, "output": 100,
         "cache_read": 2000, "cache_write": 500, "calls": 3},
        {"feature": "chat", "model": "claude-sonnet-5", "input": 0, "output": 0,
         "cache_read": 0, "cache_write": 0, "calls": 1},
        {"feature": "mission", "model": "claude-opus-4-8", "input": 500, "output": 50,
         "cache_read": 1000, "cache_write": 0, "calls": 2},
    ]
    out = dev_service._price_ab(rows, dict(dev_service._OA_TIERS))

    feats = {f["feature"]: f for f in out["by_feature"]}
    assert feats["chat"]["calls"] == 4
    assert round(feats["chat"]["claude_usd"], 4) == 0.0081  # the two chat rows (second is 0)

    t = out["totals"]
    assert t["cache_read"] == 3000 and t["cache_write"] == 500 and t["in"] == 1500
    # cache hit% = reads / (in + reads + writes)
    assert round(t["cache_hit_pct"], 1) == round(3000 / 5000 * 100, 1)
    # delta_pct is (openai - claude) / claude * 100 — a real signed number
    assert t["delta_pct"] is not None
    expect = (t["openai_usd"] - t["claude_usd"]) / t["claude_usd"] * 100
    assert round(t["delta_pct"], 4) == round(expect, 4)
    # by_feature sorted by Claude cost desc
    assert out["by_feature"][0]["claude_usd"] >= out["by_feature"][-1]["claude_usd"]
    # opus mapped to the 'top' tier
    assert out["model_tiers"]["claude-opus-4-8"] == "top"


def test_price_ab_empty_is_safe():
    out = dev_service._price_ab([], dict(dev_service._OA_TIERS))
    assert out["by_feature"] == []
    assert out["totals"]["claude_usd"] == 0.0
    assert out["totals"]["delta_pct"] is None  # no divide-by-zero
    assert out["totals"]["cache_hit_pct"] == 0.0


def test_price_ab_respects_tier_price_override():
    rows = [{"feature": "chat", "model": "claude-sonnet-5", "input": 1000, "output": 0,
             "cache_read": 0, "cache_write": 0, "calls": 1}]
    cheap = {**dev_service._OA_TIERS, "mid": {"label": "x", "in": 1.0, "out": 1.0}}
    out = dev_service._price_ab(rows, cheap)
    # 1000 input × $1/M = $0.001 on OpenAI, vs $0.003 on Claude (sonnet $3/M)
    assert round(out["totals"]["openai_usd"], 6) == 0.001
    assert round(out["totals"]["claude_usd"], 6) == 0.003
