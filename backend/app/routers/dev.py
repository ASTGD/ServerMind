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


# ── Eval runner + case capture (Phase 3 — the flywheel) ───────────────────────


class CaptureCaseRequest(BaseModel):
    category: str = Field(min_length=1, max_length=40)
    input: str = Field(min_length=1, max_length=2000)
    expected: str = Field(min_length=1, max_length=120)
    os: str = "linux"
    note: str | None = Field(default=None, max_length=1000)


def _case_out(row) -> dict:
    return {
        "id": str(row.id),
        "category": row.category,
        "input": row.input,
        "expected": row.expected,
        "os": row.os,
        "note": row.note,
        "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
    }


@router.get("/evals/run")
async def evals_run(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run the deterministic corpus + captured cases (offline, no API, no cost)."""
    return await dev_service.run_evals(db)


@router.get("/evals/cases")
async def evals_list(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return [_case_out(r) for r in await dev_service.list_captured(db)]


@router.post("/evals/cases", status_code=status.HTTP_201_CREATED)
async def evals_capture(
    body: CaptureCaseRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await dev_service.capture_case(
            db,
            category=body.category,
            input=body.input,
            expected=body.expected,
            os=body.os,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return _case_out(row)


@router.delete("/evals/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def evals_delete(
    case_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not await dev_service.delete_captured(db, case_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
