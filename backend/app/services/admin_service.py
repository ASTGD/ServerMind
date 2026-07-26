"""Operator console — the support/ops view (docs/SAAS-LAUNCH-PLAN.md §5).

NOT a billing admin. WHMCS owns customers, orders, invoices and revenue; this answers
only the questions WHMCS structurally cannot, because it knows nothing about servers,
Ally, or what the AI actually costs us:

  1. "A customer says Ally is broken."   -> their servers, missions, errors
  2. "Are we making money on them?"      -> their AI cost vs their plan
  3. "Is the platform healthy?"          -> signups, active users, our AI spend
  4. "Why is this payer still on Free?"  -> did the entitlement call land?

READ-ONLY BY CONSTRUCTION. Everything here is a SELECT. There is deliberately no path to
decrypt a credential, run a command as a customer, read chat content, or delete data —
these are properties of the design, not policies to remember. The moment an admin
endpoint can decrypt a credential, our breach radius becomes every customer's production
server. `plan` is a read-only MIRROR of WHMCS's decision; it is never edited here.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage import AiUsage
from app.models.audit_log import AuditLog
from app.models.command_log import CommandLog
from app.models.mission import Mission
from app.models.server import Server
from app.models.user import User
from app.services import metering_service
from app.services.entitlements import PLANS, limits_for_plan

# "Active" = did anything with Ally in the last 7 days. Cheap and honest: it comes from
# the ledger we already write, rather than a new last_seen column to keep in sync.
ACTIVE_DAYS = 7


def _limits(plan: str | None) -> dict:
    """Delegates, so the console shows the limits that are actually ENFORCED.

    This used to reimplement the lookup and fall back to Free, which meant an operator
    investigating a broken plan would be shown Free limits while the app was really granting
    the generous ones — the console lying about the very thing it exists to reveal.
    """
    return limits_for_plan(plan)


async def overview(db: AsyncSession) -> dict:
    """The business at a glance. Revenue lives in WHMCS; COST lives here — so this
    deliberately reports cost only. Estimated margin needs a price, which is WHMCS's
    fact, not ours (see SAAS-LAUNCH-PLAN §5.1)."""
    period = metering_service.period_start()
    active_since = datetime.now(timezone.utc) - timedelta(days=ACTIVE_DAYS)

    # Label it and group by the label: two inline copies of the same expression render
    # as distinct expressions and Postgres rejects the GROUP BY.
    plan_col = func.lower(func.coalesce(User.plan, "free")).label("plan")
    by_plan = dict(
        (await db.execute(select(plan_col, func.count()).group_by(plan_col))).all()
    )

    new_this_period = (
        await db.execute(select(func.count()).select_from(User).where(User.created_at >= period))
    ).scalar_one()

    active = (
        await db.execute(
            select(func.count(func.distinct(AiUsage.user_id))).where(AiUsage.created_at >= active_since)
        )
    ).scalar_one()

    servers_total = (await db.execute(select(func.count()).select_from(Server))).scalar_one()

    cost, actions, calls = (
        await db.execute(
            select(
                func.coalesce(func.sum(AiUsage.cost_usd), 0),
                func.coalesce(func.sum(AiUsage.actions), 0),
                func.count(),
            ).where(AiUsage.created_at >= period)
        )
    ).one()

    errors = (
        await db.execute(
            select(func.count())
            .select_from(AiUsage)
            .where(AiUsage.created_at >= period, AiUsage.status != "ok")
        )
    ).scalar_one()

    return {
        "period_start": period.isoformat(),
        "users_total": sum(by_plan.values()),
        "users_by_plan": by_plan,
        "users_new_this_period": new_this_period,
        "users_active_7d": active,
        "servers_total": servers_total,
        "ai_cost_usd": float(cost or 0),
        "ai_actions": int(actions or 0),
        "ai_calls": calls,
        "ai_errors": errors,
    }


async def list_users(db: AsyncSession, *, limit: int = 100, q: str | None = None) -> list[dict]:
    """Every user with their plan, both meters and their AI cost this period.

    Batched: one grouped query for usage and one for server counts, then joined in
    Python — a per-user gate() call would be an N+1 across the whole customer base.
    """
    period = metering_service.period_start()

    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    if q:
        stmt = stmt.where(func.lower(User.email).like(f"%{q.strip().lower()}%"))
    users = (await db.execute(stmt)).scalars().all()
    if not users:
        return []
    ids = [u.id for u in users]

    usage = dict(
        (uid, (int(acts or 0), float(cost or 0)))
        for uid, acts, cost in (
            await db.execute(
                select(
                    AiUsage.user_id,
                    func.coalesce(func.sum(AiUsage.actions), 0),
                    func.coalesce(func.sum(AiUsage.cost_usd), 0),
                )
                .where(AiUsage.user_id.in_(ids), AiUsage.created_at >= period)
                .group_by(AiUsage.user_id)
            )
        ).all()
    )
    servers = dict(
        (
            await db.execute(
                select(Server.user_id, func.count())
                .where(Server.user_id.in_(ids))
                .group_by(Server.user_id)
            )
        ).all()
    )

    out = []
    for u in users:
        lim = _limits(u.plan)
        acts, cost = usage.get(u.id, (0, 0.0))
        out.append(
            {
                "id": str(u.id),
                "email": u.email,
                "name": u.name,
                "plan": (u.plan or "free").lower(),
                "is_admin": u.is_admin,
                "is_active": u.is_active,
                "is_verified": u.is_verified,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "actions_used": acts,
                "actions_limit": lim["actions_per_month"],
                "servers_used": servers.get(u.id, 0),
                "servers_limit": lim["max_servers"],
                "ai_cost_usd": cost,
            }
        )
    return out


async def user_detail(db: AsyncSession, user_id: uuid.UUID) -> dict | None:
    """The support screen: enough to diagnose "Ally is broken for me" without ever
    asking the customer for their password — and without exposing a single credential.
    """
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        return None

    period = metering_service.period_start()
    lim = _limits(user.plan)

    acts, cost = (
        await db.execute(
            select(
                func.coalesce(func.sum(AiUsage.actions), 0),
                func.coalesce(func.sum(AiUsage.cost_usd), 0),
            ).where(AiUsage.user_id == user.id, AiUsage.created_at >= period)
        )
    ).one()

    # Their servers — identity and health only. encrypted_cred is never selected, and
    # there is no endpoint that could decrypt it.
    servers = [
        {
            "id": str(s.id),
            "name": s.name,
            "host": s.host,
            "connection_type": s.connection_type,
            "os_type": s.os_type,
            "status": s.status,
            "last_seen": s.last_seen.isoformat() if s.last_seen else None,
        }
        for s in (
            await db.execute(
                select(Server).where(Server.user_id == user.id).order_by(Server.created_at.desc())
            )
        ).scalars().all()
    ]

    missions = [
        {
            "id": str(m.id),
            "goal": m.goal[:120],
            "server_name": m.server_name,
            "status": m.status,
            "verified": m.verified,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in (
            await db.execute(
                select(Mission)
                .where(Mission.user_id == user.id)
                .order_by(Mission.created_at.desc())
                .limit(10)
            )
        ).scalars().all()
    ]

    # Recent trouble — the "what went wrong for them" list. user_input is the customer's
    # OWN words (never Ally's output or command results), which is what a support
    # operator needs to understand the request that failed.
    problems = [
        {
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "status": c.status,
            "risk_level": c.risk_level,
            "request": (c.user_input or "")[:120],
        }
        for c in (
            await db.execute(
                select(CommandLog)
                .where(CommandLog.user_id == user.id, CommandLog.status.in_(("failed", "blocked")))
                .order_by(CommandLog.created_at.desc())
                .limit(10)
            )
        ).scalars().all()
    ]

    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "plan": (user.plan or "free").lower(),
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "totp_enabled": user.totp_enabled,
        "preferred_language": user.preferred_language,
        "ally_mode": user.ally_mode,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "actions_used": int(acts or 0),
        "actions_limit": lim["actions_per_month"],
        "servers_used": len(servers),
        "servers_limit": lim["max_servers"],
        "ai_cost_usd": float(cost or 0),
        "servers": servers,
        "missions": missions,
        "problems": problems,
        "entitlements": await entitlement_log(db, limit=20, user_id=user.id),
    }


async def entitlement_log(
    db: AsyncSession, *, limit: int = 100, user_id: uuid.UUID | None = None
) -> list[dict]:
    """"Did billing land?" — every plan change WHMCS drove, from the audit trail we
    already write. This is the only place the WHMCS<->ServerAlly seam is visible, so it
    is where a "customer paid but is still Free" ticket gets answered."""
    stmt = (
        select(AuditLog, User.email)
        .join(User, User.id == AuditLog.user_id, isouter=True)
        .where(AuditLog.action.in_(("entitlement.set", "entitlement.reconcile")))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    return [
        {
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "action": a.action,
            # Prefer the email recorded ON the event; fall back to the joined user. Older
            # rows (and any whose user is gone) only have the join, hence the fallback.
            "email": (a.meta or {}).get("email") or email,
            "plan": a.target_id,
            "reference": (a.meta or {}).get("reference"),
            "created": (a.meta or {}).get("created"),
            "forced": (a.meta or {}).get("forced"),
            "ip": a.ip,
        }
        for (a, email) in (await db.execute(stmt)).all()
    ]
