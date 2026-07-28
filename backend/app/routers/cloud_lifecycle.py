"""Create, restart, resize and destroy servers in a connected cloud account.

Every route here re-reads the instance from the provider before acting. That is not
caution for its own sake: the browser's copy of a server list is the thing most likely to
be wrong at the moment someone presses a button, and the two operations that matter —
resize and destroy — are decided entirely by what the server is *now*.

Everything that changes something is audit-logged, and everything that costs money or
deletes data goes through the guards in `cloud_lifecycle_service` first.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, require_verified
from app.models.cloud_account import CloudAccount
from app.models.server import Server
from app.models.user import User
from app.services import audit_service, cloud_service, metering_service
from app.services import cloud_lifecycle_service as cl
from app.services.cloud_service import CloudError
from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cloud-accounts/{account_id}", tags=["cloud"])

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
VerifiedUser = Annotated[User, Depends(require_verified)]


class CreateBody(BaseModel):
    name: str = Field(max_length=64)
    region: str = Field(max_length=64)
    size: str = Field(max_length=64)
    image: str = Field(max_length=64)
    ssh_keys: list[str] = Field(default_factory=list, max_length=20)


class ResizeBody(BaseModel):
    size: str = Field(max_length=64)
    # Off by default on purpose: the safe half of this operation is the one that happens
    # if nobody thinks about it.
    grow_disk: bool = False


class DestroyBody(BaseModel):
    """The typed name is the whole safety mechanism, so it is required, not optional."""
    confirm_name: str = Field(max_length=64)


async def _account(account_id: uuid.UUID, user: User, db: AsyncSession) -> CloudAccount:
    acct = (await db.execute(
        select(CloudAccount).where(CloudAccount.id == account_id,
                                   CloudAccount.user_id == user.id)
    )).scalar_one_or_none()
    if acct is None:
        raise HTTPException(status_code=404, detail="Cloud account not found")
    return acct


def _adapter(acct: CloudAccount) -> cl._LifecycleAdapter:
    try:
        return cl.adapter(acct.provider, json.loads(decrypt(acct.encrypted_credential)))
    except cl.InvalidRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _run(fn, *args, **kw):
    """Provider calls are blocking HTTP; keep them off the event loop."""
    import asyncio
    return await asyncio.to_thread(fn, *args, **kw)


def _fail(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


# ── what can be built ─────────────────────────────────────────────────────────
@router.get("/catalogue")
async def catalogue(account_id: uuid.UUID, db: DBDep, current_user: CurrentUser) -> dict:
    """Regions, sizes, images and SSH keys, read live from the provider."""
    acct = await _account(account_id, current_user, db)
    if not cl.supports_lifecycle(acct.provider):
        return {"supported": False, "provider": acct.provider,
                "message": ("ServerAlly can list servers on this provider but cannot "
                            "create or delete them there yet. That works on DigitalOcean "
                            "and Hetzner today.")}
    try:
        cat = await _run(_adapter(acct).catalogue)
    except CloudError as exc:
        raise _fail(exc) from exc
    return {
        "supported": True, "provider": acct.provider,
        "regions": cat.regions,
        "sizes": [s.__dict__ for s in cat.sizes],
        "images": cat.images,
        "ssh_keys": cat.ssh_keys,
    }


@router.post("/instances", status_code=201)
async def create_instance(account_id: uuid.UUID, body: CreateBody, request: Request,
                          db: DBDep, current_user: VerifiedUser) -> dict:
    """Create a server. Costs money from the moment it exists."""
    acct = await _account(account_id, current_user, db)
    ad = _adapter(acct)
    try:
        spec = {"name": cl.valid_name(body.name),
                "region": cl.valid_slug(body.region, "region"),
                "size": cl.valid_slug(body.size, "size"),
                "image": cl.valid_slug(body.image, "operating system"),
                "ssh_keys": [cl.valid_slug(k, "SSH key") for k in body.ssh_keys]}
    except cl.InvalidRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # A new server will be imported and counted, so refuse before spending rather than
    # after: a server the plan will not let them manage is money already gone.
    gate = await metering_service.servers_gate(db, current_user)
    if not gate.allowed:
        raise HTTPException(status_code=402,
                            detail=metering_service.servers_message(gate))

    # Fails CLOSED. If the account cannot be listed we cannot prove this name is free,
    # and the cost of guessing wrong is a second server billing forever that nobody is
    # watching. An earlier version swallowed this and skipped the check entirely.
    try:
        existing = await _run(ad.list_instances)
    except CloudError as exc:
        raise HTTPException(
            status_code=502,
            detail=(f"Could not check this account for an existing server called "
                    f"“{spec['name']}” before creating one, so nothing was created: "
                    f"{exc}")) from exc
    try:
        cl.check_duplicate_name(existing, spec["name"])
    except cl.InvalidRequest as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        inst = await _run(ad.create, spec)
    except CloudError as exc:
        raise _fail(exc) from exc

    await audit_service.audit(
        db, current_user, "cloud.instance_created",
        target_type="cloud_account", target_id=acct.id,
        meta={"provider": acct.provider, "name": spec["name"], "size": spec["size"],
              "region": spec["region"], "instance_id": inst.instance_id}, request=request)
    logger.info("Created %s instance %s for user %s", acct.provider, inst.instance_id,
                current_user.id)
    return {"instance": inst.dict(),
            "message": ("It is starting up. Its address appears within a minute or two — "
                        "then import it to manage it here.")}


# ── acting on one that exists ─────────────────────────────────────────────────
async def _simple_action(account_id, instance_id: str, action: str, request: Request,
                         db: AsyncSession, user: User) -> dict:
    acct = await _account(account_id, user, db)
    ad = _adapter(acct)
    try:
        live = await _run(ad.get, instance_id)
        if live is None:
            raise HTTPException(status_code=404,
                                detail="That server is not in this cloud account any more.")
        await _run(ad.act, instance_id, action)
    except CloudError as exc:
        raise _fail(exc) from exc

    await audit_service.audit(db, user, f"cloud.{action}",
                              target_type="cloud_account", target_id=acct.id,
                              meta={"provider": acct.provider, "name": live.name,
                                    "instance_id": instance_id}, request=request)
    words = {cl.REBOOT: "Restarting", cl.POWER_ON: "Starting", cl.POWER_OFF: "Shutting down"}
    note = ("" if action != cl.POWER_OFF else
            " A server that is switched off still costs the same — delete it to stop paying.")
    return {"ok": True, "message": f"{words[action]} {live.name}.{note}"}


# Three named routes rather than one `{action}` catch-all. A catch-all sits at the same
# depth as `/resize` and `/destroy` and, registered first, silently swallows them — which
# it did, making the two most consequential routes in this file unreachable. Naming them
# removes the ordering dependency entirely instead of relying on remembering it.
@router.post("/instances/{instance_id}/reboot")
async def reboot(account_id: uuid.UUID, instance_id: str, request: Request,
                 db: DBDep, current_user: VerifiedUser) -> dict:
    """Restart a server."""
    return await _simple_action(account_id, instance_id, cl.REBOOT, request, db, current_user)


@router.post("/instances/{instance_id}/power-on")
async def power_on(account_id: uuid.UUID, instance_id: str, request: Request,
                   db: DBDep, current_user: VerifiedUser) -> dict:
    """Switch a stopped server back on."""
    return await _simple_action(account_id, instance_id, cl.POWER_ON, request, db, current_user)


@router.post("/instances/{instance_id}/power-off")
async def power_off(account_id: uuid.UUID, instance_id: str, request: Request,
                    db: DBDep, current_user: VerifiedUser) -> dict:
    """Shut a server down, asking its operating system first."""
    return await _simple_action(account_id, instance_id, cl.POWER_OFF, request, db, current_user)


@router.post("/instances/{instance_id}/resize/preview")
async def preview_resize(account_id: uuid.UUID, instance_id: str, body: ResizeBody,
                         db: DBDep, current_user: CurrentUser) -> dict:
    """What this resize would do — shown before anything is applied."""
    acct = await _account(account_id, current_user, db)
    ad = _adapter(acct)
    try:
        live = await _run(ad.get, instance_id)
        if live is None:
            raise HTTPException(status_code=404, detail="That server is gone.")
        cat = await _run(ad.catalogue)
    except CloudError as exc:
        raise _fail(exc) from exc
    try:
        plan = cl.resize_plan(cl.size_by_slug(cat, live.instance_type or ""),
                              cl.size_by_slug(cat, body.size), grow_disk=body.grow_disk)
    except cl.InvalidRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"plan": plan.__dict__, "name": live.name, "state": live.state}


@router.post("/instances/{instance_id}/resize")
async def resize(account_id: uuid.UUID, instance_id: str, body: ResizeBody, request: Request,
                 db: DBDep, current_user: VerifiedUser) -> dict:
    acct = await _account(account_id, current_user, db)
    ad = _adapter(acct)
    try:
        live = await _run(ad.get, instance_id)
        if live is None:
            raise HTTPException(status_code=404, detail="That server is gone.")
        cat = await _run(ad.catalogue)
    except CloudError as exc:
        raise _fail(exc) from exc

    try:
        # Re-decided here from the state the provider just reported, not from whatever
        # the browser previewed — the preview may be minutes old and the size may have
        # changed under it.
        plan = cl.resize_plan(cl.size_by_slug(cat, live.instance_type or ""),
                              cl.size_by_slug(cat, body.size), grow_disk=body.grow_disk)
    except cl.InvalidRequest as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if live.state not in ("off", "stopped"):
        raise HTTPException(
            status_code=409,
            detail=(f"{live.name} has to be switched off before it can be resized — both "
                    "providers require it. Shut it down first, then resize."))

    try:
        await _run(ad.act, instance_id, cl.RESIZE, size=body.size, grow_disk=body.grow_disk)
    except CloudError as exc:
        raise _fail(exc) from exc

    await audit_service.audit(
        db, current_user, "cloud.resize", target_type="cloud_account", target_id=acct.id,
        meta={"provider": acct.provider, "name": live.name, "instance_id": instance_id,
              "from": plan.from_size, "to": plan.to_size,
              "permanent": plan.grows_disk}, request=request)
    return {"ok": True, "plan": plan.__dict__,
            "message": f"Resizing {live.name}. Start it again when it finishes."}


@router.post("/instances/{instance_id}/destroy")
async def destroy(account_id: uuid.UUID, instance_id: str, body: DestroyBody,
                  request: Request, db: DBDep, current_user: VerifiedUser) -> dict:
    """Delete a server permanently. Its disk goes with it."""
    acct = await _account(account_id, current_user, db)
    ad = _adapter(acct)
    try:
        live = await _run(ad.get, instance_id)
    except CloudError as exc:
        raise _fail(exc) from exc

    try:
        cl.check_destroy(live, body.confirm_name)
    except cl.WouldDestroyWrongServer as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        await _run(ad.destroy, instance_id)
    except CloudError as exc:
        raise _fail(exc) from exc

    # An asset row pointing at a machine that no longer exists would keep being scanned,
    # monitored and reported on — and would show as "offline" forever with no explanation.
    linked = (await db.execute(
        select(Server).where(Server.cloud_account_id == acct.id,
                             Server.cloud_instance_id == instance_id)
    )).scalars().all()
    for s in linked:
        await db.delete(s)
    if linked:
        await db.commit()

    await audit_service.audit(
        db, current_user, "cloud.destroy", target_type="cloud_account", target_id=acct.id,
        meta={"provider": acct.provider, "name": live.name, "instance_id": instance_id,
              "removed_assets": len(linked)}, request=request)
    logger.warning("Destroyed %s instance %s (%s) for user %s", acct.provider,
                   instance_id, live.name, current_user.id)
    extra = (f" Its entry in ServerAlly was removed too." if linked else "")
    return {"ok": True, "message": f"{live.name} has been deleted.{extra}"}
