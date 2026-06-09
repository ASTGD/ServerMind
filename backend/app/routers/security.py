"""Security Audit router — run and retrieve server security scans."""
from __future__ import annotations

import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.security_scan import SecurityScan
from app.models.server import Server
from app.models.user import User
from app.schemas.security import Finding, ScanCounts, SecurityScanOut
from app.services import security_service

router = APIRouter(prefix="/api", tags=["security"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _get_server(server_id: str, user: User, db: AsyncSession) -> Server:
    try:
        sid = uuid.UUID(server_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Server not found")
    row = await db.execute(
        select(Server).where(Server.id == sid, Server.user_id == user.id)
    )
    server = row.scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return server


def _to_out(scan: SecurityScan) -> SecurityScanOut:
    """Build the API response from a stored scan row (parses findings JSON)."""
    try:
        raw_findings = json.loads(scan.findings or "[]")
    except (json.JSONDecodeError, TypeError):
        raw_findings = []
    return SecurityScanOut(
        id=scan.id,
        server_id=scan.server_id,
        score=scan.score,
        grade=scan.grade,
        status=scan.status,
        error=scan.error,
        duration_ms=scan.duration_ms,
        counts=ScanCounts(
            critical=scan.critical_count,
            high=scan.high_count,
            medium=scan.medium_count,
            low=scan.low_count,
            passed=scan.pass_count,
            info=scan.info_count,
        ),
        findings=[Finding(**f) for f in raw_findings],
        created_at=scan.created_at,
    )


# ── List scan history ───────────────────────────────────────────────────────

@router.get("/servers/{server_id}/security", response_model=list[SecurityScanOut])
async def list_security_scans(
    server_id: str,
    db: DBDep,
    current_user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SecurityScanOut]:
    """Return recent security scans for a server (most recent first)."""
    server = await _get_server(server_id, current_user, db)
    rows = await db.execute(
        select(SecurityScan)
        .where(SecurityScan.server_id == server.id)
        .order_by(SecurityScan.created_at.desc())
        .limit(limit)
    )
    return [_to_out(s) for s in rows.scalars().all()]


# ── Run a new scan ────────────────────────────────────────────────────────────

@router.post("/servers/{server_id}/security/scan", response_model=SecurityScanOut, status_code=201)
async def run_security_scan(
    server_id: str,
    db: DBDep,
    current_user: CurrentUser,
) -> SecurityScanOut:
    """Run a fresh security audit against the server and persist the result.

    All probe commands are read-only; suggested fixes are returned for display
    only and are never executed.
    """
    server = await _get_server(server_id, current_user, db)

    result = await security_service.run_scan(server)
    counts = result["counts"]

    scan = SecurityScan(
        server_id=server.id,
        user_id=current_user.id,
        score=result["score"],
        grade=result["grade"],
        status=result["status"],
        error=result.get("error"),
        duration_ms=result.get("duration_ms"),
        critical_count=counts.get("critical", 0),
        high_count=counts.get("high", 0),
        medium_count=counts.get("medium", 0),
        low_count=counts.get("low", 0),
        pass_count=counts.get("pass", 0),
        info_count=counts.get("info", 0),
        findings=json.dumps(result["findings"]),
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    return _to_out(scan)
