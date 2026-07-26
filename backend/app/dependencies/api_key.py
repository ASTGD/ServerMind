"""Authenticating a request that carries an API key.

This is the *only* place a key is accepted, and it is wired to the ``/api/v1`` router alone.
That is the whole security design: the routes that could turn a key into account control —
changing a password, disabling 2FA, reading a server credential, minting another key — do not
use this dependency, so they cannot be reached with a key no matter what scopes it has.

A key is accepted as ``Authorization: Bearer sa_live_…`` or ``X-API-Key: sa_live_…``. Bearer
is what most clients already do; the header is there because some CI systems make it awkward
to set Authorization.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.integration import SCOPE_WRITE, ApiKey
from app.models.user import User
from app.services import api_key_service

logger = logging.getLogger(__name__)


@dataclass
class ApiCaller:
    """Who is calling, and what they are allowed to do."""

    user: User
    key: ApiKey

    @property
    def can_write(self) -> bool:
        return SCOPE_WRITE in (self.key.scopes or [])

    def require_write(self) -> None:
        if not self.can_write:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This API key is read-only. Create a key with write access to do that.",
            )


def _present(authorization: str | None, x_api_key: str | None) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def get_api_caller(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> ApiCaller:
    """Resolve the API key on the request, or refuse.

    ``WWW-Authenticate`` is set so a well-behaved client knows *how* to authenticate rather
    than only that it failed.
    """
    presented = _present(authorization, x_api_key)
    if not presented:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Send your API key as 'Authorization: Bearer sa_live_…' or 'X-API-Key'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key, error = await api_key_service.resolve(db, presented)
    if key is None:
        # One message for unknown, revoked and expired keys would be friendlier to an
        # attacker but useless to the customer whose cron job just broke, and a key is
        # unguessable anyway — so the specific reason is worth more than the ambiguity.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=error,
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.get(User, key.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="This account is no longer active.")

    await api_key_service.touch(db, key)
    return ApiCaller(user=user, key=key)


async def require_write(caller: ApiCaller = Depends(get_api_caller)) -> ApiCaller:
    """For endpoints that change something."""
    caller.require_write()
    return caller
