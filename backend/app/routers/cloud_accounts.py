"""Cloud Accounts router (Assets Phase C) — connect a provider account, discover its
instances, and import them as normal `servers` rows.

Flow: POST (connect + verify the key) → GET {id}/instances (discover) → POST {id}/import
(create asset rows the user then finishes with an SSH key/password). The provider API only
LISTS machines; it never hands over a login, so import always needs the user's own credential.
"""
from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user, require_verified
from app.models.cloud_account import CloudAccount
from app.models.server import Server
from app.models.user import User
from app.schemas.cloud import (
    CloudAccountCreate,
    CloudAccountOut,
    ImportBody,
    ImportResult,
    InstanceOut,
)
from app.services import audit_service, cloud_service, metering_service, server_probe
from app.services.cloud_service import CloudError
from app.services.crypto_service import encrypt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cloud-accounts", tags=["cloud"])


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _resolve_account(account_id: uuid.UUID, user: User, db: AsyncSession) -> CloudAccount:
    """Fetch a cloud account the current user owns (404 otherwise)."""
    account = (
        await db.execute(
            select(CloudAccount).where(
                CloudAccount.id == account_id, CloudAccount.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cloud account not found")
    return account


async def _imported_ids(account: CloudAccount, db: AsyncSession) -> set[str]:
    """Instance IDs already imported from this account (dedupe)."""
    rows = (
        await db.execute(
            select(Server.cloud_instance_id).where(Server.cloud_account_id == account.id)
        )
    ).scalars().all()
    return {r for r in rows if r}


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[CloudAccountOut])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CloudAccount]:
    """List the current user's connected cloud accounts."""
    return list(
        (
            await db.execute(
                select(CloudAccount)
                .where(CloudAccount.user_id == current_user.id)
                .order_by(CloudAccount.created_at.desc())
            )
        ).scalars().all()
    )


@router.post("", response_model=CloudAccountOut, status_code=status.HTTP_201_CREATED)
async def connect_account(
    request: Request,
    body: CloudAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_verified),
) -> CloudAccount:
    """Connect a cloud account. The credential is verified against the provider BEFORE it's
    saved, then stored AES-256-GCM encrypted."""
    provider = body.provider.lower()
    if provider not in cloud_service.SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported cloud provider: {body.provider}",
        )
    # Prove the key works (and has the read permission) before persisting anything.
    try:
        await cloud_service.verify_credential(provider, body.credential)
    except CloudError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    account = CloudAccount(
        user_id=current_user.id,
        provider=provider,
        label=body.label,
        encrypted_credential=encrypt(json.dumps(body.credential)),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)

    await audit_service.audit(
        db, current_user, "cloud.connect",
        target_type="cloud_account", target_id=account.id,
        meta={"provider": provider, "label": account.label}, request=request,
    )
    logger.info("Cloud account %s (%s) connected by user %s", account.id, provider, current_user.id)
    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Disconnect a cloud account. Imported assets are kept (just unlinked)."""
    account = await _resolve_account(account_id, current_user, db)
    await db.delete(account)  # FK is ON DELETE SET NULL — imported servers survive
    await db.commit()
    await audit_service.audit(
        db, current_user, "cloud.disconnect",
        target_type="cloud_account", target_id=account_id, request=request,
    )


# ── Discover + import ──────────────────────────────────────────────────────────

@router.get("/{account_id}/instances", response_model=list[InstanceOut])
async def list_account_instances(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[InstanceOut]:
    """Discover the instances in a connected cloud account (already-imported ones marked)."""
    account = await _resolve_account(account_id, current_user, db)
    try:
        instances = await cloud_service.list_instances(account)
    except CloudError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    imported = await _imported_ids(account, db)
    return [
        InstanceOut(**inst.dict(), already_imported=inst.instance_id in imported)
        for inst in instances
    ]


@router.post("/{account_id}/import", response_model=ImportResult)
async def import_instances(
    account_id: uuid.UUID,
    body: ImportBody,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_verified),
) -> ImportResult:
    """Import selected instances as assets. One SSH username + key/password is applied to the
    whole batch (edit per-asset later). Re-fetches live instance data so we import real
    machines, not a stale/spoofed client payload."""
    account = await _resolve_account(account_id, current_user, db)
    try:
        instances = await cloud_service.list_instances(account)
    except CloudError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    wanted = set(body.instance_ids)
    already = await _imported_ids(account, db)
    selected = [i for i in instances if i.instance_id in wanted]

    # Respect the plan's server cap (meter #2): import up to the remaining allowance.
    sg = await metering_service.servers_gate(db, current_user)
    capacity = (sg.limit - sg.used) if sg.enforced else None

    encrypted = encrypt(body.credential)
    fresh: list[Server] = []
    imported = skipped = 0
    limited = no_address = 0
    for inst in selected:
        if inst.instance_id in already:
            skipped += 1
            continue
        host = inst.private_ip if body.use_private_ip else (inst.public_ip or inst.private_ip)
        if not host:
            no_address += 1
            continue
        if capacity is not None and imported >= capacity:
            limited += 1
            continue
        t = cloud_service.transport_defaults(inst.os)
        # The label comes from the SAME function the manual add uses, and the probe below
        # corrects it if the machine turns out to run a control panel. Hardcoding it here is
        # what filed a CyberPanel EC2 as a plain VPS while the identical machine added by
        # hand was filed as a panel.
        row = Server(
            user_id=current_user.id,
            name=inst.name or inst.instance_id,
            host=host,
            port=t["port"],
            username=body.username,
            auth_type=body.auth_type,
            connection_type=t["connection_type"],
            category=server_probe.infer_category(t["connection_type"], None),
            cloud_account_id=account.id,
            cloud_instance_id=inst.instance_id,
            encrypted_cred=encrypted,
            shell=t["shell"],
            # The provider's coarse guess ("linux"). The probe replaces it with what the
            # machine actually says, and leaves this in place if it cannot reach it.
            os_type=inst.os,
            tags=[account.provider],
        )
        db.add(row)
        fresh.append(row)
        imported += 1

    await db.commit()

    # Look at what we just imported — the same probe the manual add runs. Until it lands,
    # these rows have no host-key pin, and `ssh_service` skips verification entirely when
    # the pin is NULL. In the background because fifty machines is minutes, not a request.
    if fresh:
        background.add_task(server_probe.probe_many, [r.id for r in fresh])

    details = []
    if no_address:
        details.append(f"{no_address} had no reachable IP")
    if limited:
        details.append(f"{limited} skipped — server plan limit reached")
    await audit_service.audit(
        db, current_user, "cloud.import",
        target_type="cloud_account", target_id=account.id,
        meta={"imported": imported, "skipped": skipped}, request=request,
    )
    logger.info("Imported %s instance(s) from cloud account %s (user %s)",
                imported, account.id, current_user.id)
    return ImportResult(
        imported=imported,
        skipped=skipped + no_address,
        limited=bool(limited),
        detail="; ".join(details) or None,
    )
