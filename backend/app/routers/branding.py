"""Branding — the white-label settings, and the client report endpoint.

Branding is per user and applies only to client-facing output (public status pages, client
reports). It never changes the app for the agency's own staff.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.branding import Branding
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
