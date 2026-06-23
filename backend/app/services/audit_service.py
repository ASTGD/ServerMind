"""Audit trail — record security/account events. Never raises into the caller."""
from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    # Honour the first X-Forwarded-For hop when behind a proxy, else the peer.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


async def audit(
    db: AsyncSession,
    user: User | None,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | int | None = None,
    meta: dict | None = None,
    request: Request | None = None,
) -> None:
    """Write one audit row. Call AFTER the endpoint's main commit. Auditing must
    never break the request — failures are logged and swallowed."""
    ua = request.headers.get("user-agent") if request is not None else None
    ip = _client_ip(request)
    try:
        db.add(
            AuditLog(
                user_id=(user.id if user else None),
                action=action,
                target_type=target_type,
                target_id=(str(target_id) if target_id is not None else None),
                meta=meta,
                ip=(ip[:64] if ip else None),
                user_agent=(ua[:255] if ua else None),
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — auditing is best-effort
        logger.warning("audit write failed (%s): %s", action, exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
