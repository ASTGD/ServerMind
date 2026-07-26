"""Managing API keys and webhook endpoints.

These routes are **browser-only** — they require a logged-in session, never an API key. That
is the point: a key that could mint another key, or read its own signing secret, would be a
key that can escalate, and the whole `/api/v1` design rests on it not being able to.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.integration import (
    API_SCOPES, WEBHOOK_EVENTS, ApiKey, WebhookDelivery, WebhookEndpoint,
)
from app.models.user import User
from app.services import api_key_service, crypto_service, outbound_guard, webhook_service
from app.services import entitlements

router = APIRouter(prefix="/api", tags=["integrations"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ── API keys ─────────────────────────────────────────────────────────────────

class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["read"])
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


@router.get("/api-keys")
async def list_keys(db: DBDep, current_user: CurrentUser) -> list[dict]:
    rows = (await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id)
        .order_by(desc(ApiKey.created_at))
    )).scalars().all()
    return [api_key_service.serialize(k) for k in rows]


@router.post("/api-keys", status_code=201)
async def create_key(body: KeyCreate, db: DBDep, current_user: CurrentUser) -> dict:
    """Mint a key. The full secret is in this response and nowhere else, ever."""
    # Gate CREATING only — an existing key or webhook keeps working after a downgrade.
    entitlements.require(current_user, entitlements.API_ACCESS)
    unknown = [s for s in body.scopes if s not in API_SCOPES]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown permission: {', '.join(unknown)}. Choose from {', '.join(API_SCOPES)}.",
        )
    expires_at = (
        datetime.now(tz=timezone.utc) + timedelta(days=body.expires_in_days)
        if body.expires_in_days else None
    )
    row, full = await api_key_service.create(
        db, current_user.id, body.name, body.scopes, expires_at
    )
    return {
        **api_key_service.serialize(row),
        "key": full,
        "warning": "Copy this key now — it is not stored and cannot be shown again.",
    }


@router.delete("/api-keys/{key_id}", status_code=200)
async def revoke_key(key_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Key not found")
    key = (await db.execute(
        select(ApiKey).where(ApiKey.id == kid, ApiKey.user_id == current_user.id)
    )).scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="Key not found")
    await api_key_service.revoke(db, key)
    return api_key_service.serialize(key)


# ── Webhook endpoints ────────────────────────────────────────────────────────

class EndpointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2000)
    events: list[str] = Field(default_factory=list)


class EndpointPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    url: str | None = Field(default=None, max_length=2000)
    events: list[str] | None = None
    is_active: bool | None = None


def _check_events(events: list[str]) -> list[str]:
    unknown = [e for e in events if e not in WEBHOOK_EVENTS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"We don't send: {', '.join(unknown)}. Available events: "
                   f"{', '.join(WEBHOOK_EVENTS)}.",
        )
    if not events:
        raise HTTPException(status_code=422, detail="Choose at least one event to send.")
    return sorted(set(events))


def _check_url(url: str) -> str:
    """Validate at the write boundary so a bad URL is never stored.

    The same check runs again immediately before every delivery, because a hostname can be
    repointed at an internal address after it was saved.
    """
    try:
        return outbound_guard.check_url(url)
    except outbound_guard.BlockedURL as exc:
        raise HTTPException(status_code=422, detail=str(exc))


async def _get_endpoint(endpoint_id: str, user: User, db: AsyncSession) -> WebhookEndpoint:
    try:
        eid = uuid.UUID(endpoint_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Webhook not found")
    row = (await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == eid, WebhookEndpoint.user_id == user.id
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return row


@router.get("/webhooks")
async def list_webhooks(db: DBDep, current_user: CurrentUser) -> list[dict]:
    rows = (await db.execute(
        select(WebhookEndpoint).where(WebhookEndpoint.user_id == current_user.id)
        .order_by(desc(WebhookEndpoint.created_at))
    )).scalars().all()
    return [webhook_service.public_endpoint(r) for r in rows]


@router.get("/webhooks/events")
async def available_events() -> dict:
    """What can be subscribed to, and how to verify a signature.

    Served from code rather than written in a doc, so the instructions cannot drift from what
    we actually send.
    """
    return {
        "events": list(WEBHOOK_EVENTS),
        "signature": {
            "header": webhook_service.SIGNATURE_HEADER,
            "format": "t=<unix timestamp>,v1=<hex hmac>",
            "how_to_verify": (
                "Compute HMAC-SHA256 over the bytes '<t>.' + <raw request body> using your "
                "endpoint's secret, and compare it to v1 with a constant-time comparison. "
                f"Reject anything where t is more than {webhook_service.TOLERANCE_SECONDS} "
                "seconds from now — that is what stops an old request being replayed."
            ),
        },
        "delivery": {
            "retries": len(webhook_service.RETRY_BACKOFF_MINUTES),
            "backoff_minutes": list(webhook_service.RETRY_BACKOFF_MINUTES),
            "expects": "Any 2xx response. Redirects are not followed.",
            "disabled_after": webhook_service.FAILURES_BEFORE_DISABLE,
        },
    }


@router.post("/webhooks", status_code=201)
async def create_webhook(body: EndpointCreate, db: DBDep, current_user: CurrentUser) -> dict:
    # Gate CREATING only — an existing key or webhook keeps working after a downgrade.
    entitlements.require(current_user, entitlements.API_ACCESS)
    url = _check_url(body.url)
    events = _check_events(body.events)
    secret = webhook_service.generate_secret()
    row = WebhookEndpoint(
        user_id=current_user.id, name=body.name.strip(), url=url, events=events,
        encrypted_secret=crypto_service.encrypt(secret),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    # The secret is returned on create so the customer can paste it into their receiver
    # straight away; it stays retrievable from /secret because they will need it again.
    return {**webhook_service.public_endpoint(row), "secret": secret}


@router.put("/webhooks/{endpoint_id}")
async def update_webhook(
    endpoint_id: str, body: EndpointPatch, db: DBDep, current_user: CurrentUser
) -> dict:
    row = await _get_endpoint(endpoint_id, current_user, db)
    data = body.model_dump(exclude_unset=True)

    if "url" in data and data["url"]:
        row.url = _check_url(data["url"])
    if "events" in data and data["events"] is not None:
        row.events = _check_events(data["events"])
    if "name" in data and data["name"]:
        row.name = data["name"].strip()
    if "is_active" in data and data["is_active"] is not None:
        row.is_active = data["is_active"]
        if data["is_active"]:
            # Re-enabling clears the strike count, otherwise it would be switched off again
            # on the very next failure.
            row.failure_count = 0
            row.disabled_reason = None

    await db.commit()
    await db.refresh(row)
    return webhook_service.public_endpoint(row)


@router.get("/webhooks/{endpoint_id}/secret")
async def reveal_secret(endpoint_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """The signing secret, for the receiving code.

    Its own route, rather than a field on the list response, so it is fetched deliberately
    instead of appearing in every page load, log line and browser cache.
    """
    row = await _get_endpoint(endpoint_id, current_user, db)
    secret = webhook_service.read_secret(row)
    if secret is None:
        raise HTTPException(status_code=500,
                            detail="This webhook's secret could not be read. Recreate it.")
    return {"secret": secret}


@router.delete("/webhooks/{endpoint_id}", status_code=204)
async def delete_webhook(endpoint_id: str, db: DBDep, current_user: CurrentUser) -> None:
    row = await _get_endpoint(endpoint_id, current_user, db)
    await db.delete(row)
    await db.commit()


@router.post("/webhooks/{endpoint_id}/test")
async def test_webhook(endpoint_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Send a signed test event now, and report exactly what happened.

    Immediate rather than queued: someone setting this up needs the answer while they are
    still looking at their receiver's logs.
    """
    import asyncio
    import json as _json

    row = await _get_endpoint(endpoint_id, current_user, db)
    secret = webhook_service.read_secret(row)
    if secret is None:
        raise HTTPException(status_code=500, detail="This webhook's secret could not be read.")

    payload = webhook_service.build_payload("test", {
        "message": "This is a test event from ServerAlly.",
        "endpoint": row.name,
    })
    body = _json.dumps(payload).encode()
    headers = webhook_service.headers_for("test", str(uuid.uuid4()), secret, body)
    status, error = await asyncio.to_thread(webhook_service._post_sync, row.url, body, headers)

    row.last_delivery_at = datetime.now(tz=timezone.utc)
    row.last_status = "delivered" if not error else "failed"
    await db.commit()

    if error:
        raise HTTPException(status_code=502, detail=error)
    return {"sent": True, "http_status": status}


@router.get("/webhooks/{endpoint_id}/deliveries")
async def list_deliveries(
    endpoint_id: str, db: DBDep, current_user: CurrentUser,
    limit: int = Query(default=25, ge=1, le=100),
) -> list[dict]:
    row = await _get_endpoint(endpoint_id, current_user, db)
    rows = (await db.execute(
        select(WebhookDelivery).where(WebhookDelivery.endpoint_id == row.id)
        .order_by(desc(WebhookDelivery.created_at)).limit(limit)
    )).scalars().all()
    return [webhook_service.public_delivery(d) for d in rows]
