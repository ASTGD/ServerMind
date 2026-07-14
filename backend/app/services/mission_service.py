"""Mission persistence (Ally Missions Phase 3) — durable, resumable, reviewable.

The mission loop lives on the WebSocket; this checkpoints its state to the DB after
every step so a dropped socket doesn't lose the mission (it becomes ``interrupted``
and resumable from the saved transcript) and so there's a reviewable history.

Two audiences, two conventions:
- **Loop-facing writes** (``start`` / ``checkpoint`` / ``finalize`` /
  ``mark_interrupted``) open their OWN short-lived session and are BEST-EFFORT — a
  persistence hiccup must never break a running mission, so they log and swallow.
- **Router-facing reads** (``list_for_user`` / ``get_for_user`` / ``to_dict``) take
  the request's ``db`` and are ordinary (errors surface as HTTP errors).
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.mission import Mission
from app.models.server import Server
from app.models.user import User

logger = logging.getLogger(__name__)

_LIVE_STATUSES = ("running", "awaiting_approval")


# ── Loop-facing writes (own session, best-effort) ─────────────────────────────

async def start(
    *, user_id: uuid.UUID, server: Server | None, skill_slug: str | None,
    goal: str, budget: int,
) -> uuid.UUID | None:
    """Create a running mission row; return its id (or None if persistence failed —
    the mission still runs, just un-checkpointed)."""
    try:
        async with AsyncSessionLocal() as db:
            mission = Mission(
                user_id=user_id,
                server_id=server.id if server is not None else None,
                server_name=server.name if server is not None else None,
                skill_slug=skill_slug,
                goal=goal[:2000],
                status="running",
                steps="[]",
                steps_used=0,
                budget=budget,
            )
            db.add(mission)
            await db.commit()
            return mission.id
    except Exception as exc:  # noqa: BLE001 — persistence must never break a mission
        logger.warning("mission persist (start) failed: %s", exc)
        return None


async def checkpoint(
    mission_id: uuid.UUID | None, *, status: str, steps: list[dict],
    verified: bool | None = None, summary: str | None = None,
    result: dict | None = None,
) -> None:
    """Update a mission's transcript + status. Called after every step (and on
    terminal states). No-op if the mission wasn't persisted."""
    if mission_id is None:
        return
    try:
        values: dict = {
            "status": status,
            "steps": json.dumps(steps)[:2_000_000],  # hard guard on a runaway blob
            "steps_used": len(steps),
        }
        if verified is not None:
            values["verified"] = verified
        if summary is not None:
            values["summary"] = summary[:4000]
        if result is not None:
            values["result"] = json.dumps(result)[:8000]
        async with AsyncSessionLocal() as db:
            await db.execute(update(Mission).where(Mission.id == mission_id).values(**values))
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("mission persist (checkpoint) failed: %s", exc)


async def finalize(
    mission_id: uuid.UUID | None, *, status: str, steps: list[dict],
    verified: bool | None = None, summary: str | None = None,
    result: dict | None = None,
) -> None:
    """Terminal checkpoint (complete/blocked/failed/stopped). Same as checkpoint —
    named for intent at the call sites."""
    await checkpoint(
        mission_id, status=status, steps=steps, verified=verified,
        summary=summary, result=result,
    )


async def recover_orphaned() -> int:
    """On startup, any mission still marked live CAN'T really be running — the process
    that drove it is gone (deploy, restart, crash). Mark those ``interrupted`` so they
    become resumable instead of stuck forever. Returns how many were recovered."""
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                update(Mission).where(Mission.status.in_(_LIVE_STATUSES)).values(status="interrupted")
            )
            await db.commit()
            n = res.rowcount or 0
            if n:
                logger.info("recovered %d orphaned mission(s) → interrupted", n)
            return n
    except Exception as exc:  # noqa: BLE001 — recovery must never block startup
        logger.warning("mission orphan recovery failed: %s", exc)
        return 0


async def mark_interrupted(mission_id: uuid.UUID | None) -> None:
    """Flag a mission ``interrupted`` (resumable) — but ONLY if it's still live, so a
    disconnect that arrives just after the mission finished can't clobber its real
    terminal status."""
    if mission_id is None:
        return
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Mission)
                .where(Mission.id == mission_id, Mission.status.in_(_LIVE_STATUSES))
                .values(status="interrupted")
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("mission persist (interrupt) failed: %s", exc)


# ── Router-facing reads (caller's session) ────────────────────────────────────

async def list_for_user(db, user: User, *, limit: int = 50, server_id: str | None = None) -> list[Mission]:
    """A user's mission history, newest first. Scoped to the user's own missions."""
    stmt = select(Mission).where(Mission.user_id == user.id)
    if server_id:
        stmt = stmt.where(Mission.server_id == server_id)
    stmt = stmt.order_by(Mission.created_at.desc()).limit(min(limit, 200))
    return list((await db.execute(stmt)).scalars().all())


async def get_for_user(db, user: User, mission_id: str) -> Mission | None:
    """One mission by id, only if it belongs to the user."""
    try:
        mid = uuid.UUID(str(mission_id))
    except (ValueError, TypeError):
        return None
    m = await db.get(Mission, mid)
    return m if (m is not None and m.user_id == user.id) else None


def steps_of(mission: Mission) -> list[dict]:
    """Parse the stored transcript (empty list on any corruption)."""
    try:
        data = json.loads(mission.steps or "[]")
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


def result_of(mission: Mission) -> dict | None:
    """Parse the stored structured outcome (None if absent or corrupt)."""
    if not mission.result:
        return None
    try:
        data = json.loads(mission.result)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def incident_report_of(mission: Mission) -> dict | None:
    """Parse the stored AI incident narrative (None if absent or corrupt)."""
    if not mission.incident_report:
        return None
    try:
        data = json.loads(mission.incident_report)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


async def save_incident_report(db, mission: Mission, report: dict) -> None:
    """Cache a generated incident report on the mission (router-facing write)."""
    mission.incident_report = json.dumps(report)[:16000]
    await db.commit()


def to_dict(mission: Mission, *, include_steps: bool = False) -> dict:
    out = {
        "id": str(mission.id),
        "server_id": str(mission.server_id) if mission.server_id else None,
        "server_name": mission.server_name,
        "skill": mission.skill_slug,
        "goal": mission.goal,
        "status": mission.status,
        "verified": mission.verified,
        "summary": mission.summary,
        "result": result_of(mission),
        "steps_used": mission.steps_used,
        "budget": mission.budget,
        "resumable": mission.status == "interrupted",
        # Whether an "Explain this incident" narrative has been generated (light flag for
        # the list; the full report only rides the detail view).
        "has_incident_report": bool(mission.incident_report),
        "created_at": mission.created_at.isoformat() if mission.created_at else None,
        "updated_at": mission.updated_at.isoformat() if mission.updated_at else None,
    }
    if include_steps:
        out["steps"] = steps_of(mission)
        out["incident_report"] = incident_report_of(mission)
    return out
