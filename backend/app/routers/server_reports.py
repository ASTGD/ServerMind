"""Whole-server report — one aggregate report across ALL of a server's finished missions.

A per-mission report (``/api/missions/{id}/incident-report``) explains one incident; this
rolls up an entire server: every finished mission's outcome synthesized into a single
owner-/management-facing summary. Generated on demand (1 AI action); the frontend renders
it and offers PDF / Markdown export. See ai_service.explain_server_report.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.mission import Mission
from app.models.user import User
from app.services import ai_service, metering_service, mission_service

router = APIRouter(prefix="/api/servers", tags=["reports"])

_FINISHED = ("complete", "blocked", "failed", "stopped")


def _verdict(m: Mission) -> str:
    """A short, plain outcome label for one mission (mirrors the frontend's verdict)."""
    if m.status == "complete":
        return "Verified" if m.verified else ("Not confirmed" if m.verified is False else "Done")
    return {"blocked": "Needs your OK", "stopped": "Stopped", "failed": "Failed"}.get(m.status, m.status)


def _brief(m: Mission) -> dict:
    """Condense one mission into the brief the aggregator summarizes from."""
    result = mission_service.result_of(m) or {}
    when = m.updated_at or m.created_at
    return {
        "date": when.strftime("%Y-%m-%d") if when else "",
        "goal": (m.goal or "")[:400],
        "verdict": _verdict(m),
        "headline": result.get("headline") or "",
        "found": result.get("found") or [],
        "did": result.get("did") or [],
        "left": result.get("left") or [],
        "summary": m.summary or "",
    }


@router.post("/{server_id}/report")
async def generate_server_report(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate the whole-server report from this server's finished missions. One AI action."""
    server = await resolve_server(server_id, current_user, db)  # view access (owner/team)

    missions = await mission_service.list_for_user(
        db, current_user, server_id=str(server.id), limit=200
    )
    finished = [m for m in missions if m.status in _FINISHED]
    if not finished:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No finished missions on this server yet — run a mission first.",
        )

    # AI quota gate — one aggregate report = 1 action.
    g = await metering_service.gate(db, current_user)
    if not g.allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=metering_service.quota_message(g),
        )

    briefs = [_brief(m) for m in reversed(finished)]  # oldest first for the timeline
    tok = metering_service.start_collection()
    try:
        report = await ai_service.explain_server_report(
            server.name, briefs, user_language=current_user.preferred_language or "en"
        )
    except Exception as exc:  # noqa: BLE001
        calls = metering_service.finish_collection(tok)
        await metering_service.record(
            db, user_id=current_user.id, feature="server_report", calls=calls,
            actions=0, status="provider_error",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Couldn't generate the server report: {exc}",
        )
    calls = metering_service.finish_collection(tok)
    await metering_service.record(db, user_id=current_user.id, feature="server_report", calls=calls)

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't generate the server report — please try again.",
        )
    return {
        "server_id": str(server.id),
        "server_name": server.name,
        "mission_count": len(finished),
        "report": report,
    }
