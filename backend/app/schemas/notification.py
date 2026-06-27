from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    body: str | None
    status: str | None
    server_id: uuid.UUID | None
    ref_id: uuid.UUID | None
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread: int
