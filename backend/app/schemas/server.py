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
