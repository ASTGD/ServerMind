"""Dev Door service (docs/EVAL-DRIVEN-DEV.md) — admin-only tooling to see EXACTLY what
Ally sees and produces, without touching a real server.

``dry_run`` plans a chat message through the REAL pipeline (the same context assembly and
``plan_commands`` the live WebSocket uses) but stops after planning — it NEVER executes a
command. It returns a full **Trace**: the prompt Ally received (stable system + volatile
tail), the raw model output, the parsed plan, and token/cost/model meta. This is the
foundation the Prompt Inspector renders.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.evals import Case, deterministic_cases, run
from app.evals.model import DETERMINISTIC_CATEGORIES
from app.models.ai_usage import AiUsage
from app.models.dev_eval_case import DevEvalCase
from app.models.server import Server
from app.models.user import User
from app.services import (
    ai_context_service,
    ai_service,
    metering_service,
    skill_service,
)

logger = logging.getLogger(__name__)

# Defence in depth: a captured eval case must never carry a real credential (an admin may
# capture a message/command that mentions one). Mask obvious secrets before storing.
_SECRET_KV_RE = re.compile(r"(?i)\b(password|passwd|secret|token|api[_-]?key|bearer)\b\s*[:=]\s*\S+")
_TOKEN_RE = re.compile(r"\b(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,}|AKIA[A-Z0-9]{12,}|xox[baprs]-[A-Za-z0-9-]{8,})\b")


def scrub_secret(text: str) -> str:
    """Mask ``password=…`` / ``token: …`` style pairs and standalone provider tokens."""
    text = _SECRET_KV_RE.sub(lambda m: f"{m.group(1)}=***", text)
    return _TOKEN_RE.sub("***", text)


def _meta_from_calls(calls: list[dict], trace: dict) -> dict:
    """Roll the metering collection up into display meta (exact provider token counts +
    the same cost estimate the ledger uses)."""
    cost = sum(
        metering_service._cost_usd(
            c.get("model", ""),
            c.get("input_tokens", 0),
            c.get("output_tokens", 0),
            c.get("cache_read", 0),
            c.get("cache_write", 0),
        )
        for c in calls
    )
    return {
        "models": [c.get("model", "") for c in calls],
        "calls": len(calls),
        "input_tokens": sum(c.get("input_tokens", 0) for c in calls),
        "output_tokens": sum(c.get("output_tokens", 0) for c in calls),
        "cache_read_tokens": sum(c.get("cache_read", 0) for c in calls),
        "cache_write_tokens": sum(c.get("cache_write", 0) for c in calls),
        "cost_usd": round(cost, 6),
        "escalated": bool(trace.get("escalated")),
        "retried_trimmed": bool(trace.get("retried_trimmed")),
    }


async def dry_run(server: Server, message: str, *, acting_user: User) -> dict:
    """Plan ``message`` against ``server`` exactly as chat would — but stop before
    executing. Returns ``{input, context, prompt, output, meta}``. Read-only: it assembles
    context (which may SSH-probe the server read-only via the scout / live look, same as
    real chat) and asks the model to plan, but NEVER runs a planned command.
    """
    language = acting_user.preferred_language or "en"
    skill = skill_service.match(message, server.os_type)

    # Same assembly the live WS handler uses → the dry-run sees exactly what chat sees.
    ctx = await ai_context_service.build_chat_context(
        server, message, acting_user_id=str(acting_user.id), skill=skill
    )

    trace: dict = {}
    tok = metering_service.start_collection()
    try:
        plan = await ai_service.plan_commands(
            message,
            server,
            language,
            server_profile=ctx.server_profile,
            memories=ctx.memories,
            skill=skill,
            skill_menu=ctx.skill_menu,
            live_snapshot=ctx.live_snapshot,
            other_servers=ctx.other_servers,
            scout=ctx.scout,
            ally_mode=ctx.ally_mode,
            trace=trace,
        )
    finally:
        calls = metering_service.finish_collection(tok)

    return {
        "input": {
            "message": message,
            "server": {
                "id": str(server.id),
                "name": server.name,
                "os_type": server.os_type,
                "connection_type": server.connection_type,
            },
            "ally_mode": ctx.ally_mode,
            "language": language,
        },
        "context": {
            "skill": skill.slug if skill else None,
            "skill_menu_offered": ctx.skill_menu is not None,
            "has_live_snapshot": bool(ctx.live_snapshot),
            "has_scout": bool(ctx.scout),
            "has_server_profile": bool(ctx.server_profile),
            "has_memories": bool(ctx.memories),
            "other_servers": ctx.other_servers,
            "use_skill_requested": plan.get("use_skill"),
        },
        "prompt": {
            "system": trace.get("system", ""),
            "volatile": trace.get("volatile", ""),
        },
        "output": {
            "raw": trace.get("raw", ""),
            "parsed": plan,
        },
        "meta": _meta_from_calls(calls, trace),
    }


# ── Eval runner + case capture (Phase 3 — the flywheel) ───────────────────────

async def run_evals(db: AsyncSession) -> dict:
    """Run the deterministic corpus + any admin-captured cases (offline, no API). Returns a
    per-category pass-rate summary, the failures, and each captured case's live result."""
    corpus_cases = deterministic_cases()
    rows = (
        await db.execute(select(DevEvalCase).order_by(DevEvalCase.created_at))
    ).scalars().all()
    captured_cases = [
        Case(
            id=f"captured:{r.id}",
            category=r.category,
            input=r.input,
            expected=r.expected,
            os=r.os or "linux",
            provenance="captured",
        )
        for r in rows
    ]
    result = run(cases=corpus_cases + captured_cases)

    captured_by_key = {f"captured:{r.id}": r for r in rows}
    failures: list[dict] = []
    captured_out: list[dict] = []
    for res in result.results:
        row = captured_by_key.get(res.case.id)
        if not res.passed:
            failures.append({
                "category": res.case.category,
                "input": res.case.input,
                "expected": res.case.expected,
                "got": res.got,
                "error": res.error,
                "source": "captured" if row is not None else "corpus",
            })
        if row is not None:
            captured_out.append({
                "id": str(row.id),
                "category": row.category,
                "input": row.input,
                "expected": row.expected,
                "os": row.os,
                "note": row.note,
                "got": res.got,
                "passed": res.passed,
            })
    return {
        "summary": {"total": result.total, "passed": result.passed, "ok": result.ok},
        "by_category": [
            {"category": c, "passed": p, "total": t}
            for c, (p, t) in result.by_category().items()
        ],
        "failures": failures,
        "captured": captured_out,
    }


async def capture_case(
    db: AsyncSession,
    *,
    category: str,
    input: str,
    expected: str,
    os: str = "linux",
    note: str | None = None,
) -> DevEvalCase:
    """Store a new captured eval case (category validated, input/note secret-scrubbed)."""
    if category not in DETERMINISTIC_CATEGORIES:
        raise ValueError(f"unknown eval category: {category!r}")
    row = DevEvalCase(
        category=category,
        input=scrub_secret(input.strip()),
        expected=(expected.strip() or "None"),
        os=os or "linux",
        note=scrub_secret(note.strip()) if note else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_captured(db: AsyncSession) -> list[DevEvalCase]:
    return list(
        (await db.execute(select(DevEvalCase).order_by(DevEvalCase.created_at.desc())))
        .scalars()
        .all()
    )


async def delete_captured(db: AsyncSession, case_id) -> bool:
    row = await db.get(DevEvalCase, case_id)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


# ── Observability (Phase 4) — the AI ledger, admin view ───────────────────────

async def activity(db: AsyncSession, limit: int = 60) -> dict:
    """Recent AI calls (the ai_usage ledger) + this period's cost/actions summary — so an
    admin can see what Ally is doing and what it costs. Counts + labels only (the ledger
    never stores prompt/response content — no secrets by construction)."""
    period = metering_service.period_start()

    rows = (
        await db.execute(
            select(AiUsage, User.email, Server.name)
            .join(User, User.id == AiUsage.user_id, isouter=True)
            .join(Server, Server.id == AiUsage.server_id, isouter=True)
            .order_by(AiUsage.created_at.desc())
            .limit(limit)
        )
    ).all()
    recent = [
        {
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "feature": u.feature,
            "model": u.model,
            "skill": u.skill,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cache_read_tokens": u.cache_read_tokens,
            "cost_usd": float(u.cost_usd or 0),
            "actions": u.actions,
            "status": u.status,
            "user": email,
            "server": server_name,
        }
        for (u, email, server_name) in rows
    ]

    totals = (
        await db.execute(
            select(
                func.coalesce(func.sum(AiUsage.cost_usd), 0),
                func.coalesce(func.sum(AiUsage.actions), 0),
                func.count(),
            ).where(AiUsage.created_at >= period)
        )
    ).one()

    by_feature = (
        await db.execute(
            select(AiUsage.feature, func.coalesce(func.sum(AiUsage.cost_usd), 0), func.count())
            .where(AiUsage.created_at >= period)
            .group_by(AiUsage.feature)
            .order_by(func.sum(AiUsage.cost_usd).desc())
        )
    ).all()

    # Cost trend — one point per day this period (the Dev Door charts it, Phase 5).
    day = func.date_trunc("day", AiUsage.created_at)
    daily_rows = (
        await db.execute(
            select(day, func.coalesce(func.sum(AiUsage.cost_usd), 0), func.count())
            .where(AiUsage.created_at >= period)
            .group_by(day)
            .order_by(day)
        )
    ).all()
    daily = [
        {
            "day": (d.date().isoformat() if hasattr(d, "date") else str(d)),
            "cost_usd": float(c or 0),
            "calls": int(n or 0),
        }
        for (d, c, n) in daily_rows
    ]

    return {
        "period_start": period.isoformat(),
        "summary": {
            "cost_usd": float(totals[0] or 0),
            "actions": int(totals[1] or 0),
            "calls": int(totals[2] or 0),
        },
        "by_feature": [
            {"feature": f, "cost_usd": float(c or 0), "calls": int(n or 0)}
            for (f, c, n) in by_feature
        ],
        "daily": daily,
        "recent": recent,
    }
