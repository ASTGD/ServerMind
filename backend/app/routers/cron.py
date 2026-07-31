"""The server's own scheduled jobs.

Deliberately separate from ServerAlly's scheduled tasks: those run from here and we keep
their history, while these run on the server whether or not this product is up. Laravel
and WordPress both need the second kind, and anything already on the server has been
invisible until now.

Every write carries the fingerprint of the crontab the screen was showing. If the file
moved on in between, the change is refused rather than applied — writing it would delete
whatever else was added, and what gets deleted that way is usually a backup job.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import audit_service, cron_service as cron

router = APIRouter(prefix="/api/servers/{server_id}/cron", tags=["cron"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class AddIn(BaseModel):
    user: str = Field(default="root", max_length=32)
    schedule: str = Field(max_length=100)
    command: str = Field(max_length=500)
    note: str = Field(default="", max_length=120)
    # What the screen was showing. Absent for a caller that did not read first.
    expect: str | None = Field(default=None, max_length=64)


class RemoveIn(BaseModel):
    user: str = Field(default="root", max_length=32)
    raw_line: str = Field(max_length=600)
    expect: str | None = Field(default=None, max_length=64)


def _supported(server) -> None:
    if server.connection_type != "ssh":
        raise HTTPException(
            400,
            "Scheduled jobs are read from a Linux server's crontab over SSH. This asset "
            "does not have one.",
        )


@router.get("")
async def list_jobs(server_id: str, current_user: CurrentUser, db: DBDep) -> dict:
    """Every scheduled job on this server, grouped by the account that owns it."""
    server = await resolve_server(server_id, current_user, db)
    _supported(server)
    result = await cron.list_jobs(server)
    result["presets"] = cron.PRESETS
    return result


@router.post("", status_code=201)
async def add_job(server_id: str, body: AddIn,
                  current_user: CurrentUser, db: DBDep) -> dict:
    """Schedule one job."""
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    _supported(server)
    try:
        result = await cron.add_job(
            server, user=body.user, schedule=body.schedule,
            command=body.command, note=body.note, expect=body.expect)
    except cron.CronError as exc:
        raise HTTPException(422, str(exc)) from exc

    await audit_service.audit(db, current_user, "cron.added",
                              target_type="server", target_id=server_id,
                              meta={"user": body.user, "schedule": body.schedule})
    return result


@router.post("/remove")
async def remove_job(server_id: str, body: RemoveIn,
                     current_user: CurrentUser, db: DBDep) -> dict:
    """Remove one scheduled job, matched by its exact line."""
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    _supported(server)
    try:
        result = await cron.remove_job(
            server, user=body.user, raw_line=body.raw_line, expect=body.expect)
    except cron.CronError as exc:
        raise HTTPException(422, str(exc)) from exc

    await audit_service.audit(db, current_user, "cron.removed",
                              target_type="server", target_id=server_id,
                              meta={"user": body.user})
    return result
