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

from app.models.server import Server
from app.models.user import User
from app.services import (
    ai_context_service,
    ai_service,
    metering_service,
    skill_service,
)

logger = logging.getLogger(__name__)


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
