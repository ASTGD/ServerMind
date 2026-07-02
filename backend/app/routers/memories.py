"""Memories router — view and delete what Ally remembers (Ally Brain Phase 5).

Transparency is the point: no hidden brain. User-scoped notes are visible only to
their user; server-scoped notes are visible to anyone who can access that server
(shared team knowledge about the box, like the server itself).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import memory_service, team_service

router = APIRouter(prefix="/api", tags=["memories"])


class MemoryOut(BaseModel):
    id: uuid.UUID
    server_id: uuid.UUID | None
    kind: str
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.get("/memories", response_model=list[MemoryOut])
async def my_memories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MemoryOut]:
    """What Ally remembers about ME (user-scoped notes — preferences etc.)."""
    return await memory_service.list_user_memories(db, current_user.id)


@router.get("/servers/{server_id}/memories", response_model=list[MemoryOut])
async def server_memories(
    server_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MemoryOut]:
    """What Ally remembers about a server (anyone with access to the server)."""
    server = await resolve_server(server_id, current_user, db)
    return await memory_service.list_server_memories(db, server.id)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Forget one note. User-scoped: only its owner. Server-scoped: anyone with
    execute access to that server (same trust level as acting on the box)."""
    memory = await memory_service.get_memory(db, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    if memory.server_id is None:
        if memory.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Memory not found")
    else:
        access = await team_service.get_access(db, current_user, str(memory.server_id))
        if access is None or not access.can_execute:
            raise HTTPException(status_code=404, detail="Memory not found")
    await memory_service.delete_memory(db, memory)
