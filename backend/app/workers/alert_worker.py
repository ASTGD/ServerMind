"""Alert worker — evaluate active alert rules against the latest server metrics."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy import update as sa_update

from app.database import AsyncSessionLocal
from app.models.alert import Alert, ServerMetric
from app.models.server import Server

logger = logging.getLogger(__name__)

# Re-fire the same alert at most once per hour
COOLDOWN_SECONDS = 3600


async def check_alerts_for_server(server_id: str) -> None:
    """Compare the server's latest metric snapshot against all active alert rules.

    Fires a notification when a threshold is breached and the cooldown has elapsed.
    """
    from app.services import notification_service

    server_uuid = uuid.UUID(server_id)

    async with AsyncSessionLocal() as db:
        # Latest metric snapshot
        m_row = await db.execute(
            select(ServerMetric)
            .where(ServerMetric.server_id == server_uuid)
            .order_by(ServerMetric.recorded_at.desc())
            .limit(1)
        )
        metric = m_row.scalar_one_or_none()
        if not metric:
            return

        # Server name for notification text
        srv_row = await db.execute(select(Server).where(Server.id == server_uuid))
        server = srv_row.scalar_one_or_none()
        if not server:
            return

        # All active alert rules for this server
        a_row = await db.execute(
            select(Alert).where(
                Alert.server_id == server_uuid,
                Alert.is_active == True,  # noqa: E712
            )
        )
        alerts = a_row.scalars().all()

        now = datetime.now(tz=timezone.utc)

        for alert in alerts:
            current_value = _metric_value(metric, str(alert.metric))
            if current_value is None:
                continue

            if not _breached(current_value, str(alert.condition), float(alert.threshold)):
                continue

            # Cooldown check — skip if we already fired within COOLDOWN_SECONDS
            if alert.last_triggered:
                last_ts = alert.last_triggered
                if last_ts.tzinfo is None:
                    last_ts = last_ts.replace(tzinfo=timezone.utc)
                elapsed = (now - last_ts).total_seconds()
                if elapsed < COOLDOWN_SECONDS:
                    logger.debug(
                        "Alert %s in cooldown (%.0fs remaining)",
                        alert.id,
                        COOLDOWN_SECONDS - elapsed,
                    )
                    continue

            logger.info(
                "Alert fired — server=%s metric=%s value=%.1f %s %.1f",
                server.name,
                alert.metric,
                current_value,
                alert.condition,
                float(alert.threshold),
            )

            try:
                await notification_service.fire_alert(alert, server.name, current_value)
                await db.execute(
                    sa_update(Alert)
                    .where(Alert.id == alert.id)
                    .values(last_triggered=now)
                )
                await db.commit()
            except Exception as exc:
                logger.error("Failed to deliver alert %s: %s", alert.id, exc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _metric_value(metric: ServerMetric, metric_name: str) -> float | None:
    """Extract a float value from a metric snapshot by name."""
    val = {
        "cpu": metric.cpu_percent,
        "ram": metric.ram_percent,
        "disk": metric.disk_percent,
    }.get(metric_name)
    return float(val) if val is not None else None


def _breached(value: float, condition: str, threshold: float) -> bool:
    """Return True when the alert condition is satisfied."""
    return {
        "gt": value > threshold,
        "gte": value >= threshold,
        "lt": value < threshold,
        "lte": value <= threshold,
    }.get(condition, False)
