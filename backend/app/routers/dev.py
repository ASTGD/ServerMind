"""Dev Door endpoints (admin-only) — docs/EVAL-DRIVEN-DEV.md.

The Prompt Inspector's dry-run: plan a chat message and return the full trace (prompt,
raw output, parsed plan, token/cost meta) WITHOUT executing anything on the server. Every
route is guarded by ``require_admin`` — never reachable by a customer, even one with a
valid token. The server is resolved through the admin's own access (team_service), so the
dev tool cannot reach a server the admin isn't entitled to.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import require_admin
from app.models.user import User
from app.services import dev_service, team_service

router = APIRouter(prefix="/api/dev", tags=["dev"])


class DryRunRequest(BaseModel):
    server_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4000)


@router.post("/dry-run")
async def dry_run(
    body: DryRunRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Plan a message as Ally would — return the full trace, never execute a command."""
    access = await team_service.get_access(db, admin, str(body.server_id))
    if access is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Server not found"
        )
    return await dev_service.dry_run(access.server, body.message, acting_user=admin)
