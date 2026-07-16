"""Ally's long-term memory (Ally Brain Phase 5).

Short notes Ally saves while working with the user — server facts, user preferences,
lessons from failures — so the next conversation starts smarter. Design rules:

- **Never secrets.** The chat prompt forbids it AND :func:`_looks_secret` filters every
  note before saving; anything that smells like a credential is dropped, not stored.
- **User-visible, user-deletable.** No hidden brain: list + delete endpoints back a
  "What Ally remembers" UI.
- **Bounded.** Hard caps per scope with oldest-first eviction; duplicate notes refresh
  the existing row instead of piling up.
- **Data, not instructions.** Injection framing lives in ai_service; a saved note can
  never smuggle a command.
- **Best-effort.** Like metering: a memory failure must never break the chat itself.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ally_memory import AllyMemory
from app.services import safety_service

logger = logging.getLogger(__name__)

MAX_SERVER_NOTES = 30
MAX_USER_NOTES = 20
MAX_NOTE_CHARS = 300
_KINDS = ("fact", "preference", "lesson")

# Conservative secret smells — better to drop a real memory than store a credential.
_SECRET_PATTERNS = [
    re.compile(r"-----BEGIN"),                                   # PEM keys
    re.compile(r"(password|passwd|passphrase)\s*(is|[:=])\s*\S", re.I),
    re.compile(r"(secret|token|api[_-]?key|access[_-]?key)\s*(is|[:=])\s*\S", re.I),
    re.compile(r"\b(sk|pk)-[A-Za-z0-9]{8,}"),                    # provider-style keys
    re.compile(r"\bsm_live_[A-Za-z0-9_-]+"),                     # our own gateway tokens
    re.compile(r"[A-Za-z0-9+/_-]{40,}"),                         # long random blobs
]


def _looks_secret(text: str) -> bool:
    return any(p.search(text) for p in _SECRET_PATTERNS)


async def save_from_ai(
    db: AsyncSession,
    *,
    user_id,
    remember: object,
    server_id=None,
) -> None:
    """Persist a ``remember`` value Ally emitted in its JSON reply.

    Accepts ``{"kind": "fact|preference|lesson", "note": "..."}`` or a plain string
    (kind defaults to 'fact'). Scope: preferences are about the PERSON → always
    user-scoped; facts/lessons stick to the server when one is in context.
    Best-effort: validation failures and secret smells are dropped silently (logged).
    """
    try:
        if isinstance(remember, str):
            kind, note = "fact", remember
        elif isinstance(remember, dict):
            kind = str(remember.get("kind", "fact")).lower()
            note = remember.get("note", "")
        else:
            return
        if not isinstance(note, str):
            return
        note = " ".join(note.split()).strip()  # collapse whitespace/newlines
        if not note or len(note) < 8:
            return
        if kind not in _KINDS:
            kind = "fact"
        note = note[:MAX_NOTE_CHARS]
        if _looks_secret(note):
            logger.info("ally memory dropped — looked like a secret (user=%s)", user_id)
            return

        scope_server_id = None if kind == "preference" else server_id

        # Duplicate → refresh the existing row instead of stacking copies.
        existing = (
            await db.execute(
                select(AllyMemory).where(
                    AllyMemory.user_id == user_id,
                    AllyMemory.server_id.is_(None)
                    if scope_server_id is None
                    else AllyMemory.server_id == scope_server_id,
                    AllyMemory.content == note,
                )
            )
        ).scalars().first()
        now = datetime.now(timezone.utc)
        if existing:
            existing.updated_at = now
            existing.last_used_at = now
            await db.commit()
            return

        db.add(AllyMemory(user_id=user_id, server_id=scope_server_id, kind=kind, content=note))
        await db.commit()
        await _evict_over_cap(db, user_id=user_id, server_id=scope_server_id)
    except Exception as exc:  # noqa: BLE001 — memory must never break the chat
        logger.warning("ally memory save failed (user=%s): %s", user_id, exc)


MAX_ACTION_NOTE_CHARS = 200


async def record_action(
    db: AsyncSession,
    *,
    user_id,
    server_id,
    commands: object,
    status: str | None,
) -> None:
    """Auto-record a CRITICAL change Ally just made — no model cooperation needed.

    The chat prompt ASKS Ally to `remember` its cleanups, but a prompt is a request, not
    a guarantee: BUG-001 was exactly the model failing to record its own quarantine and
    then, a day later, nearly restoring a 10-month-old backup over a live site. This is
    the code-level floor under that prompt.

    Deliberately NARROW. ``ally_memories`` is capped per server and injected into every
    prompt, so flooding it with routine work would evict the curated facts and make the
    memory feature worse. Only a HIGH-RISK command that actually CHANGED the server and
    SUCCEEDED earns a permanent note; ordinary work is recalled from ``command_logs``
    via the server profile instead (see ai_context_service._actions_done).

    Best-effort, like the rest of memory: a failure here must never break the chat.
    """
    if status != "success" or not isinstance(commands, list):
        return
    try:
        for c in commands:
            if not isinstance(c, dict):
                continue
            cmd = (c.get("cmd") or "").strip()
            if not cmd:
                continue
            if str(c.get("risk_level", "")).lower() != "high":
                continue        # only the big, lasting ones
            if safety_service.is_read_only_command(cmd):
                continue        # looked, didn't change
            desc = " ".join((c.get("description") or cmd).split())
            if not desc:
                continue
            day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            note = f"ServerAlly did this on {day}: {desc}"[:MAX_ACTION_NOTE_CHARS]
            # save_from_ai gives us the secret filter, dedupe and cap-eviction for free.
            await save_from_ai(
                db, user_id=user_id, remember={"kind": "fact", "note": note},
                server_id=server_id,
            )
            return   # one note per action, not one per command
    except Exception as exc:  # noqa: BLE001 — memory must never break the chat
        logger.warning("ally action record failed (user=%s): %s", user_id, exc)


async def _evict_over_cap(db: AsyncSession, *, user_id, server_id) -> None:
    """Keep the newest MAX notes per scope; drop the stalest beyond the cap."""
    if server_id is not None:
        q = select(AllyMemory).where(AllyMemory.server_id == server_id)
        cap = MAX_SERVER_NOTES
    else:
        q = select(AllyMemory).where(AllyMemory.user_id == user_id, AllyMemory.server_id.is_(None))
        cap = MAX_USER_NOTES
    rows = (await db.execute(q.order_by(AllyMemory.updated_at.desc()))).scalars().all()
    if len(rows) > cap:
        stale_ids = [m.id for m in rows[cap:]]
        await db.execute(delete(AllyMemory).where(AllyMemory.id.in_(stale_ids)))
        await db.commit()


async def _touch(db: AsyncSession, ids: list) -> None:
    if ids:
        await db.execute(
            update(AllyMemory)
            .where(AllyMemory.id.in_(ids))
            .values(last_used_at=datetime.now(timezone.utc))
        )
        await db.commit()


async def block_for_server(db: AsyncSession, server_id, acting_user_id) -> str | None:
    """The memory text for a per-server chat: notes about this server (shared team
    knowledge) + the acting user's own preferences. Marks the notes as used."""
    server_notes = (
        await db.execute(
            select(AllyMemory)
            .where(AllyMemory.server_id == server_id)
            .order_by(AllyMemory.updated_at.desc())
            .limit(MAX_SERVER_NOTES)
        )
    ).scalars().all()
    prefs = (
        await db.execute(
            select(AllyMemory)
            .where(
                AllyMemory.user_id == acting_user_id,
                AllyMemory.server_id.is_(None),
                AllyMemory.kind == "preference",
            )
            .order_by(AllyMemory.updated_at.desc())
            .limit(MAX_USER_NOTES)
        )
    ).scalars().all()
    lines: list[str] = []
    if server_notes:
        lines.append("Notes about this server:")
        lines += [f"- {m.content}" for m in server_notes]
    if prefs:
        lines.append("User preferences:")
        lines += [f"- {m.content}" for m in prefs]
    if not lines:
        return None
    await _touch(db, [m.id for m in server_notes] + [m.id for m in prefs])
    return "\n".join(lines)


async def block_for_user(db: AsyncSession, user_id) -> str | None:
    """The memory text for fleet chat: everything user-scoped. Marks notes as used."""
    notes = (
        await db.execute(
            select(AllyMemory)
            .where(AllyMemory.user_id == user_id, AllyMemory.server_id.is_(None))
            .order_by(AllyMemory.updated_at.desc())
            .limit(MAX_USER_NOTES)
        )
    ).scalars().all()
    if not notes:
        return None
    await _touch(db, [m.id for m in notes])
    return "\n".join(f"- {m.content}" for m in notes)


# ── For the view/delete API ──────────────────────────────────────────────────

async def list_user_memories(db: AsyncSession, user_id) -> list[AllyMemory]:
    return (
        await db.execute(
            select(AllyMemory)
            .where(AllyMemory.user_id == user_id, AllyMemory.server_id.is_(None))
            .order_by(AllyMemory.updated_at.desc())
        )
    ).scalars().all()


async def list_server_memories(db: AsyncSession, server_id) -> list[AllyMemory]:
    return (
        await db.execute(
            select(AllyMemory)
            .where(AllyMemory.server_id == server_id)
            .order_by(AllyMemory.updated_at.desc())
        )
    ).scalars().all()


async def get_memory(db: AsyncSession, memory_id) -> AllyMemory | None:
    return (
        await db.execute(select(AllyMemory).where(AllyMemory.id == memory_id))
    ).scalar_one_or_none()


async def delete_memory(db: AsyncSession, memory: AllyMemory) -> None:
    await db.delete(memory)
    await db.commit()
