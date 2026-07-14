"""Missions router — mission history + detail (Ally Missions Phase 3).

Read-only: the mission LOOP runs over the WebSocket (start/resume/stop are chat-socket
messages). These endpoints expose the persisted record so the UI can show a history
list, a detail view, and detect a resumable (``interrupted``) mission. Scoped to the
signed-in user's own missions.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import ai_service, metering_service, mission_service

router = APIRouter(prefix="/api/missions", tags=["missions"])


@router.get("")
async def list_missions(
    server_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """The user's mission history (newest first); optionally filtered to one server."""
    missions = await mission_service.list_for_user(db, current_user, limit=limit, server_id=server_id)
    return [mission_service.to_dict(m) for m in missions]


@router.get("/{mission_id}")
async def get_mission(
    mission_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """One mission with its full step transcript."""
    m = await mission_service.get_for_user(db, current_user, mission_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission_service.to_dict(m, include_steps=True)


@router.post("/{mission_id}/incident-report")
async def generate_incident_report(
    mission_id: str,
    refresh: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """"Explain this incident" — synthesize the mission's durable transcript into a
    plain-language story (how it happened + timeline + impact). Cached on the mission;
    ``refresh=true`` regenerates. One AI action from the acting user's pool."""
    m = await mission_service.get_for_user(db, current_user, mission_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    cached = mission_service.incident_report_of(m)
    if cached and not refresh:
        return cached  # already generated — no AI call, no action charged

    steps = mission_service.steps_of(m)
    if not steps:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This mission has no recorded steps to explain.",
        )

    # AI quota gate (docs/AI-METERING.md) — generating a report = 1 action.
    g = await metering_service.gate(db, current_user)
    if not g.allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=metering_service.quota_message(g),
        )

    tok = metering_service.start_collection()
    try:
        report = await ai_service.explain_incident(
            goal=m.goal,
            steps=steps,
            server_name=m.server_name,
            result=mission_service.result_of(m),
            summary=m.summary,
            user_language=current_user.preferred_language or "en",
        )
    except Exception as exc:  # noqa: BLE001
        calls = metering_service.finish_collection(tok)
        await metering_service.record(
            db, user_id=current_user.id, feature="incident_report", calls=calls,
            actions=0, status="provider_error",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Couldn't generate the incident report: {exc}",
        )
    calls = metering_service.finish_collection(tok)
    await metering_service.record(
        db, user_id=current_user.id, feature="incident_report", calls=calls,
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't generate the incident report — please try again.",
        )
    await mission_service.save_incident_report(db, m, report)
    return report
