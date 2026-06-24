"""Celery tasks for durable playbook/command execution (Update 15).

The task runs in a worker process and appends each output message to a Redis
**list** ``run:{run_id}:log`` (a replayable backlog with a TTL), and persists the
final result to the PlaybookRun row. A WebSocket handler *tails* that list — so a
run survives the client disconnecting, and a reconnecting client can replay
everything it missed (slice 2). The run also survives a web-process restart.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis, from_url
from sqlalchemy import select, update as sa_update

from app.celery_app import celery
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.playbook import PlaybookRun
from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)


def run_log_key(run_id: str) -> str:
    return f"run:{run_id}:log"


async def _emit(redis: Redis, key: str, message: dict) -> None:
    """Append one message to the run's replay log and refresh its TTL."""
    await redis.rpush(key, json.dumps(message))
    await redis.expire(key, settings.EXECUTION_LOG_TTL)


async def _execute(run_id: str, server_id: str, script: str) -> None:
    """Stream the script's output into the Redis log and persist the result. A
    fresh Redis client is used per task (each Celery task gets its own loop)."""
    redis = from_url(settings.REDIS_URL, decode_responses=True)
    key = run_log_key(run_id)
    output: list[str] = []
    status = "success"
    try:
        async with AsyncSessionLocal() as db:
            server = (
                await db.execute(select(Server).where(Server.id == uuid.UUID(server_id)))
            ).scalar_one_or_none()
            if server is None:
                await _emit(redis, key, {"type": "output", "data": "ERROR: server not found\n"})
                await _emit(redis, key, {"type": "complete", "run_id": run_id, "status": "failed"})
                return
            await db.execute(
                sa_update(PlaybookRun).where(PlaybookRun.id == uuid.UUID(run_id)).values(status="running")
            )
            await db.commit()

        cancel_key = f"run:{run_id}:cancel"
        try:
            stream = await connection_manager.execute_stream(server, script)
            async for line in stream:
                if await redis.exists(cancel_key):
                    break
                output.append(line)
                await _emit(redis, key, {"type": "output", "data": line + "\n"})
        except Exception as exc:  # noqa: BLE001 — CommandError (non-zero exit) or connection error
            status = "failed"
            output.append(f"ERROR: {exc}")
            await _emit(redis, key, {"type": "output", "data": f"ERROR: {exc}\n"})
        # Honour a cancel requested via the HTTP endpoint (flag set in Redis).
        if await redis.exists(cancel_key):
            status = "cancelled"
            await _emit(redis, key, {"type": "output", "data": "⏹ Cancelled by user\n"})
        await redis.delete(cancel_key)

        async with AsyncSessionLocal() as db:
            await db.execute(
                sa_update(PlaybookRun)
                .where(PlaybookRun.id == uuid.UUID(run_id))
                .values(status=status, output="\n".join(output), completed_at=datetime.now(timezone.utc))
            )
            await db.commit()

        await _emit(redis, key, {"type": "complete", "run_id": run_id, "status": status})
    finally:
        await redis.aclose()


@celery.task(name="run_playbook")
def run_playbook_task(run_id: str, server_id: str, script: str) -> None:
    """Celery entrypoint — runs the async executor in its own event loop."""
    asyncio.run(_execute(run_id, server_id, script))
