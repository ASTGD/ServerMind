import uuid
from datetime import datetime

from pydantic import BaseModel


class ServerMetricOut(BaseModel):
    id: uuid.UUID
    server_id: uuid.UUID
    cpu_percent: float | None
    ram_percent: float | None
    ram_used_mb: int | None
    ram_total_mb: int | None
    disk_percent: float | None
    disk_used_gb: float | None
    disk_total_gb: float | None
    load_1: float | None
    load_5: float | None
    load_15: float | None
    uptime_seconds: int | None
    recorded_at: datetime

    model_config = {"from_attributes": True}


class AlertCreate(BaseModel):
    metric: str
    condition: str
    threshold: float
    channel: str
    channel_target: str


class AlertOut(BaseModel):
    id: uuid.UUID
    server_id: uuid.UUID
    metric: str | None
    condition: str | None
    threshold: float | None
    channel: str | None
    channel_target: str | None
    is_active: bool
    last_triggered: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
