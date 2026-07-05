from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CloudAccountCreate(BaseModel):
    provider: str                       # 'aws' (Phase D adds more)
    label: str = Field(min_length=1)
    credential: dict[str, str]          # provider-shaped, e.g. {access_key_id, secret_access_key, region}


class CloudAccountOut(BaseModel):
    id: uuid.UUID
    provider: str
    label: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InstanceOut(BaseModel):
    instance_id: str
    name: str
    public_ip: str | None
    private_ip: str | None
    os: str
    state: str
    region: str | None = None
    instance_type: str | None = None
    already_imported: bool = False


class ImportBody(BaseModel):
    instance_ids: list[str] = Field(min_length=1)
    username: str = Field(min_length=1)      # applied to the whole batch (edit per-asset later)
    auth_type: str                           # 'password' | 'key'
    credential: str                          # the SSH key / password for the batch
    use_private_ip: bool = False             # prefer the private IP as the host


class ImportResult(BaseModel):
    imported: int
    skipped: int                             # already-imported instances
    limited: bool = False                    # stopped early on the plan's server cap
    detail: str | None = None
