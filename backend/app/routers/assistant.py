"""Assistant threads router — saved AI-assistant conversations (Phase 2).

Simple, user-scoped CRUD over ``assistant_threads``. Messages are stored inline as a
JSONB list; the frontend appends turns as the conversation happens and reloads a thread
to revisit it.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.assistant_thread import AssistantThread
from app.models.user import User

router = APIRouter(tags=["assistant"])

# Bound thread growth: messages live inline in a JSONB column (read-modify-write on
# every append), so cap both the message count and per-message size to keep threads —
# and the shared DB — from being bloated by a single account.
_MAX_MESSAGES_PER_THREAD = 500
_MAX_CONTENT_CHARS = 20000


class ThreadCreate(BaseModel):
    title: str | None = None


class ThreadRename(BaseModel):
    title: str


class MessageAppend(BaseModel):
    role: str
    content: str = Field(max_length=_MAX_CONTENT_CHARS)


def _summary(t: AssistantThread) -> dict:
    return {
        "id": str(t.id),
        "title": t.title,
        "updated_at": t.updated_at,
        "message_count": len(t.messages or []),
    }


async def _get_owned(db: AsyncSession, user: User, thread_id: str) -> AssistantThread:
    try:
        tid = uuid.UUID(thread_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Thread not found")
    t = (
        await db.execute(
            select(AssistantThread).where(
                AssistantThread.id == tid, AssistantThread.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t


@router.get("/api/assistant/threads")
async def list_threads(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[dict]:
    rows = (
        await db.execute(
            select(AssistantThread)
            .where(AssistantThread.user_id == user.id)
            .order_by(AssistantThread.updated_at.desc())
        )
    ).scalars().all()
    return [_summary(t) for t in rows]


@router.post("/api/assistant/threads", status_code=201)
async def create_thread(
    body: ThreadCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    t = AssistantThread(user_id=user.id, title=(body.title or "New chat")[:255], messages=[])
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return {"id": str(t.id), "title": t.title, "messages": [], "updated_at": t.updated_at}


@router.get("/api/assistant/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    t = await _get_owned(db, user, thread_id)
    return {"id": str(t.id), "title": t.title, "messages": t.messages or [], "updated_at": t.updated_at}


@router.patch("/api/assistant/threads/{thread_id}")
async def rename_thread(
    thread_id: str,
    body: ThreadRename,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    t = await _get_owned(db, user, thread_id)
    t.title = (body.title.strip() or "New chat")[:255]
    await db.commit()
    return {"id": str(t.id), "title": t.title}


@router.delete("/api/assistant/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    t = await _get_owned(db, user, thread_id)
    await db.delete(t)
    await db.commit()


@router.post("/api/assistant/threads/{thread_id}/messages", status_code=201)
async def append_message(
    thread_id: str,
    body: MessageAppend,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    t = await _get_owned(db, user, thread_id)
    msgs = list(t.messages or [])
    if len(msgs) >= _MAX_MESSAGES_PER_THREAD:
        raise HTTPException(status_code=409, detail="This conversation is full — start a new chat.")
    role = "user" if body.role == "user" else "assistant"
    msgs.append({"role": role, "content": body.content})
    t.messages = msgs
    flag_modified(t, "messages")
    # Auto-title the thread from its first user message.
    if role == "user" and t.title in (None, "", "New chat"):
        t.title = (body.content.strip()[:60] or "New chat")
    await db.commit()
    return {"ok": True, "title": t.title}
