"""Entitlement API — the billing system's door into ServerAlly (docs/WHMCS-INTEGRATION.md).

Called by the WHMCS provisioning module (or any future billing system) to set a
customer's plan when billing events fire: order paid → pro, overdue/suspended → free,
unsuspended → pro, cancelled → free. Per pricing v2 ("open features, two meters") a
plan is just two numbers, so this API only ever moves `users.plan` — it never deletes
anything and never touches the customer's servers or data.

Auth: the shared secret in the X-Entitlement-Key header (settings.ENTITLEMENT_API_KEY;
empty = the whole API is disabled). Every change is audit-logged.

New customers: if the email has no ServerAlly account yet, one is created (verified —
the billing system knows the email is real) with an unusable random password, and a
one-time CLAIM link is returned; the billing side emails it to the customer, who sets
their password there. Claim tokens die on first use (token_version bump).
"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services import audit_service, metering_service
from app.services.auth_service import create_claim_token, hash_password
from app.services.entitlements import PLANS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/entitlements", tags=["entitlements"])


def _require_key(x_entitlement_key: str = Header(default="")) -> None:
    if not settings.ENTITLEMENT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Entitlement API is not configured (ENTITLEMENT_API_KEY is empty).",
        )
    if not secrets.compare_digest(x_entitlement_key, settings.ENTITLEMENT_API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad entitlement key")


class SetPlanRequest(BaseModel):
    email: EmailStr
    plan: str  # 'free' | 'pro'
    # Free-text reference from the billing side (e.g. WHMCS service id) — audit only.
    reference: str | None = None


class SetPlanResponse(BaseModel):
    email: str
    plan: str
    created: bool
    # Present only when a new account was created — the billing side emails this link.
    claim_url: str | None = None


@router.get("/ping", dependencies=[Depends(_require_key)])
async def ping() -> dict:
    """Connection test for the billing module."""
    return {"ok": True, "app": settings.APP_NAME}


@router.post("/set", response_model=SetPlanResponse, dependencies=[Depends(_require_key)])
async def set_plan(
    body: SetPlanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SetPlanResponse:
    """Set (or provision) a customer's plan. Idempotent — safe to call repeatedly."""
    plan = body.plan.strip().lower()
    if plan not in PLANS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown plan '{body.plan}' — expected one of: {', '.join(PLANS)}",
        )

    email = body.email.strip().lower()
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()

    created = False
    claim_url: str | None = None
    if user is None:
        # Billing-provisioned account: verified email (billing knows it's real), an
        # unusable random password, and a one-time claim link to set the real one.
        user = User(
            email=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            is_verified=True,
            plan=plan,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        created = True
        base = (settings.APP_BASE_URL or "").rstrip("/")
        token = create_claim_token(str(user.id), user.token_version)
        claim_url = f"{base}/claim?token={token}" if base else f"/claim?token={token}"
        logger.info("entitlement: provisioned new account %s (plan=%s)", email, plan)
    else:
        user.plan = plan
        await db.commit()
        logger.info("entitlement: %s -> plan=%s", email, plan)

    await audit_service.audit(
        db, user, "entitlement.set",
        target_type="plan", target_id=plan,
        meta={"reference": body.reference, "created": created},
        request=request,
    )
    return SetPlanResponse(email=email, plan=plan, created=created, claim_url=claim_url)


class EntitlementStatus(BaseModel):
    email: str
    plan: str
    actions_used: int
    actions_limit: int
    servers_used: int
    servers_limit: int


@router.get("/{email}", response_model=EntitlementStatus, dependencies=[Depends(_require_key)])
async def get_status(
    email: str,
    db: AsyncSession = Depends(get_db),
) -> EntitlementStatus:
    """Current plan + both meters for a customer (shown in the WHMCS client area)."""
    user = (
        await db.execute(select(User).where(User.email == email.strip().lower()))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account for this email")
    g = await metering_service.gate(db, user)
    sg = await metering_service.servers_gate(db, user)
    return EntitlementStatus(
        email=user.email,
        plan=(user.plan or "free"),
        actions_used=g.used,
        actions_limit=g.limit,
        servers_used=sg.used,
        servers_limit=sg.limit,
    )
