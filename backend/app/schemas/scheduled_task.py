from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel


class ScheduledTaskCreate(BaseModel):
    title: str
    task_type: str  # 'command'|'playbook'|'user_script'
    payload: dict
    cron_expression: str | None = None
    human_schedule: str | None = None  # natural language → AI converts to cron


class ScheduledTaskOut(BaseModel):
    id: uuid.UUID
    server_id: uuid.UUID
    title: str
    task_type: str
    payload: dict | None
    cron_expression: str
    human_schedule: str | None
    is_active: bool
    last_run: datetime | None
    last_status: str | None
    next_run: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
