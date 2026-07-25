"""Autopilot — Ally's scheduled missions (docs/PRO-FEATURES-PLAN.md §4 #1+#2).

A task is a standing instruction: a goal, a schedule, and a policy saying how far Ally may
go without you. Tasks are user-owned; a task bound to a server requires **execute** access
to it, because that is what the mission will do.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.autopilot import POLICIES, POLICY_REPORT_ONLY, AutopilotTask
from app.models.user import User
from app.services import autopilot_service, scheduler_service

router = APIRouter(prefix="/api", tags=["autopilot"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    goal: str = Field(min_length=1)
    server_id: uuid.UUID | None = None
    policy: str = POLICY_REPORT_ONLY
    cron_expression: str = Field(min_length=1, max_length=100)
    human_schedule: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    channel: str | None = None
    channel_target: str | None = Field(default=None, max_length=500)
    notify_on_change_only: bool = True


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    goal: str | None = None
    policy: str | None = None
    cron_expression: str | None = Field(default=None, max_length=100)
    human_schedule: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    channel: str | None = None
    channel_target: str | None = Field(default=None, max_length=500)
    notify_on_change_only: bool | None = None


class TaskOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    server_id: uuid.UUID | None = None
    name: str
    goal: str
    policy: str
    policy_label: str = ""
    cron_expression: str
    human_schedule: str | None = None
    is_active: bool
    channel: str | None = None
    channel_target: str | None = None
    notify_on_change_only: bool
    last_run: datetime | None = None
    last_status: str | None = None
    next_run: datetime | None = None
    created_at: datetime


def _out(task: AutopilotTask) -> TaskOut:
    item = TaskOut.model_validate(task)
    item.policy_label = autopilot_service.policy_label(task.policy)
    return item


def _validate(policy: str | None, cron: str | None) -> None:
    if policy is not None and policy not in POLICIES:
        raise HTTPException(status_code=422, detail=f"policy must be one of {sorted(POLICIES)}")
    if cron is not None and not scheduler_service.validate_cron(cron):
        raise HTTPException(status_code=422, detail="Invalid schedule")


async def _get_task(task_id: str, user: User, db: AsyncSession) -> AutopilotTask:
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Task not found")
    task = (await db.execute(
        select(AutopilotTask).where(AutopilotTask.id == tid, AutopilotTask.user_id == user.id)
    )).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/autopilot/tasks", response_model=list[TaskOut])
async def list_tasks(db: DBDep, current_user: CurrentUser) -> list[TaskOut]:
    """Your autopilot tasks."""
    rows = (await db.execute(
        select(AutopilotTask)
        .where(AutopilotTask.user_id == current_user.id)
        .order_by(AutopilotTask.created_at.desc())
    )).scalars().all()
    return [_out(t) for t in rows]


@router.post("/autopilot/tasks", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate, db: DBDep, current_user: CurrentUser) -> TaskOut:
    """Create a task. A server-bound task needs EXECUTE access — autopilot will act there."""
    _validate(body.policy, body.cron_expression)
    if body.server_id:
        await resolve_server(str(body.server_id), current_user, db, need_execute=True)

    task = AutopilotTask(
        user_id=current_user.id, server_id=body.server_id,
        name=body.name, goal=body.goal, policy=body.policy,
        cron_expression=body.cron_expression, human_schedule=body.human_schedule,
        is_active=body.is_active, channel=body.channel, channel_target=body.channel_target,
        notify_on_change_only=body.notify_on_change_only,
    )
    try:
        task.next_run = scheduler_service.compute_next_run(task.cron_expression)
    except Exception:  # noqa: BLE001
        task.next_run = None

    db.add(task)
    await db.commit()
    await db.refresh(task)
    autopilot_service.schedule_task(task)
    return _out(task)


@router.put("/autopilot/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: str, body: TaskUpdate, db: DBDep, current_user: CurrentUser) -> TaskOut:
    task = await _get_task(task_id, current_user, db)
    data = body.model_dump(exclude_unset=True)
    _validate(data.get("policy"), data.get("cron_expression"))

    for field, value in data.items():
        setattr(task, field, value)
    try:
        task.next_run = scheduler_service.compute_next_run(task.cron_expression) if task.is_active else None
    except Exception:  # noqa: BLE001
        task.next_run = None

    await db.commit()
    await db.refresh(task)
    autopilot_service.schedule_task(task)
    return _out(task)


@router.delete("/autopilot/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str, db: DBDep, current_user: CurrentUser) -> None:
    task = await _get_task(task_id, current_user, db)
    autopilot_service.unschedule_task(task.id)
    await db.delete(task)
    await db.commit()


@router.post("/autopilot/tasks/{task_id}/run", response_model=TaskOut)
async def run_now(task_id: str, db: DBDep, current_user: CurrentUser) -> TaskOut:
    """Run this task now, so the owner can see what it does before trusting it nightly."""
    task = await _get_task(task_id, current_user, db)
    await autopilot_service._execute_task(str(task.id))
    await db.refresh(task)
    return _out(task)
