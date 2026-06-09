"""Pydantic schemas for Team Management."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TeamInvite(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role: str  # viewer | operator | admin


class TeamMemberUpdate(BaseModel):
    role: str


class TeamMemberOut(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    member_id: uuid.UUID | None = None
    role: str | None = None
    invited_email: str | None = None
    invite_token: str | None = None
    invite_accepted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ServerAccessItem(BaseModel):
    server_id: uuid.UUID
    can_execute: bool = False
    can_view_logs: bool = True


class ServerAccessOut(BaseModel):
    id: uuid.UUID
    server_id: uuid.UUID
    can_execute: bool
    can_view_logs: bool

    model_config = {"from_attributes": True}


class SetAccessBody(BaseModel):
    items: list[ServerAccessItem]


class AcceptResult(BaseModel):
    message: str
    owner_id: uuid.UUID
    role: str | None = None
