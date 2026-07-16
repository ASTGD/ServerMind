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
from sqlalchemy import func, or_, select
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
        # Record the email IN the event: an audit trail that can only name its subject by
        # joining a live row stops being able to answer "did billing land for X?" the
        # moment that row is gone.
        meta={"reference": body.reference, "created": created, "email": email},
        request=request,
    )
    return SetPlanResponse(email=email, plan=plan, created=created, claim_url=claim_url)


# ── Reconciliation ───────────────────────────────────────────────────────────
# Renewal is SILENCE (docs/SAAS-LAUNCH-PLAN.md §3.3): a paying customer's renewal calls
# nothing, because nothing needs to change. The cost is that a MISSED event — module
# error, this API down during the WHMCS cron, a stopped cron — leaves a plan wrong
# forever, and silence means both "fine" and "broken". The dangerous direction is the
# quiet one: a missed suspend leaves a non-paying customer on Pro and nobody complains.
#
# So billing pushes the full truth here nightly and we make reality match. This is the
# ONLY thing that can detect drift; without it the integration has no failure detection.

# A reconcile can mass-downgrade every customer, so a bad list is the real risk — a
# WHMCS query that silently truncates or returns nothing must not empty the whole
# customer base. These bound the blast radius; `force` is the deliberate human override.
MAX_DOWNGRADE_RATIO = 0.2   # >20% of Pro users churning in one night isn't churn, it's a bug
MIN_DOWNGRADE_FLOOR = 3     # ...but always allow a few, so a small base can churn normally


class ReconcileRequest(BaseModel):
    # Every email the billing system considers an ACTIVE paying customer right now.
    active_pro_emails: list[EmailStr]
    # Report what WOULD change without changing it — safe to run any time.
    dry_run: bool = False
    # Override the blast-radius guard (and allow an empty list). Deliberate and audited.
    force: bool = False


class ReconcileResponse(BaseModel):
    dry_run: bool
    upgraded: list[str]
    downgraded: list[str]
    # In the billing list but has no ServerAlly account — reported, never created.
    # Provisioning stays with CreateAccount, which is the only event that can email
    # the customer their claim link.
    unknown: list[str]
    unchanged: int


@router.post("/reconcile", response_model=ReconcileResponse, dependencies=[Depends(_require_key)])
async def reconcile(
    body: ReconcileRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ReconcileResponse:
    """Make plans match the billing system's list of active paying customers.

    Idempotent, and never deletes: a downgrade only shrinks the two meters, exactly as
    a suspend does. Admin accounts are never downgraded — internal staff are Pro by
    hand and do not exist in WHMCS, so a nightly reconcile would otherwise demote the
    team every night.
    """
    active = {str(e).strip().lower() for e in body.active_pro_emails}

    if not active and not body.force:
        # An empty list almost certainly means a broken billing query, not "we lost
        # every customer overnight". Refuse rather than empty the customer base.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Refusing to reconcile against an empty active list — this would "
                   "downgrade every customer. Pass force=true if that is genuinely intended.",
        )

    # Only two groups can change: current Pro users, and anyone named in the list.
    rows = (
        await db.execute(
            select(User).where(or_(User.plan == "pro", func.lower(User.email).in_(active)))
        )
    ).scalars().all()

    total_pro = sum(1 for u in rows if (u.plan or "free").lower() == "pro")

    to_upgrade: list[User] = []
    to_downgrade: list[User] = []
    unchanged = 0
    for u in rows:
        plan = (u.plan or "free").lower()
        is_paying = u.email.lower() in active
        if is_paying and plan != "pro":
            to_upgrade.append(u)          # billing says paying, we had them on free
        elif not is_paying and plan == "pro" and not u.is_admin:
            to_downgrade.append(u)        # the quiet failure: Pro but not paying
        else:
            unchanged += 1

    limit = max(MIN_DOWNGRADE_FLOOR, int(total_pro * MAX_DOWNGRADE_RATIO))
    if len(to_downgrade) > limit and not body.force:
        # Loud on purpose. A silent 200 here would recreate the very failure this
        # endpoint exists to catch — the billing cron must surface a non-2xx.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Refusing to reconcile — too many downgrades at once.",
                "would_downgrade": len(to_downgrade),
                "allowed_without_force": limit,
                "total_pro": total_pro,
                "hint": "This usually means the billing list is truncated or wrong. "
                        "Verify it, then re-send with force=true if it is correct.",
            },
        )

    up = sorted(u.email for u in to_upgrade)
    down = sorted(u.email for u in to_downgrade)
    unknown = sorted(active - {u.email.lower() for u in rows})

    if not body.dry_run and (to_upgrade or to_downgrade):
        for u in to_upgrade:
            u.plan = "pro"
        for u in to_downgrade:
            u.plan = "free"
        await db.commit()
        for u in to_upgrade + to_downgrade:
            await audit_service.audit(
                db, u, "entitlement.reconcile",
                target_type="plan", target_id=u.plan,
                meta={"forced": body.force, "email": u.email}, request=request,
            )
        logger.info(
            "entitlement reconcile: %d upgraded, %d downgraded, %d unknown",
            len(up), len(down), len(unknown),
        )

    return ReconcileResponse(
        dry_run=body.dry_run, upgraded=up, downgraded=down,
        unknown=unknown, unchanged=unchanged,
    )


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
