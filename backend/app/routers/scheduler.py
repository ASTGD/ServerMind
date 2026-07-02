"""Scheduler router — scheduled task CRUD endpoints."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, get_db
from app.dependencies.access import resolve_server
from app.models.scheduled_task import ScheduledTask
from app.models.server import Server
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.scheduled_task import ScheduledTaskCreate, ScheduledTaskOut
from app.services import ai_service, metering_service, scheduler_service

router = APIRouter(prefix="/api", tags=["scheduler"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _get_server(
    server_id: str, user: User, db: AsyncSession, *, need_execute: bool = False
) -> Server:
    """Fetch a server the user can access (owner or team member)."""
    return await resolve_server(server_id, user, db, need_execute=need_execute)


async def _get_task(task_id: str, user: User, db: AsyncSession) -> ScheduledTask:
    """Fetch a scheduled task that belongs to the authenticated user."""
    try:
        tid = uuid.UUID(task_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == tid,
            ScheduledTask.user_id == user.id,
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return task


async def _resolve_cron(body: ScheduledTaskCreate) -> tuple[str, str | None]:
    """Return (cron_expression, human_schedule) resolving NL input if needed."""
    cron = body.cron_expression
    human = body.human_schedule

    if not cron and human:
        try:
            parsed = await ai_service.parse_schedule(human)
            cron = parsed["cron_expression"]
        except Exception as exc:
            logger.error("parse_schedule failed for '%s': %s", human, exc)
            raise HTTPException(
                status_code=422,
                detail=f"Could not parse schedule '{human}': {exc}",
            )

    if not cron:
        raise HTTPException(
            status_code=422,
            detail="Provide either cron_expression or human_schedule.",
        )

    # Validate cron
    if not scheduler_service.validate_cron(cron):
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: {cron!r}")

    return cron, human


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/servers/{server_id}/schedules", response_model=list[ScheduledTaskOut])
async def list_schedules(
    server_id: str, db: DBDep, current_user: CurrentUser
) -> list[ScheduledTask]:
    """List all scheduled tasks for a server."""
    await _get_server(server_id, current_user, db)
    result = await db.execute(
        select(ScheduledTask)
        .where(
            ScheduledTask.server_id == uuid.UUID(server_id),
            ScheduledTask.user_id == current_user.id,
        )
        .order_by(ScheduledTask.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/servers/{server_id}/schedules", response_model=ScheduledTaskOut, status_code=201)
async def create_schedule(
    server_id: str,
    body: ScheduledTaskCreate,
    db: DBDep,
    current_user: CurrentUser,
) -> ScheduledTask:
    """Create a new scheduled task.

    If *human_schedule* is provided and *cron_expression* is omitted, the AI
    converts the natural language description into a cron expression.
    """
    await _get_server(server_id, current_user, db, need_execute=True)
    cron, human = await _resolve_cron(body)

    next_run = scheduler_service.compute_next_run(cron)

    task = ScheduledTask(
        server_id=uuid.UUID(server_id),
        user_id=current_user.id,
        title=body.title,
        task_type=body.task_type,
        payload=body.payload,
        cron_expression=cron,
        human_schedule=human,
        is_active=True,
        next_run=next_run,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    scheduler_service.schedule_task(task)
    return task


@router.put("/schedules/{task_id}", response_model=ScheduledTaskOut)
async def update_schedule(
    task_id: str,
    body: ScheduledTaskCreate,
    db: DBDep,
    current_user: CurrentUser,
) -> ScheduledTask:
    """Update a scheduled task. Natural language schedule is re-parsed if supplied."""
    task = await _get_task(task_id, current_user, db)

    cron, human = await _resolve_cron(body) if (body.cron_expression or body.human_schedule) \
        else (task.cron_expression, task.human_schedule)

    next_run = scheduler_service.compute_next_run(cron)

    task.title = body.title
    task.task_type = body.task_type
    task.payload = body.payload
    task.cron_expression = cron
    task.human_schedule = human
    task.next_run = next_run

    await db.commit()
    await db.refresh(task)

    scheduler_service.unschedule_task(task_id)
    if task.is_active:
        scheduler_service.schedule_task(task)

    return task


@router.delete("/schedules/{task_id}", status_code=204)
async def delete_schedule(
    task_id: str, db: DBDep, current_user: CurrentUser
) -> None:
    """Delete a scheduled task and remove it from the scheduler."""
    task = await _get_task(task_id, current_user, db)
    scheduler_service.unschedule_task(task_id)
    await db.delete(task)
    await db.commit()


@router.post("/schedules/{task_id}/toggle", response_model=ScheduledTaskOut)
async def toggle_schedule(
    task_id: str, db: DBDep, current_user: CurrentUser
) -> ScheduledTask:
    """Pause or resume a scheduled task."""
    task = await _get_task(task_id, current_user, db)
    task.is_active = not task.is_active

    if task.is_active:
        scheduler_service.schedule_task(task)
    else:
        scheduler_service.unschedule_task(task_id)

    await db.commit()
    await db.refresh(task)
    return task


@router.post("/schedules/{task_id}/run-now", response_model=ScheduledTaskOut)
async def run_now(
    task_id: str, db: DBDep, current_user: CurrentUser
) -> ScheduledTask:
    """Trigger an immediate (out-of-schedule) run of a task."""
    task = await _get_task(task_id, current_user, db)
    asyncio.create_task(scheduler_service._execute_task(str(task.id)))
    return task


# ── Parse schedule helper endpoint ───────────────────────────────────────────

class ParseScheduleRequest(BaseModel):
    """Request body for the schedule parser helper."""

    input: str


class ParseScheduleResponse(BaseModel):
    """Parsed schedule result."""

    cron_expression: str
    human_description: str


@router.post("/parse-schedule", response_model=ParseScheduleResponse)
async def parse_schedule(
    body: ParseScheduleRequest, current_user: CurrentUser
) -> ParseScheduleResponse:
    """Convert a natural language schedule string to a cron expression.

    Used by the frontend to preview the cron before saving.
    """
    # Metered in the ledger at 0 actions (docs/AI-METERING.md §2 — tiny utility call,
    # free to the user; the tokens still show in our cost accounting).
    tok = metering_service.start_collection()
    try:
        result = await ai_service.parse_schedule(body.input)
        return ParseScheduleResponse(
            cron_expression=result.get("cron_expression", ""),
            human_description=result.get("human_description", ""),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        calls = metering_service.finish_collection(tok)
        if calls:
            async with AsyncSessionLocal() as db:
                await metering_service.record(
                    db, user_id=current_user.id, feature="schedule_parse",
                    calls=calls, actions=0,
                )
