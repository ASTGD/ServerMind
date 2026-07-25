"""Server log viewer — discover the logs on a server and read their tails.

Read-only: discovery uses a fixed catalogue authored in ``log_service``, and reading is
``tail``/``grep`` only. Access follows the same rule as every other server-scoped router
(``resolve_server``), so a teammate only sees logs on servers they can access.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import log_service

router = APIRouter(prefix="/api", tags=["logs"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class LogFile(BaseModel):
    path: str
    label: str
    category: str
    size_bytes: int


class LogContent(BaseModel):
    path: str
    content: str
    truncated: bool
    line_count: int


@router.get("/servers/{server_id}/logs", response_model=list[LogFile])
async def list_logs(server_id: str, db: DBDep, current_user: CurrentUser) -> list[LogFile]:
    """Which log files exist on this server — labelled in plain language."""
    server = await resolve_server(server_id, current_user, db)
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=400,
            detail=f"Log viewing needs an SSH server (this one is '{server.connection_type}').",
        )
    return [LogFile(**entry) for entry in await log_service.discover(server)]


@router.get("/servers/{server_id}/logs/read", response_model=LogContent)
async def read_log(
    server_id: str,
    db: DBDep,
    current_user: CurrentUser,
    path: str = Query(..., min_length=1, max_length=1024),
    lines: int = Query(default=log_service.DEFAULT_LINES, ge=1, le=log_service.MAX_LINES),
    search: str | None = Query(default=None, max_length=200),
) -> LogContent:
    """Read the last ``lines`` of a log, optionally filtered by plain text."""
    server = await resolve_server(server_id, current_user, db)
    if server.connection_type != "ssh":
        raise HTTPException(
            status_code=400,
            detail=f"Log viewing needs an SSH server (this one is '{server.connection_type}').",
        )
    try:
        result = await log_service.read(server, path, lines, (search or "").strip() or None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Log read failed on %s: %s", server_id, exc)
        raise HTTPException(status_code=502, detail=f"Could not read the log: {type(exc).__name__}")
    return LogContent(path=path, **result)
