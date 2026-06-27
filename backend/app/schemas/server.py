from __future__ import annotations
import uuid
from datetime import datetime

from pydantic import BaseModel


class ServerCreate(BaseModel):
    name: str
    host: str
    port: int = 22
    username: str
    auth_type: str  # 'password' | 'key'
    connection_type: str  # 'ssh' | 'winrm' | 'hosting'
    panel_type: str | None = None
    credential: str  # plaintext — encrypted before storage
    tags: list[str] | None = None
    notes: str | None = None


class ServerUpdate(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    # Connection details (all optional) — provide `credential` to change the password/key.
    host: str | None = None
    port: int | None = None
    username: str | None = None
    auth_type: str | None = None     # 'password' | 'key'
    credential: str | None = None    # plaintext new secret — encrypted before storage


class ServerOut(BaseModel):
    id: uuid.UUID
    name: str
    host: str
    port: int
    username: str
    auth_type: str
    connection_type: str
    panel_type: str | None
    os_type: str | None
    os_version: str | None
    arch: str | None
    shell: str
    status: str
    tags: list[str] | None
    notes: str | None
    last_seen: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
