from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: uuid.UUID
    action: str
    target_type: str | None
    target_id: str | None
    meta: dict | None
    ip: str | None
    user_agent: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
