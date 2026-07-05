"""Fleet router — proactive fleet intelligence (Ally's "what needs attention").

Read-only + cheap (no AI, no SSH): analyzes the data ServerAlly already collects into
per-server health scores + ranked, plain-English findings, each with a one-click
action. Scoped to the signed-in user's accessible servers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import digest_service, fleet_service, team_service

router = APIRouter(prefix="/api/fleet", tags=["fleet"])

_DIGEST_FREQUENCIES = {"off", "weekly", "daily"}


@router.get("/health")
async def fleet_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Every accessible server, worst-first, with a health score and ranked findings."""
    servers = await team_service.accessible_servers(db, current_user)
    fleet = await fleet_service.analyze_fleet(db, servers)
    return {
        "servers": [fleet_service.to_dict(h) for h in fleet],
        "summary": fleet_service.summarize(fleet),
    }


# ── Fleet-health email digest ─────────────────────────────────────────────────

class DigestPref(BaseModel):
    frequency: str  # 'off' | 'weekly' | 'daily'


@router.put("/digest")
async def set_digest_frequency(
    body: DigestPref,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Set how often Ally emails this user their fleet-health digest."""
    if body.frequency not in _DIGEST_FREQUENCIES:
        raise HTTPException(status_code=422, detail="frequency must be off, weekly, or daily")
    current_user.digest_frequency = body.frequency
    await db.commit()
    return {"frequency": body.frequency}


@router.get("/digest/preview")
async def digest_preview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """The digest this user would receive right now (subject + HTML + text), or a flag
    that there's nothing to send yet."""
    digest = await digest_service.build_for_user(db, current_user)
    if digest is None:
        return {"empty": True, "frequency": current_user.digest_frequency}
    return {"empty": False, "frequency": current_user.digest_frequency, **digest}


@router.post("/digest/test")
async def digest_send_test(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Email this user their digest now (a "send me one" button). Reports whether an
    email went out — a send failure surfaces as a 502 with a plain reason."""
    if not current_user.email:
        return {"sent": False, "reason": "no email address on your account"}
    try:
        sent = await digest_service.send_for_user(db, current_user)
    except Exception as exc:  # noqa: BLE001 — surface SMTP problems honestly
        raise HTTPException(status_code=502, detail=f"Could not send the email: {exc}")
    return {
        "sent": sent,
        "reason": "" if sent else "You have no servers yet, so there's nothing to report.",
    }
