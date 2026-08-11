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
    # Optional now: an instance reached through Systems Manager has no login of its own, and
    # demanding one would be demanding the exact artefact SSM exists to remove. Required
    # again — checked in the router, against what each instance actually resolves to — the
    # moment one selected instance will use SSH or WinRM.
    username: str = ""                       # applied to the whole batch (edit per-asset later)
    auth_type: str = "password"              # 'password' | 'key'
    credential: str = ""                     # the SSH key / password for the batch
    use_private_ip: bool = False             # prefer the private IP as the host
    prefer_ssm: bool = False                 # use Systems Manager wherever it is available


class ImportResult(BaseModel):
    imported: int
    skipped: int                             # already-imported instances
    limited: bool = False                    # stopped early on the plan's server cap
    detail: str | None = None
