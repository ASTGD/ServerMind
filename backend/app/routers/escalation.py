"""On-call escalation — policies, incidents, acknowledging, and provider credentials.

One endpoint here is **unauthenticated**: ``POST /api/public/ack/{token}``, the link inside
a page. It has to be, because the person it wakes may be reading a text message on a phone
that has never logged in. So it is bounded as tightly as possible:

- the token reaches exactly one incident and can only acknowledge it — it is not a login,
  carries no session, and grants nothing else;
- it is 256 random bits, so it cannot be guessed;
- it is rate-limited, like the public status page.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.escalation import (
    CHANNELS, SEVERITIES, STATUS_ACKNOWLEDGED, STATUS_OPEN,
    EscalationPolicy, EscalationStep, Incident, NotificationProvider,
)
from app.models.server import Server
from app.models.user import User
from app.services import escalation_service as esc
from app.services import entitlements, incident_service, paging_service
from app.services.rate_limit_service import limiter

router = APIRouter(prefix="/api", tags=["escalation"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Schemas ──────────────────────────────────────────────────────────────────

class StepIn(BaseModel):
    after_minutes: int = Field(default=0, ge=0, le=60 * 24 * 7)
    channel: str
    target: str = Field(min_length=1, max_length=500)
    label: str | None = Field(default=None, max_length=120)


class PolicyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    min_severity: str = "high"
    repeat_minutes: int = Field(default=15, ge=1, le=60 * 24)
    # Bounded at the API too, not only inside the state machine — the number a user types is
    # also the number the UI promises them ("at most N messages"), so it must be honest.
    max_repeats: int = Field(default=3, ge=0, le=esc.MAX_REPEATS_CEILING)
    is_default: bool = False
    is_active: bool = True
    steps: list[StepIn] = Field(default_factory=list)


class PolicyPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    min_severity: str | None = None
    repeat_minutes: int | None = Field(default=None, ge=1, le=60 * 24)
    max_repeats: int | None = Field(default=None, ge=0, le=esc.MAX_REPEATS_CEILING)
    is_default: bool | None = None
    is_active: bool | None = None
    steps: list[StepIn] | None = None


class ProviderIn(BaseModel):
    # Twilio
    account_sid: str | None = None
    auth_token: str | None = None
    from_number: str | None = None
    # Telegram
    bot_token: str | None = None
    monthly_limit: int | None = Field(default=None, ge=0, le=10_000)


# Channels that cost real money per message, and are therefore a paid feature.
_PAID_CHANNELS = ("sms", "telegram")


def _validate_channel(channel: str, user: User | None = None) -> None:
    """Check the channel exists, and that the plan includes it.

    Gated here rather than only at provider setup: a step pointing at a channel the account
    cannot use would fail at 3am, which is the worst possible moment to discover a plan limit.
    """
    if user is not None and channel in _PAID_CHANNELS:
        entitlements.require(user, entitlements.SMS_ALERTS)
    if channel not in CHANNELS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown way to reach someone: '{channel}'. Choose one of "
                   f"{', '.join(CHANNELS)}.",
        )


def _validate_severity(severity: str | None) -> None:
    if severity is not None and severity not in SEVERITIES:
        raise HTTPException(
            status_code=422,
            detail=f"Severity must be one of {', '.join(SEVERITIES)}.",
        )


async def _get_policy(policy_id: str, user: User, db: AsyncSession) -> EscalationPolicy:
    try:
        pid = uuid.UUID(policy_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy = (await db.execute(
        select(EscalationPolicy).where(
            EscalationPolicy.id == pid, EscalationPolicy.user_id == user.id
        )
    )).scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


async def _steps_rows(db: AsyncSession, policy: EscalationPolicy) -> list[EscalationStep]:
    return list((await db.execute(
        select(EscalationStep).where(EscalationStep.policy_id == policy.id)
        .order_by(EscalationStep.position)
    )).scalars().all())


async def _policy_out(db: AsyncSession, policy: EscalationPolicy) -> dict:
    rows = await _steps_rows(db, policy)
    steps = [esc.Step(r.after_minutes, r.channel, r.target, r.label) for r in rows]
    return {
        "id": str(policy.id),
        "name": policy.name,
        "min_severity": policy.min_severity,
        "repeat_minutes": policy.repeat_minutes,
        "max_repeats": policy.max_repeats,
        "is_default": policy.is_default,
        "is_active": policy.is_active,
        "steps": [
            {"after_minutes": r.after_minutes, "channel": r.channel,
             "target": r.target, "label": r.label}
            for r in rows
        ],
        # The ladder in sentences, and the honest ceiling on how many messages it can send.
        "summary": esc.describe(steps, policy.repeat_minutes, policy.max_repeats),
        "max_notifications": esc.total_notifications(steps, policy.max_repeats),
        "created_at": policy.created_at.isoformat() if policy.created_at else None,
    }


async def _replace_steps(db: AsyncSession, policy: EscalationPolicy,
                         steps: list[StepIn], user: User) -> None:
    await db.execute(delete(EscalationStep).where(EscalationStep.policy_id == policy.id))
    for position, step in enumerate(steps[:esc.MAX_STEPS]):
        _validate_channel(step.channel, user)
        db.add(EscalationStep(
            policy_id=policy.id, position=position,
            after_minutes=step.after_minutes, channel=step.channel,
            target=step.target.strip(), label=(step.label or "").strip() or None,
        ))


async def _clear_other_defaults(db: AsyncSession, user: User, keep: uuid.UUID) -> None:
    """Exactly one default. Two defaults would make which policy pages you a coin flip."""
    await db.execute(
        update(EscalationPolicy)
        .where(EscalationPolicy.user_id == user.id, EscalationPolicy.id != keep)
        .values(is_default=False)
    )


# ── Policies ─────────────────────────────────────────────────────────────────

@router.get("/escalation/policies")
async def list_policies(db: DBDep, current_user: CurrentUser) -> list[dict]:
    policies = (await db.execute(
        select(EscalationPolicy).where(EscalationPolicy.user_id == current_user.id)
        .order_by(EscalationPolicy.is_default.desc(), EscalationPolicy.created_at)
    )).scalars().all()
    return [await _policy_out(db, p) for p in policies]


@router.post("/escalation/policies", status_code=201)
async def create_policy(body: PolicyIn, db: DBDep, current_user: CurrentUser) -> dict:
    _validate_severity(body.min_severity)
    policy = EscalationPolicy(
        user_id=current_user.id, name=body.name.strip(),
        min_severity=body.min_severity, repeat_minutes=body.repeat_minutes,
        max_repeats=body.max_repeats, is_default=body.is_default, is_active=body.is_active,
    )
    db.add(policy)
    await db.flush()
    await _replace_steps(db, policy, body.steps, current_user)
    if body.is_default:
        await _clear_other_defaults(db, current_user, policy.id)
    await db.commit()
    await db.refresh(policy)
    return await _policy_out(db, policy)


@router.put("/escalation/policies/{policy_id}")
async def update_policy(policy_id: str, body: PolicyPatch, db: DBDep, current_user: CurrentUser) -> dict:
    policy = await _get_policy(policy_id, current_user, db)
    data = body.model_dump(exclude_unset=True)
    _validate_severity(data.get("min_severity"))

    for field in ("name", "min_severity", "repeat_minutes", "max_repeats", "is_default", "is_active"):
        if field in data and data[field] is not None:
            setattr(policy, field, data[field].strip() if field == "name" else data[field])
    if body.steps is not None:
        await _replace_steps(db, policy, body.steps, current_user)
    if data.get("is_default"):
        await _clear_other_defaults(db, current_user, policy.id)

    await db.commit()
    await db.refresh(policy)
    return await _policy_out(db, policy)


@router.delete("/escalation/policies/{policy_id}", status_code=204)
async def delete_policy(policy_id: str, db: DBDep, current_user: CurrentUser) -> None:
    policy = await _get_policy(policy_id, current_user, db)
    await db.delete(policy)
    await db.commit()


@router.post("/escalation/policies/{policy_id}/preview")
async def preview_policy(policy_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Send a test page through the FIRST step, so the user learns their number is wrong
    now rather than during an outage."""
    policy = await _get_policy(policy_id, current_user, db)
    rows = await _steps_rows(db, policy)
    ladder = esc.ordered_steps([esc.Step(r.after_minutes, r.channel, r.target, r.label) for r in rows])
    if not ladder:
        raise HTTPException(status_code=422, detail="Add a step first, then test it.")

    first = ladder[0]
    ok, detail = await paging_service.deliver(
        db, current_user.id, first.channel, first.target,
        "ServerAlly test page",
        "This is a test of your on-call policy. A real alert would name the server and "
        "include a link to stop the alerts.",
    )
    if not ok:
        raise HTTPException(status_code=502, detail=detail)
    return {"sent": True, "channel": first.channel, "to": first.target}


# ── Incidents ────────────────────────────────────────────────────────────────

@router.get("/incidents")
async def list_incidents(
    db: DBDep, current_user: CurrentUser,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    query = select(Incident).where(Incident.user_id == current_user.id)
    if status == "active":
        # What the UI opens on: anything not yet resolved.
        query = query.where(Incident.status.in_([STATUS_OPEN, STATUS_ACKNOWLEDGED]))
    elif status:
        query = query.where(Incident.status == status)
    rows = (await db.execute(
        query.order_by(Incident.created_at.desc()).limit(limit)
    )).scalars().all()

    names: dict[uuid.UUID, str] = {}
    ids = {r.server_id for r in rows if r.server_id}
    if ids:
        names = {
            s.id: s.name for s in (await db.execute(
                select(Server).where(Server.id.in_(ids))
            )).scalars().all()
        }
    return [
        incident_service.serialize(r, server_name=names.get(r.server_id) if r.server_id else None)
        for r in rows
    ]


async def _get_incident(incident_id: str, user: User, db: AsyncSession) -> Incident:
    try:
        iid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident = (await db.execute(
        select(Incident).where(Incident.id == iid, Incident.user_id == user.id)
    )).scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    incident = await _get_incident(incident_id, current_user, db)
    await incident_service.acknowledge(db, incident, by=current_user.name or current_user.email)
    return incident_service.serialize(incident)


@router.post("/incidents/{incident_id}/resolve")
async def resolve_incident(incident_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    incident = await _get_incident(incident_id, current_user, db)
    await incident_service.resolve(
        db, incident, auto=False, by=current_user.name or current_user.email
    )
    return incident_service.serialize(incident)


# ── The acknowledge link (public) ────────────────────────────────────────────

@router.post("/public/ack/{token}")
@limiter.limit("30/minute")
async def acknowledge_by_link(token: str, request: Request, db: DBDep) -> dict:
    """Acknowledge from the link in a page. No authentication — the person being woken up
    may be on a phone that has never signed in.

    The response DOES distinguish a valid token from an unknown one, deliberately: someone
    woken at 3am needs to see that the alerts actually stopped. That is safe because the
    protection here is entropy, not ambiguity — the token is 256 random bits, so there is
    nothing to probe for, and the endpoint is rate-limited on top. It is also idempotent:
    refreshing the page re-confirms rather than reporting a failure.
    """
    incident = await incident_service.acknowledge_by_token(db, token)
    if incident is None:
        return {"acknowledged": False,
                "message": "This link is no longer active. The alert may already be handled."}
    return {
        "acknowledged": True,
        "title": incident.title,
        "status": incident.status,
        "message": "Thanks — we've stopped the alerts for this one.",
    }


# ── Provider credentials ─────────────────────────────────────────────────────

@router.get("/escalation/providers")
async def list_providers(db: DBDep, current_user: CurrentUser) -> list[dict]:
    """What is configured, and how much of the SMS budget is left. Never the credentials."""
    out = []
    for name in ("twilio", "telegram"):
        row = await paging_service.get_provider(db, current_user.id, name)
        out.append(paging_service.public_provider(row, name))
    return out


@router.put("/escalation/providers/{provider}")
async def set_provider(
    provider: str, body: ProviderIn, db: DBDep, current_user: CurrentUser
) -> dict:
    """Store provider credentials, encrypted. Returns only the public view."""
    entitlements.require(current_user, entitlements.SMS_ALERTS)
    if provider not in ("twilio", "telegram"):
        raise HTTPException(status_code=422, detail=f"Unknown provider '{provider}'.")

    if provider == "twilio":
        if not (body.account_sid and body.auth_token and body.from_number):
            raise HTTPException(
                status_code=422,
                detail="Twilio needs an Account SID, an Auth Token and a 'from' number.",
            )
        config = {"account_sid": body.account_sid.strip(),
                  "auth_token": body.auth_token.strip(),
                  "from_number": body.from_number.strip()}
    else:
        if not body.bot_token:
            raise HTTPException(status_code=422, detail="Telegram needs a bot token.")
        config = {"bot_token": body.bot_token.strip()}

    row = await paging_service.get_provider(db, current_user.id, provider)
    if row is None:
        row = NotificationProvider(
            user_id=current_user.id, provider=provider,
            encrypted_config=paging_service.encode_config(config),
        )
        db.add(row)
    else:
        row.encrypted_config = paging_service.encode_config(config)
        # New credentials are unproven until a test send succeeds.
        row.verified_at = None
    if body.monthly_limit is not None:
        row.monthly_limit = body.monthly_limit

    await db.commit()
    await db.refresh(row)
    return paging_service.public_provider(row, provider)


@router.delete("/escalation/providers/{provider}", status_code=204)
async def delete_provider(provider: str, db: DBDep, current_user: CurrentUser) -> None:
    row = await paging_service.get_provider(db, current_user.id, provider)
    if row is not None:
        await db.delete(row)
        await db.commit()


@router.post("/escalation/providers/{provider}/test")
async def test_provider(
    provider: str, db: DBDep, current_user: CurrentUser,
    to: str = Query(min_length=1, max_length=200),
) -> dict:
    """Actually deliver a test message. Checking credentials without sending would pass on
    an account that cannot reach the user's own country."""
    try:
        await paging_service.verify(db, current_user.id, provider, to.strip())
    except paging_service.PagingError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"sent": True, "to": to}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
