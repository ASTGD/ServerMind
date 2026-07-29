"""DNS — connect a provider, read zones, change records.

Records are read live on every request rather than cached. A cached copy of DNS drifts
from the authoritative answer, and stale DNS presented as current is worse than showing
nothing: someone would fix a record that was already fixed, or trust one that is wrong.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.dns_account import DnsAccount
from app.models.user import User
from app.services import audit_service, dns_service as dns
from app.services.crypto_service import encrypt

router = APIRouter(prefix="/api/dns", tags=["dns"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class ConnectIn(BaseModel):
    provider: str = Field(default="cloudflare", max_length=30)
    label: str = Field(max_length=255)
    api_token: str = Field(min_length=8, max_length=500)


class RecordIn(BaseModel):
    type: str = Field(max_length=10)
    name: str = Field(max_length=255)
    content: str = Field(max_length=4000)
    ttl: int = Field(default=300, ge=1, le=604_800)
    priority: int | None = Field(default=None, ge=0, le=65535)
    proxied: bool | None = None


async def _account(account_id: str, db: AsyncSession, user: User) -> DnsAccount:
    a = await db.get(DnsAccount, account_id)
    if not a or a.user_id != user.id:
        raise HTTPException(status_code=404, detail="No such DNS account.")
    return a


@router.get("/accounts")
async def list_accounts(db: DBDep, current_user: CurrentUser) -> dict:
    rows = (await db.execute(
        select(DnsAccount).where(DnsAccount.user_id == current_user.id)
        .order_by(DnsAccount.created_at)
    )).scalars().all()
    return {"accounts": [dns.public_account(a) for a in rows], "count": len(rows)}


@router.post("/accounts", status_code=201)
async def connect(body: ConnectIn, db: DBDep, current_user: CurrentUser) -> dict:
    """Connect a DNS provider.

    The token is VERIFIED before it is stored. A credential that does not work is worse
    than none: it sits there looking connected until someone urgently needs to change a
    record and discovers it never worked.
    """
    token = dns.clean_token(body.api_token)
    if not dns.looks_like_token(token):
        # Said before the round trip, because "Invalid request headers" from Cloudflare
        # does not tell anyone that they pasted the wrong box's contents.
        raise HTTPException(
            status_code=422,
            detail="That does not look like a Cloudflare API token. It is about 40 "
                   "letters and numbers, shown once when you create it — not the "
                   "Global API Key and not your account ID.")
    cred = {"api_token": token}
    try:
        await dns.verify_credential(body.provider, cred)
    except dns.DnsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    a = DnsAccount(user_id=current_user.id, provider=body.provider.lower(),
                   label=body.label.strip()[:255] or body.provider,
                   encrypted_credential=encrypt(json.dumps(cred)))
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return dns.public_account(a)


@router.delete("/accounts/{account_id}", status_code=204)
async def disconnect(account_id: str, db: DBDep, current_user: CurrentUser) -> None:
    a = await _account(account_id, db, current_user)
    await db.delete(a)
    await db.commit()


@router.get("/accounts/{account_id}/zones")
async def zones(account_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    a = await _account(account_id, db, current_user)
    try:
        found = await dns.list_zones(a)
    except dns.DnsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"zones": [{"id": z.zone_id, "name": z.name, "status": z.status}
                      for z in found], "count": len(found)}


@router.get("/accounts/{account_id}/zones/{zone_id}/records")
async def records(account_id: str, zone_id: str, zone: str, db: DBDep,
                  current_user: CurrentUser) -> dict:
    a = await _account(account_id, db, current_user)
    try:
        found = await dns.list_records(a, zone_id)
    except dns.DnsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"zone": zone, "records": [dns.public_record(r) for r in found],
            "count": len(found), "editable_types": list(dns.MANAGED_TYPES)}


@router.post("/accounts/{account_id}/zones/{zone_id}/records", status_code=201)
async def create(account_id: str, zone_id: str, zone: str, body: RecordIn,
                 db: DBDep, current_user: CurrentUser) -> dict:
    a = await _account(account_id, db, current_user)
    try:
        rec = dns.validate(type_=body.type, name=body.name, content=body.content,
                           zone=zone, ttl=body.ttl, priority=body.priority)
    except dns.InvalidRecord as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.proxied is not None:
        rec["proxied"] = body.proxied
    try:
        made = await dns.create_record(a, zone_id, rec)
    except dns.DnsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # DNS changes are the ones people need to reconstruct later — "when did this break?"
    # is usually answered by finding the record change that caused it.
    await audit_service.audit(db, current_user, "dns.record.create",
                               meta={"zone": zone, "type": rec["type"],
                                     "name": rec["name"], "content": rec["content"]})
    return dns.public_record(made)


@router.put("/accounts/{account_id}/zones/{zone_id}/records/{record_id}")
async def update(account_id: str, zone_id: str, record_id: str, zone: str,
                 body: RecordIn, db: DBDep, current_user: CurrentUser) -> dict:
    a = await _account(account_id, db, current_user)
    try:
        rec = dns.validate(type_=body.type, name=body.name, content=body.content,
                           zone=zone, ttl=body.ttl, priority=body.priority)
    except dns.InvalidRecord as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.proxied is not None:
        rec["proxied"] = body.proxied
    try:
        made = await dns.update_record(a, zone_id, record_id, rec)
    except dns.DnsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await audit_service.audit(db, current_user, "dns.record.update",
                               meta={"zone": zone, "type": rec["type"],
                                     "name": rec["name"], "content": rec["content"]})
    return dns.public_record(made)


@router.delete("/accounts/{account_id}/zones/{zone_id}/records/{record_id}",
               status_code=204)
async def remove(account_id: str, zone_id: str, record_id: str, zone: str,
                 db: DBDep, current_user: CurrentUser) -> None:
    a = await _account(account_id, db, current_user)
    try:
        await dns.delete_record(a, zone_id, record_id)
    except dns.DnsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await audit_service.audit(db, current_user, "dns.record.delete",
                               meta={"zone": zone, "record_id": record_id})


@router.get("/check")
async def check(type: str, name: str, content: str, zone: str,
                current_user: CurrentUser, ttl: int = 300,
                priority: int | None = None) -> dict:
    """Validate a record WITHOUT saving it, and return any warning.

    The UI calls this as the owner types, so the objection arrives before the mistake
    rather than after — which for DNS is the difference between a correction and an
    outage.
    """
    try:
        dns.validate(type_=type, name=name, content=content, zone=zone,
                     ttl=ttl, priority=priority)
    except dns.InvalidRecord as exc:
        return {"ok": False, "error": str(exc), "warning": None}
    return {"ok": True, "error": None,
            "warning": dns.warn_for(type_=type, name=name, zone=zone)}
