"""Metrics worker — collect CPU/RAM/disk from every server every 5 minutes.

Registered as an APScheduler job on application startup.
After collecting, runs alert threshold checks for each server.
Prunes metric points older than RETENTION_HOURS (7 days).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update

from app.database import AsyncSessionLocal
from app.models.alert import ServerMetric
from app.models.server import Server

logger = logging.getLogger(__name__)

# 7 days of history at 5-min intervals = 2 016 points per server
RETENTION_HOURS = 168

# A server is only marked "offline" after this many CONSECUTIVE failed checks, so a single
# transient blip (a slow SSH handshake, a momentary network drop) doesn't flap a healthy
# server to offline. Identity/credential problems are surfaced immediately — they're real,
# not transient. Counter is per-process and reset the moment the server is reachable again.
_OFFLINE_STRIKES = 2
_offline_strikes: dict[str, int] = {}


async def collect_all_metrics() -> None:
    """Entry point called by APScheduler every 5 minutes.

    1. Fetch all registered servers.
    2. Collect metrics from each (skip unreachable ones silently).
    3. Run alert checks per server.
    4. Prune old data.
    """
    from app.workers import alert_worker

    async with AsyncSessionLocal() as db:
        rows = await db.execute(select(Server))
        servers = rows.scalars().all()

    logger.info("Metrics collection run: %d servers", len(servers))

    for server in servers:
        try:
            stored = await _collect_server(server)
            if stored:
                await alert_worker.check_alerts_for_server(str(server.id))
        except Exception as exc:
            logger.debug("Skipping server %s (%s): %s", server.name, server.id, exc)

    await _prune_old_metrics()


async def _collect_server(server: Server) -> bool:
    """Collect metrics for one server and persist them.

    Returns True if data was saved, False if the server was unreachable.
    """
    from app.services import metrics_service

    try:
        data = await metrics_service.get_metrics(server)
    except Exception as exc:
        from app.services.ssh_service import is_auth_error, is_host_key_mismatch
        logger.debug("Cannot reach %s for metrics: %s", server.name, exc)
        sid = str(server.id)
        # Distinguish identity change (host-key mismatch — e.g. the server was
        # reinstalled) from stale credentials from simply unreachable, so the UI can
        # offer the right recovery (trust new key / update password / retry).
        if is_host_key_mismatch(exc):
            new_status = "host_changed"          # definitive — surface immediately
            _offline_strikes.pop(sid, None)
        elif is_auth_error(exc):
            new_status = "auth_failed"           # definitive — surface immediately
            _offline_strikes.pop(sid, None)
        else:
            # Generic "unreachable" is often a momentary blip. Only flip to offline after
            # _OFFLINE_STRIKES consecutive misses; until then keep the prior status so a
            # single slow/dropped check doesn't flap a healthy server.
            strikes = _offline_strikes.get(sid, 0) + 1
            _offline_strikes[sid] = strikes
            if strikes < _OFFLINE_STRIKES:
                logger.info(
                    "Metrics check failed for %s (%d/%d) — keeping current status, rechecking next cycle",
                    server.name, strikes, _OFFLINE_STRIKES,
                )
                return False
            new_status = "offline"
        async with AsyncSessionLocal() as db:
            await db.execute(
                sa_update(Server).where(Server.id == server.id).values(status=new_status)
            )
            await db.commit()
        return False

    # Reachable again (no connection error) — clear any pending strikes.
    _offline_strikes.pop(str(server.id), None)

    if not data or data.get("error"):
        return False

    now = datetime.now(tz=timezone.utc)

    async with AsyncSessionLocal() as db:
        metric = ServerMetric(
            server_id=server.id,
            cpu_percent=data.get("cpu_percent"),
            ram_percent=data.get("ram_percent"),
            ram_used_mb=data.get("ram_used_mb"),
            ram_total_mb=data.get("ram_total_mb"),
            disk_percent=data.get("disk_percent"),
            disk_used_gb=data.get("disk_used_gb"),
            disk_total_gb=data.get("disk_total_gb"),
            load_1=data.get("load_1"),
            load_5=data.get("load_5"),
            load_15=data.get("load_15"),
            uptime_seconds=data.get("uptime_seconds"),
        )
        db.add(metric)
        # Keep server.last_seen and status fresh
        await db.execute(
            sa_update(Server)
            .where(Server.id == server.id)
            .values(last_seen=now, status="online")
        )
        await db.commit()

    logger.debug(
        "Stored metrics for %s — CPU %.1f%% RAM %.1f%% Disk %.1f%%",
        server.name,
        float(data.get("cpu_percent") or 0),
        float(data.get("ram_percent") or 0),
        float(data.get("disk_percent") or 0),
    )
    return True


async def _prune_old_metrics() -> None:
    """Delete metric rows older than RETENTION_HOURS to prevent unbounded growth."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=RETENTION_HOURS)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            sa_delete(ServerMetric).where(ServerMetric.recorded_at < cutoff)
        )
        if result.rowcount:
            logger.info("Pruned %d old metric rows (older than %dh)", result.rowcount, RETENTION_HOURS)
        await db.commit()
