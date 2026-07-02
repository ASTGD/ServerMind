"""Entitlements — the single plan → limits map (docs/AI-METERING.md §3.3, PRICING §10).

One static declaration of what each plan allows. Both the API (the wall) and the UI
(greying-out, usage bar) read THIS map — gating is enforced server-side, never only
hidden client-side. Numbers are the PRICING §9 placeholders; tune them from real
ai_usage ledger data before launch.

The billing webhook (Brick 3) is deliberately NOT built — ``users.plan`` is set
manually until a payment provider is chosen.
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
        "max_servers": None,  # unlimited
    },
}


def limits_for(user: User) -> dict:
    """The limits map for a user's plan; unknown plans fall back to free."""
    return PLANS.get((user.plan or "free").lower(), PLANS["free"])
