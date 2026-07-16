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
from app.services import admin_service, dev_service, team_service

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


# ── Observability (Phase 4) ───────────────────────────────────────────────────


@router.get("/activity")
async def activity(
    limit: int = 60,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Recent AI calls (the ledger) + this period's cost/actions summary."""
    return await dev_service.activity(db, limit=min(max(limit, 1), 200))


# ── Operator console (SAAS-LAUNCH-PLAN §5) ───────────────────────────────────
# Support/ops, NOT billing: WHMCS owns customers, orders and revenue. These answer only
# what WHMCS cannot — servers, Ally, and what the AI really costs us. All read-only.


@router.get("/admin/overview")
async def admin_overview(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Users, plans, active, servers, and our REAL AI cost this period."""
    return await admin_service.overview(db)


@router.get("/admin/users")
async def admin_users(
    q: str | None = None,
    limit: int = 100,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Every user with plan (a read-only mirror of WHMCS) + both meters + AI cost."""
    return await admin_service.list_users(db, limit=min(max(limit, 1), 500), q=q)


@router.get("/admin/users/{user_id}")
async def admin_user_detail(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """The support screen: their servers, missions and recent failures — never credentials."""
    out = await admin_service.user_detail(db, user_id)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such user")
    return out


@router.get("/admin/entitlements")
async def admin_entitlements(
    limit: int = 100,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """"Did billing land?" — every plan change WHMCS drove."""
    return await admin_service.entitlement_log(db, limit=min(max(limit, 1), 500))


class ProviderAbRequest(BaseModel):
    # Optional OpenAI price overrides per tier, e.g. {"mid": {"in": 2.5, "out": 10}} — so
    # management can plug in OpenAI's real quote and see the true cost on our real usage.
    openai: dict[str, dict[str, float]] | None = None


@router.post("/provider-ab")
async def provider_ab(
    body: ProviderAbRequest | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Claude vs OpenAI cost, re-priced over this period's REAL ledger token usage. No
    live calls, no OpenAI key — arithmetic over data we already have (docs/AI-METERING.md)."""
    return await dev_service.provider_ab(db, body.openai if body else None)
