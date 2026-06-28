from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel


class PlaybookOut(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    category: str | None
    os_family: str | None
    script_type: str | None
    variables: list | None
    supported_os: list[str] | None
    est_runtime_sec: int | None
    is_official: bool
    run_count: int
    rating: float | None
    tags: list[str] | None
    version: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PlaybookDetailOut(PlaybookOut):
    script_bash: str | None
    script_powershell: str | None
    access_info: dict | None = None


class PlaybookRunOut(BaseModel):
    id: uuid.UUID
    server_id: uuid.UUID
    playbook_id: uuid.UUID | None
    variables_used: dict | None
    output: str | None
    status: str | None
    failure_reason: str | None = None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class RunPlaybookRequest(BaseModel):
    server_id: uuid.UUID
    variables: dict | None = None


class UserScriptCreate(BaseModel):
    title: str
    description: str | None = None
    script_type: str
    script_content: str
    variables: dict | None = None
    tags: list[str] | None = None


class UserScriptOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    script_type: str | None
    script_content: str
    source: str | None
    tags: list[str] | None
    created_at: datetime

    model_config = {"from_attributes": True}
