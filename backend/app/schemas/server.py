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
    category: str | None = None  # 'bare_metal'|'vps'|'hosting'|'windows'|'cloud' (inferred if omitted)
    credential: str  # plaintext — encrypted before storage
    tags: list[str] | None = None
    notes: str | None = None


class ServerUpdate(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    notes: str | None = None
    category: str | None = None      # re-file an asset into another category
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
    category: str | None
    os_type: str | None
    os_version: str | None
    arch: str | None
    shell: str
    rdp_enabled: bool = False       # Windows Remote Desktop opt-in (Phase E)
    status: str
    tags: list[str] | None
    notes: str | None
    last_seen: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
