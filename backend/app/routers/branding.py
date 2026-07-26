"""Branding — the white-label settings, and the client report endpoint.

Branding is per user and applies only to client-facing output (public status pages, client
reports). It never changes the app for the agency's own staff.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.branding import Branding
from app.models.client_report import ClientReportSubscription
from app.models.server import Server
from app.models.user import User
from app.services import branding_service, client_report_service

router = APIRouter(prefix="/api", tags=["branding"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class BrandingBody(BaseModel):
    company_name: str | None = Field(default=None, max_length=120)
    logo_url: str | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, max_length=9)
    support_url: str | None = Field(default=None, max_length=500)
    support_email: str | None = Field(default=None, max_length=255)
    footer_text: str | None = None
    hide_serverally_branding: bool | None = None


class BrandingOut(BaseModel):
    model_config = {"from_attributes": True}

    company_name: str | None = None
    logo_url: str | None = None
    primary_color: str | None = None
    support_url: str | None = None
    support_email: str | None = None
    footer_text: str | None = None
    hide_serverally_branding: bool = False


async def _get_or_create(db: AsyncSession, user: User) -> Branding:
    row = (await db.execute(
        select(Branding).where(Branding.user_id == user.id)
    )).scalar_one_or_none()
    if row is None:
        row = Branding(user_id=user.id)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


@router.get("/branding", response_model=BrandingOut)
async def get_branding(db: DBDep, current_user: CurrentUser) -> BrandingOut:
    return BrandingOut.model_validate(await _get_or_create(db, current_user))


@router.put("/branding", response_model=BrandingOut)
async def update_branding(body: BrandingBody, db: DBDep, current_user: CurrentUser) -> BrandingOut:
    """Update branding. The colour and URLs are validated here because they are rendered
    on a PUBLIC page — rejecting at the boundary is the only place it happens once."""
    branding = await _get_or_create(db, current_user)
    data = body.model_dump(exclude_unset=True)

    if "primary_color" in data and not branding_service.valid_color(data["primary_color"]):
        raise HTTPException(status_code=422, detail="Colour must be a hex value like #4F46E5.")
    for field in ("logo_url", "support_url"):
        if field in data and not branding_service.valid_url(data[field]):
            raise HTTPException(
                status_code=422,
                detail=f"{field.replace('_', ' ').title()} must be a full http(s) address.",
            )

    for field, value in data.items():
        setattr(branding, field, value)
    if branding.primary_color:
        branding.primary_color = branding_service.normalise_color(branding.primary_color)

    await db.commit()
    await db.refresh(branding)
    return BrandingOut.model_validate(branding)


@router.get("/servers/{server_id}/client-report")
async def client_report(
    server_id: str, db: DBDep, current_user: CurrentUser,
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    """A branded, plain-language summary of the period — for an agency to send a client.

    Deterministic: every number comes from data we already store, so it costs nothing to
    generate and cannot hallucinate.
    """
    server = await resolve_server(server_id, current_user, db)
    report = await client_report_service.build(db, server, days)
    branding = (await db.execute(
        select(Branding).where(Branding.user_id == current_user.id)
    )).scalar_one_or_none()
    report["branding"] = branding_service.public_branding(branding)
    report["summary"] = client_report_service.plain_summary(report)
    return report


# ── Scheduled monthly delivery ───────────────────────────────────────────────


class SubscriptionBody(BaseModel):
    server_id: uuid.UUID
    recipient_email: EmailStr
    recipient_name: str | None = Field(default=None, max_length=255)
    # Capped at 28 so every month actually has this day.
    send_day: int = Field(default=1, ge=1, le=28)
    period_days: int = Field(default=30, ge=1, le=365)
    is_active: bool = True


class SubscriptionPatch(BaseModel):
    recipient_email: EmailStr | None = None
    recipient_name: str | None = Field(default=None, max_length=255)
    send_day: int | None = Field(default=None, ge=1, le=28)
    period_days: int | None = Field(default=None, ge=1, le=365)
    is_active: bool | None = None


class SubscriptionOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    server_id: uuid.UUID
    recipient_email: str
    recipient_name: str | None = None
    send_day: int
    period_days: int
    is_active: bool
    last_sent: datetime | None = None
    last_status: str | None = None


async def _get_sub(sub_id: str, user: User, db: AsyncSession) -> ClientReportSubscription:
    try:
        sid = uuid.UUID(sub_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Recipient not found")
    sub = (await db.execute(
        select(ClientReportSubscription).where(
            ClientReportSubscription.id == sid,
            ClientReportSubscription.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return sub


@router.get("/client-reports", response_model=list[SubscriptionOut])
async def list_report_recipients(db: DBDep, current_user: CurrentUser) -> list[SubscriptionOut]:
    rows = (await db.execute(
        select(ClientReportSubscription)
        .where(ClientReportSubscription.user_id == current_user.id)
        .order_by(ClientReportSubscription.created_at.desc())
    )).scalars().all()
    return [SubscriptionOut.model_validate(r) for r in rows]


@router.post("/client-reports", response_model=SubscriptionOut, status_code=201)
async def add_report_recipient(
    body: SubscriptionBody, db: DBDep, current_user: CurrentUser
) -> SubscriptionOut:
    """Send this server's report to a client every month.

    ``resolve_server`` is the access check — a recipient can only ever be attached to a
    server the caller may actually see.
    """
    await resolve_server(str(body.server_id), current_user, db)
    sub = ClientReportSubscription(
        user_id=current_user.id,
        server_id=body.server_id,
        recipient_email=str(body.recipient_email),
        recipient_name=(body.recipient_name or "").strip() or None,
        send_day=body.send_day,
        period_days=body.period_days,
        is_active=body.is_active,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return SubscriptionOut.model_validate(sub)


@router.put("/client-reports/{sub_id}", response_model=SubscriptionOut)
async def update_report_recipient(
    sub_id: str, body: SubscriptionPatch, db: DBDep, current_user: CurrentUser
) -> SubscriptionOut:
    sub = await _get_sub(sub_id, current_user, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(sub, field, str(value) if field == "recipient_email" else value)
    await db.commit()
    await db.refresh(sub)
    return SubscriptionOut.model_validate(sub)


@router.delete("/client-reports/{sub_id}", status_code=204)
async def delete_report_recipient(sub_id: str, db: DBDep, current_user: CurrentUser) -> None:
    sub = await _get_sub(sub_id, current_user, db)
    await db.delete(sub)
    await db.commit()


@router.post("/client-reports/{sub_id}/send")
async def send_report_now(sub_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Send this recipient their report right now — the "see what my client gets" button.

    Deliberately does NOT touch ``last_sent``: a test send must not consume the month's
    scheduled delivery.
    """
    sub = await _get_sub(sub_id, current_user, db)
    from app.workers import client_report_worker
    try:
        sent = await client_report_worker.send_one(db, sub)
    except Exception as exc:  # noqa: BLE001 — report the reason, don't 500
        logger.warning("Manual client report send failed for %s: %s", sub.id, exc)
        raise HTTPException(status_code=502, detail=f"Could not send the email: {exc}")
    if not sent:
        raise HTTPException(status_code=422, detail="That server no longer exists.")
    return {"sent": True, "to": sub.recipient_email}


@router.get("/client-reports/{sub_id}/preview")
async def preview_report_email(sub_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """The exact email this recipient would receive — so an agency can check it before
    a client ever sees it."""
    sub = await _get_sub(sub_id, current_user, db)
    server = await db.get(Server, sub.server_id)
    if server is None:
        raise HTTPException(status_code=422, detail="That server no longer exists.")
    report = await client_report_service.build(db, server, sub.period_days)
    report["summary"] = client_report_service.plain_summary(report)
    branding = branding_service.public_branding(
        (await db.execute(
            select(Branding).where(Branding.user_id == current_user.id)
        )).scalar_one_or_none()
    )
    return client_report_service.render_email(
        report, branding, server.name, sub.recipient_name
    )
