"""Celery tasks for durable playbook/command execution (Update 15).

The task runs in a worker process, streams output to a Redis pub/sub channel
(``run:{run_id}``), and persists the final result to the PlaybookRun row — so the
run survives the client disconnecting or the web process restarting. A WebSocket
handler subscribes to the channel and relays output to the browser.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from redis.asyncio import from_url
from sqlalchemy import select, update as sa_update

from app.celery_app import celery
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.playbook import PlaybookRun
from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)


def run_channel(run_id: str) -> str:
    return f"run:{run_id}"


async def _execute(run_id: str, server_id: str, script: str) -> None:
    """Stream the script's output to Redis and persist the result. A fresh Redis
    client is created per task (each Celery task gets its own event loop)."""
    redis = from_url(settings.REDIS_URL, decode_responses=True)
    channel = run_channel(run_id)
    output: list[str] = []
    status = "success"
    try:
        async with AsyncSessionLocal() as db:
            server = (
                await db.execute(select(Server).where(Server.id == uuid.UUID(server_id)))
            ).scalar_one_or_none()
            if server is None:
                await redis.publish(channel, json.dumps({"type": "output", "data": "ERROR: server not found\n"}))
                await redis.publish(channel, json.dumps({"type": "complete", "run_id": run_id, "status": "failed"}))
                return
            await db.execute(
                sa_update(PlaybookRun).where(PlaybookRun.id == uuid.UUID(run_id)).values(status="running")
            )
            await db.commit()

        try:
            stream = await connection_manager.execute_stream(server, script)
            async for line in stream:
                output.append(line)
                await redis.publish(channel, json.dumps({"type": "output", "data": line + "\n"}))
        except Exception as exc:  # noqa: BLE001 — CommandError (non-zero exit) or connection error
            status = "failed"
            output.append(f"ERROR: {exc}")
            await redis.publish(channel, json.dumps({"type": "output", "data": f"ERROR: {exc}\n"}))

        async with AsyncSessionLocal() as db:
            await db.execute(
                sa_update(PlaybookRun)
                .where(PlaybookRun.id == uuid.UUID(run_id))
                .values(status=status, output="\n".join(output), completed_at=datetime.now(timezone.utc))
            )
            await db.commit()

        await redis.publish(channel, json.dumps({"type": "complete", "run_id": run_id, "status": status}))
    finally:
        await redis.aclose()


@celery.task(name="run_playbook")
def run_playbook_task(run_id: str, server_id: str, script: str) -> None:
    """Celery entrypoint — runs the async executor in its own event loop."""
    asyncio.run(_execute(run_id, server_id, script))
