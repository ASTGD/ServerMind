"""AI metering — the ledger + monthly action counter (docs/AI-METERING.md, Brick 1+2).

How it plugs in:
- ``llm_service`` calls :func:`note_usage` after every provider call (exact token counts
  from the provider's response).
- A feature entry point (chat message, fleet message, script generation…) wraps its work
  in :func:`start_collection` / :func:`finish_collection` (contextvar-based, asyncio-safe)
  and then persists everything with :func:`record` — one ledger row per model call, the
  first row carrying the action count.
- Before calling the model it checks :func:`gate`; the wall only blocks when
  ``ENFORCE_AI_QUOTA`` is on (default off — self-hosted/dev instances just collect data).

Failure policy (§4): metering is best-effort — a metering bug must never punish the
customer. ``record`` swallows and logs its own errors; callers never wrap it in flow
control.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.ai_usage import AiUsage
from app.models.user import User
from app.services.entitlements import limits_for

logger = logging.getLogger(__name__)

# ── Price table (USD per 1M tokens) — cost ESTIMATES for the ledger ───────────
# Prefix-matched against the model id; unknown models are recorded at cost 0 (the
# token counts are still exact). Update alongside provider pricing.
_PRICES_PER_MTOK: list[tuple[str, float, float]] = [
    # (model-id prefix, input $/M, output $/M)
    ("claude-opus", 15.0, 75.0),
    ("claude-sonnet", 3.0, 15.0),
    ("claude-haiku", 1.0, 5.0),
    ("claude-3-5-haiku", 0.8, 4.0),
    ("gpt-4o-mini", 0.15, 0.6),
    ("gpt-4o", 2.5, 10.0),
    ("gemini-1.5-pro", 1.25, 5.0),
    ("gemini-1.5-flash", 0.075, 0.3),
]


def _cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float:
    """Cost estimate incl. prompt caching: cache reads ≈ 10% of the input price and
    writes ≈ 125% (Anthropic); OpenAI-style caches read at ~50%, write free."""
    for prefix, in_price, out_price in _PRICES_PER_MTOK:
        if model.startswith(prefix):
            read_mult, write_mult = (0.5, 0.0) if prefix.startswith("gpt") else (0.1, 1.25)
            return (
                input_tokens * in_price
                + cache_read * in_price * read_mult
                + cache_write * in_price * write_mult
                + output_tokens * out_price
            ) / 1_000_000
    return 0.0


# ── Usage collection (contextvar — one collection per request/task) ───────────

_collector: ContextVar[list[dict] | None] = ContextVar("ai_usage_collector", default=None)


def start_collection():
    """Begin collecting model-call usage for the current async context. Returns a token
    for :func:`finish_collection`."""
    return _collector.set([])


def finish_collection(token) -> list[dict]:
    """Stop collecting and return the calls seen: [{model, input_tokens, output_tokens}]."""
    calls = _collector.get() or []
    _collector.reset(token)
    return calls


def note_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> None:
    """Called by llm_service after each provider call. No-op unless a collection is
    active in this context. ``cache_read``/``cache_write`` are prompt-cache tokens."""
    calls = _collector.get()
    if calls is not None:
        calls.append({
            "model": model or "",
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
            "cache_read": int(cache_read or 0),
            "cache_write": int(cache_write or 0),
        })


# ── Monthly period + counter ──────────────────────────────────────────────────

def period_start(now: datetime | None = None) -> datetime:
    """Current period start — first of the calendar month, UTC. (The billing-anchor
    reset arrives with Brick 3.)"""
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def period_reset(now: datetime | None = None) -> datetime:
    """When the current period rolls over (first of next month, UTC)."""
    start = period_start(now)
    return (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )


async def actions_used(db: AsyncSession, user_id) -> int:
    """Actions consumed by a user this period — SUM over the ledger (source of truth)."""
    return (
        await db.execute(
            select(func.coalesce(func.sum(AiUsage.actions), 0)).where(
                AiUsage.user_id == user_id,
                AiUsage.created_at >= period_start(),
            )
        )
    ).scalar_one()


@dataclass
class GateResult:
    allowed: bool
    used: int
    limit: int
    resets_at: str  # ISO date the allowance resets
    enforced: bool


async def gate(db: AsyncSession, user: User) -> GateResult:
    """Check the user's action allowance. Always returns the numbers; only blocks
    (allowed=False) when ENFORCE_AI_QUOTA is on."""
    limit = limits_for(user)["actions_per_month"]
    used = await actions_used(db, user.id)
    enforced = bool(settings.ENFORCE_AI_QUOTA)
    allowed = (used < limit) if enforced else True
    return GateResult(
        allowed=allowed,
        used=used,
        limit=limit,
        resets_at=period_reset().date().isoformat(),
        enforced=enforced,
    )


def quota_message(g: GateResult) -> str:
    """The friendly wall text (easy English — non-technical users)."""
    return (
        f"You've used all {g.limit} Ally actions for this month. "
        f"Your allowance resets on {g.resets_at}. "
        "Upgrade to Pro for a bigger allowance, or add your own AI key."
    )


# ── Ledger writes ─────────────────────────────────────────────────────────────

async def record(
    db: AsyncSession,
    *,
    user_id,
    feature: str,
    calls: list[dict],
    server_id=None,
    actions: int = 1,
    fuel: str = "included",
    status: str = "ok",
    skill: str | None = None,
) -> None:
    """Persist one ledger row per model call; the FIRST row carries ``actions`` and the
    rest carry 0 (one user request = one action, however many calls it needed).

    Best-effort by contract: any failure is logged and swallowed — metering must never
    break the feature that called it.
    """
    try:
        if not calls:
            return
        for i, call in enumerate(calls):
            model = call.get("model", "")
            in_tok = int(call.get("input_tokens", 0))
            out_tok = int(call.get("output_tokens", 0))
            c_read = int(call.get("cache_read", 0))
            c_write = int(call.get("cache_write", 0))
            db.add(
                AiUsage(
                    user_id=user_id,
                    server_id=server_id,
                    feature=feature,
                    skill=skill,
                    model=model,
                    fuel=fuel,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cache_read_tokens=c_read,
                    cache_write_tokens=c_write,
                    cost_usd=_cost_usd(model, in_tok, out_tok, c_read, c_write),
                    actions=actions if i == 0 else 0,
                    status=status,
                )
            )
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — metering never punishes the customer
        logger.error("ai_usage record failed (feature=%s user=%s): %s", feature, user_id, exc)
