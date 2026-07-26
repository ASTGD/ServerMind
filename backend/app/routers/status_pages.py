"""Status pages — owner CRUD, plus the PUBLIC page endpoint.

The public endpoint (`GET /api/public/status/{slug}`) takes **no authentication** — it is
the one route in the app a stranger is meant to reach. Therefore:

- it only serves pages the owner explicitly set ``is_public``;
- every field is built by ``status_page_service.public_item`` (an allowlist), never by
  dumping a model;
- it is rate-limited, because it is the app's only unauthenticated read surface.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.branding import Branding
from app.models.status_page import StatusPage, StatusPageItem
from app.models.uptime import UptimeMonitor
from app.models.user import User
from app.services import branding_service, entitlements, status_page_service
from app.services.rate_limit_service import limiter

router = APIRouter(prefix="/api", tags=["status-pages"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class PageItemIn(BaseModel):
    monitor_id: uuid.UUID
    display_name: str | None = Field(default=None, max_length=255)


class PageCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    support_url: str | None = Field(default=None, max_length=500)
    is_public: bool = False
    items: list[PageItemIn] = Field(default_factory=list)


class PageUpdate(BaseModel):
    slug: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    support_url: str | None = Field(default=None, max_length=500)
    is_public: bool | None = None
    items: list[PageItemIn] | None = None


class PageItemOut(BaseModel):
    monitor_id: uuid.UUID
    display_name: str | None = None
    monitor_name: str


class PageOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None = None
    support_url: str | None = None
    is_public: bool
    items: list[PageItemOut]
    created_at: datetime


async def _get_page(page_id: str, user: User, db: AsyncSession) -> StatusPage:
    try:
        pid = uuid.UUID(page_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Status page not found")
    page = (await db.execute(
        select(StatusPage).where(StatusPage.id == pid, StatusPage.user_id == user.id)
    )).scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Status page not found")
    return page


async def _items_out(db: AsyncSession, page: StatusPage) -> list[PageItemOut]:
    rows = (await db.execute(
        select(StatusPageItem, UptimeMonitor)
        .join(UptimeMonitor, UptimeMonitor.id == StatusPageItem.monitor_id)
        .where(StatusPageItem.page_id == page.id)
        .order_by(StatusPageItem.position)
    )).all()
    return [
        PageItemOut(monitor_id=item.monitor_id, display_name=item.display_name,
                    monitor_name=monitor.name)
        for item, monitor in rows
    ]


async def _out(db: AsyncSession, page: StatusPage) -> PageOut:
    return PageOut(
        id=page.id, slug=page.slug, title=page.title, description=page.description,
        support_url=page.support_url, is_public=page.is_public,
        items=await _items_out(db, page), created_at=page.created_at,
    )


async def _replace_items(db: AsyncSession, page: StatusPage, items: list[PageItemIn], user: User) -> None:
    """Set the page's monitors. Every monitor must belong to the caller — otherwise a page
    could publish someone else's uptime."""
    await db.execute(delete(StatusPageItem).where(StatusPageItem.page_id == page.id))
    if not items:
        return
    ids = [i.monitor_id for i in items]
    owned = {
        m.id for m in (await db.execute(
            select(UptimeMonitor).where(
                UptimeMonitor.id.in_(ids), UptimeMonitor.user_id == user.id
            )
        )).scalars().all()
    }
    missing = [str(i) for i in ids if i not in owned]
    if missing:
        raise HTTPException(status_code=404, detail=f"Monitor(s) not found: {', '.join(missing)}")
    for position, item in enumerate(items):
        db.add(StatusPageItem(
            page_id=page.id, monitor_id=item.monitor_id,
            display_name=(item.display_name or "").strip() or None, position=position,
        ))


def _validate_slug(slug: str | None) -> None:
    if slug is None:
        return
    if not status_page_service.valid_slug(slug):
        raise HTTPException(
            status_code=422,
            detail="The address may use lowercase letters, numbers and hyphens only, and "
                   "cannot be a reserved word.",
        )


# ── Owner CRUD ───────────────────────────────────────────────────────────────

@router.get("/status-pages", response_model=list[PageOut])
async def list_pages(db: DBDep, current_user: CurrentUser) -> list[PageOut]:
    pages = (await db.execute(
        select(StatusPage).where(StatusPage.user_id == current_user.id)
        .order_by(StatusPage.created_at.desc())
    )).scalars().all()
    return [await _out(db, p) for p in pages]


@router.post("/status-pages", response_model=PageOut, status_code=201)
async def create_page(body: PageCreate, db: DBDep, current_user: CurrentUser) -> PageOut:
    existing = (await db.execute(
        select(func.count()).select_from(StatusPage).where(StatusPage.user_id == current_user.id)
    )).scalar() or 0
    allowed, limit = entitlements.count_gate(current_user, "max_status_pages", existing)
    if not allowed:
        raise HTTPException(
            status_code=402,
            detail=entitlements.count_message(current_user, "status pages", limit),
        )

    slug = body.slug.strip().lower()
    _validate_slug(slug)
    if (await db.execute(select(StatusPage).where(StatusPage.slug == slug))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="That address is already taken.")

    page = StatusPage(
        user_id=current_user.id, slug=slug, title=body.title,
        description=body.description, support_url=body.support_url,
        is_public=body.is_public,
    )
    db.add(page)
    await db.flush()
    await _replace_items(db, page, body.items, current_user)
    await db.commit()
    await db.refresh(page)
    return await _out(db, page)


@router.put("/status-pages/{page_id}", response_model=PageOut)
async def update_page(page_id: str, body: PageUpdate, db: DBDep, current_user: CurrentUser) -> PageOut:
    page = await _get_page(page_id, current_user, db)
    data = body.model_dump(exclude_unset=True)

    if "slug" in data and data["slug"]:
        slug = data["slug"].strip().lower()
        _validate_slug(slug)
        clash = (await db.execute(
            select(StatusPage).where(StatusPage.slug == slug, StatusPage.id != page.id)
        )).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="That address is already taken.")
        page.slug = slug

    for field in ("title", "description", "support_url", "is_public"):
        if field in data:
            setattr(page, field, data[field])
    if body.items is not None:
        await _replace_items(db, page, body.items, current_user)

    await db.commit()
    await db.refresh(page)
    return await _out(db, page)


@router.delete("/status-pages/{page_id}", status_code=204)
async def delete_page(page_id: str, db: DBDep, current_user: CurrentUser) -> None:
    page = await _get_page(page_id, current_user, db)
    await db.delete(page)
    await db.commit()


# ── The public page ──────────────────────────────────────────────────────────

@router.get("/public/status/{slug}")
@limiter.limit("60/minute")
async def public_status(slug: str, request: Request, db: DBDep) -> dict:
    """The unauthenticated status page payload.

    Only serves a page the owner published. Everything here comes from
    ``status_page_service.public_item`` — an allowlist — so the monitored URL, the internal
    error text and the server behind it can never appear.
    """
    page = (await db.execute(
        select(StatusPage).where(
            StatusPage.slug == slug.strip().lower(), StatusPage.is_public.is_(True)
        )
    )).scalar_one_or_none()
    if not page:
        # Same answer whether it doesn't exist or isn't published — an unpublished page
        # must not be discoverable.
        raise HTTPException(status_code=404, detail="No status page here.")

    rows = (await db.execute(
        select(StatusPageItem, UptimeMonitor)
        .join(UptimeMonitor, UptimeMonitor.id == StatusPageItem.monitor_id)
        .where(StatusPageItem.page_id == page.id)
        .order_by(StatusPageItem.position)
    )).all()

    monitor_ids = [m.id for _i, m in rows]
    history = await status_page_service.daily_history(db, monitor_ids)
    percentages = await status_page_service.uptime_percentages(db, monitor_ids)

    items = [
        status_page_service.public_item(
            monitor, item.display_name,
            history.get(monitor.id, []),
            percentages.get(monitor.id, [100.0, 100.0])[0],
            percentages.get(monitor.id, [100.0, 100.0])[1],
        )
        for item, monitor in rows
    ]
    status = status_page_service.overall_status(items)
    down = sum(1 for i in items if i["status"] == "down")

    # White-label: the page belongs to the owner's brand, not ours.
    branding = (await db.execute(
        select(Branding).where(Branding.user_id == page.user_id)
    )).scalar_one_or_none()

    return {
        "branding": branding_service.public_branding(branding),
        "title": page.title,
        "description": page.description,
        "support_url": page.support_url,
        "status": status,
        "message": status_page_service.overall_message(status, down, len(items) or 1),
        "items": items,
        "history_days": status_page_service.HISTORY_DAYS,
        "checked_at": datetime.now().astimezone().isoformat(),
    }
