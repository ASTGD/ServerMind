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


async def _notify(db, alert, server_name: str, value: float, *, recovered: bool) -> None:
    """Send through the alert's named channel if it has one, else its inline destination.

    Both paths exist because rules created before channels carry their own copy of the
    destination, and a migration could only guess which named channel the customer meant.
    A named channel wins when set; nothing else changes.
    """
    from app.models.notification_channel import NotificationChannel
    from app.services import channel_service, notification_service

    if alert.channel_id:
        row = await db.execute(
            select(NotificationChannel).where(NotificationChannel.id == alert.channel_id)
        )
        ch = row.scalar_one_or_none()
        if ch is not None and ch.is_active:
            metric = str(alert.metric).upper()
            if recovered:
                subject = f"Resolved — {server_name}: {metric} is back to normal"
                body = f"{metric} is {value:.1f}%, inside your threshold. Nothing to do."
            else:
                subject = f"{server_name}: {metric} is {value:.1f}%"
                body = (f"{metric} is past your {float(alert.threshold):.0f}% threshold.")
            try:
                await channel_service.deliver(db, ch, subject=subject, body=body)
                await channel_service.record_result(db, ch, error=None)
            except Exception as exc:  # noqa: BLE001 — record it, do not lose the alert
                await channel_service.record_result(db, ch, error=str(exc))
                raise
            return

    # No channel named (or it was deleted) — the original inline path, unchanged.
    if recovered:
        await notification_service.fire_recovery(alert, server_name, value)
    else:
        await notification_service.fire_alert(alert, server_name, value)


async def check_alerts_for_server(server_id: str) -> None:
    """Compare the server's latest metric snapshot against all active alert rules.

    Fires a notification when a threshold is breached and the cooldown has elapsed.
    """
    from app.services import incident_service, notification_service

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
                # Back inside the threshold — close any incident this rule opened, so a
                # disk that was cleared stops paging without anyone having to acknowledge.
                try:
                    await incident_service.resolve_key(db, alert.user_id, f"metric:{alert.id}")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Metric incident close failed for %s: %s", alert.id, exc)

                # And say so, once. Being told a disk filled up but never that it was
                # sorted leaves someone checking manually — which is the job they bought
                # this to avoid. Only on the transition down: `is_breaching` is what keeps
                # this from repeating every sweep forever.
                if alert.is_breaching:
                    logger.info("Alert recovered — server=%s metric=%s value=%.1f",
                                server.name, alert.metric, current_value)
                    try:
                        await _notify(db, alert, server.name, current_value,
                                      recovered=True)
                    except Exception as exc:  # noqa: BLE001 — never block clearing the flag
                        logger.warning("Recovery notice failed for alert %s: %s",
                                       alert.id, exc)
                    await db.execute(
                        sa_update(Alert).where(Alert.id == alert.id)
                        .values(is_breaching=False)
                    )
                    await db.commit()
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
                # A metric threshold is a warning by nature — the disk is filling, not the
                # site is down — so it escalates only if the user's policy asks to be paged
                # about warnings. Otherwise it stays the ordinary one-shot alert.
                escalated = False
                try:
                    escalated = await incident_service.raise_for(
                        db, user_id=alert.user_id, server=server, source="metric",
                        dedup_key=f"metric:{alert.id}",
                        title=f"{server.name}: {str(alert.metric).upper()} is "
                              f"{current_value:.0f}%",
                        message=(f"{str(alert.metric).upper()} is {current_value:.1f}%, which "
                                 f"is past your {float(alert.threshold):.0f}% threshold."),
                        severity="warning",
                    ) is not None
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Metric escalation failed for alert %s: %s", alert.id, exc)

                if not escalated:
                    await _notify(db, alert, server.name, current_value,
                                  recovered=False)
                # Set inside the fire block, i.e. AFTER the cooldown check, so a breach we
                # deliberately stayed quiet about can never produce a "back to normal"
                # message for something the customer was never told about.
                await db.execute(
                    sa_update(Alert)
                    .where(Alert.id == alert.id)
                    .values(last_triggered=now, is_breaching=True)
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
