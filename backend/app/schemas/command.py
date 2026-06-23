from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    language: str = "en"


class CommandItem(BaseModel):
    cmd: str
    description: str
    risk_level: str
    requires_confirmation: bool = False


class AIPlan(BaseModel):
    intent_understood: str
    clarification_needed: str | None
    plan_summary: str
    commands: list[CommandItem]
    estimated_duration_seconds: int
    post_execution_message: str
    follow_up_suggestions: list[str]


class CommandLogOut(BaseModel):
    id: uuid.UUID
    server_id: uuid.UUID
    user_input: str
    ai_plan: dict | None
    commands: list | None
    output: str | None
    status: str | None
    ai_explanation: str | None
    risk_level: str | None
    execution_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ActivityItem(BaseModel):
    """A unified activity feed entry — an AI command or a playbook/script run."""

    id: uuid.UUID
    kind: str                      # 'command' | 'playbook'
    server_id: uuid.UUID | None
    title: str                     # user_input, or the playbook/script title
    status: str | None
    risk_level: str | None = None
    duration_ms: int | None = None
    created_at: datetime
