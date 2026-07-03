"""Entitlements — the plan map (PRICING-FREE-VS-PRO.md v2: "open features, two meters").

The pricing model is deliberately simple: EVERY feature is available on EVERY plan —
missions, memory, skills, scheduler, backups, security, team, fleet. Plans differ only
in two numbers, each aligned with a real cost/value:

- ``actions_per_month`` — Ally requests (our AI bill; ~$0.03–0.05/action measured).
- ``max_servers``       — servers the user can add (our per-server infra: metrics
                          polling, scans, probes — and the market's value metric).

No feature flags, by design: gating features would cripple the free experience
(the full Ally magic IS the conversion moment), punish safety features (backups),
and add enforcement surface everywhere. The two meters are enforced at exactly two
choke points (AI calls via metering_service.gate; server creation via servers_gate)
and only block when ``ENFORCE_PLAN_LIMITS`` is on.

The billing webhook (Brick 3) is deliberately NOT built — ``users.plan`` is set
manually until a payment provider is chosen. Numbers below are launch placeholders;
tune from real ai_usage ledger data.
"""
from __future__ import annotations

from app.models.user import User

PLANS: dict[str, dict] = {
    "free": {
        "actions_per_month": 30,
        "max_servers": 2,
    },
    "pro": {
        "actions_per_month": 1000,
        # Deliberately NOT unlimited — leaves honest room for an Agency tier later
        # (never take features away; only ever add tiers above).
        "max_servers": 15,
    },
}


def limits_for(user: User) -> dict:
    """The limits map for a user's plan; unknown plans fall back to free."""
    return PLANS.get((user.plan or "free").lower(), PLANS["free"])
