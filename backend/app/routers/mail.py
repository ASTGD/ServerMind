"""Mail health — will this domain's email arrive.

Read-only apart from turning a domain's checking on or off. The check itself runs entirely
from ServerAlly against public DNS: nothing touches the customer's server, so this works
for a domain on a host we do not manage at all.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.mail_health import MailHealthRecord
from app.models.site import Site
from app.models.user import User
from app.services import mail_service
from app.workers import mail_worker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mail", tags=["mail"])

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class WatchBody(BaseModel):
    """Which domains to check. Empty means every site the customer has."""
    domains: list[str] = Field(default_factory=list, max_length=500)


def _public(r: MailHealthRecord) -> dict:
    return {
        "id": str(r.id), "domain": r.domain, "verdict": r.verdict, "score": r.score,
        "summary": r.summary, "findings": r.findings or [],
        "has_mx": r.has_mx, "spf": r.spf, "dkim_selector": r.dkim_selector,
        "dmarc": r.dmarc, "sending_ip": r.sending_ip,
        "last_checked": r.last_checked.isoformat() if r.last_checked else None,
    }


@router.get("")
async def list_mail_health(db: DBDep, current_user: CurrentUser) -> dict:
    rows = (await db.execute(
        select(MailHealthRecord).where(MailHealthRecord.user_id == current_user.id)
        .order_by(MailHealthRecord.score))).scalars().all()
    failing = sum(1 for r in rows if r.verdict == "failing")
    return {"domains": [_public(r) for r in rows], "count": len(rows), "failing": failing}


@router.post("/watch")
async def watch(body: WatchBody, db: DBDep, current_user: CurrentUser) -> dict:
    """Start checking domains. Defaults to every website the customer has."""
    wanted: list[str] = []
    if body.domains:
        for raw in body.domains:
            try:
                wanted.append(mail_service.clean_domain_for_mail(raw))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        wanted = [s.domain for s in (await db.execute(
            select(Site).where(Site.user_id == current_user.id,
                               Site.is_present.is_(True)))).scalars().all()]

    known = {r.domain for r in (await db.execute(
        select(MailHealthRecord).where(
            MailHealthRecord.user_id == current_user.id))).scalars().all()}

    added = 0
    for domain in wanted:
        if domain in known:
            continue
        db.add(MailHealthRecord(user_id=current_user.id, domain=domain, is_active=True))
        known.add(domain)
        added += 1
    if added:
        await db.commit()
    return {"added": added,
            "message": (f"Checking email for {added} domain{'' if added == 1 else 's'}. "
                        "The first results appear within a few minutes."
                        if added else "Every domain is already being checked.")}


@router.post("/{record_id}/check")
async def check_now(record_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    record = (await db.execute(
        select(MailHealthRecord).where(MailHealthRecord.id == record_id,
                                       MailHealthRecord.user_id == current_user.id)
    )).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Not checking that domain.")
    await mail_worker.check_one(record.id)
    await db.refresh(record)
    return _public(record)


@router.delete("/{record_id}", status_code=204)
async def stop_watching(record_id: str, db: DBDep, current_user: CurrentUser) -> None:
    record = (await db.execute(
        select(MailHealthRecord).where(MailHealthRecord.id == record_id,
                                       MailHealthRecord.user_id == current_user.id)
    )).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="Not checking that domain.")
    await db.delete(record)
    await db.commit()
