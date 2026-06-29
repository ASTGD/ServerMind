"""Notification service — email and webhook alert delivery.

Supports:
  - email    → SMTP (smtplib via asyncio.to_thread)
  - webhook  → HTTP POST JSON to any URL
  - slack    → Slack incoming webhook (same POST format, different payload)
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests as _requests

from app.config import settings

logger = logging.getLogger(__name__)


async def create_run_notification(db, run_id) -> None:
    """Create an in-app notification when a playbook/script run finishes
    (Update 17, Phase 2). Best-effort — never raises into the run path."""
    from sqlalchemy import select

    from app.models.notification import Notification
    from app.models.playbook import Playbook, PlaybookRun, UserScript
    from app.models.server import Server

    try:
        run = (await db.execute(select(PlaybookRun).where(PlaybookRun.id == run_id))).scalar_one_or_none()
        if run is None:
            return
        name = "Playbook"
        if run.playbook_id:
            name = (await db.execute(select(Playbook.title).where(Playbook.id == run.playbook_id))).scalar_one_or_none() or name
        elif run.user_script_id:
            name = (await db.execute(select(UserScript.title).where(UserScript.id == run.user_script_id))).scalar_one_or_none() or name
        server_name = (await db.execute(select(Server.name).where(Server.id == run.server_id))).scalar_one_or_none() or "the server"
        status = run.status or "done"
        verb = {
            "success": "finished",
            "failed": "failed",
            "stalled": "stopped responding",
            "cancelled": "was cancelled",
        }.get(status, "finished")
        db.add(Notification(
            user_id=run.user_id, type="playbook_run", status=status,
            title=f"{name} {verb}", body=f"on {server_name}",
            server_id=run.server_id, ref_id=run.id,
        ))
        await db.commit()
    except Exception:  # noqa: BLE001 — notifications must never break a run
        logger.warning("Failed to create run notification for %s", run_id, exc_info=True)


# ── Email ─────────────────────────────────────────────────────────────────────

def _send_email_sync(to: str, subject: str, body_text: str) -> None:
    """Blocking SMTP send — runs in a thread pool."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured — skipping email to %s", to)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg.attach(MIMEText(body_text, "plain"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        logger.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        logger.error("SMTP error sending to %s: %s", to, exc)
        raise


async def send_email(to: str, subject: str, body: str) -> None:
    """Async email notification."""
    await asyncio.to_thread(_send_email_sync, to, subject, body)


# ── Webhook / Slack ───────────────────────────────────────────────────────────

def _send_webhook_sync(url: str, payload: dict) -> None:
    """Blocking HTTP POST — runs in a thread pool."""
    try:
        resp = _requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Webhook delivered to %s (status %d)", url, resp.status_code)
    except Exception as exc:
        logger.error("Webhook error to %s: %s", url, exc)
        raise


async def send_webhook(url: str, payload: dict) -> None:
    """Async webhook / Slack notification."""
    await asyncio.to_thread(_send_webhook_sync, url, payload)


# ── Unified alert dispatch ─────────────────────────────────────────────────────

async def fire_alert(
    alert: object,  # Alert model instance — typed loosely to avoid circular import
    server_name: str,
    current_value: float,
) -> None:
    """Send an alert notification through the channel configured on the alert rule."""
    metric_label = str(alert.metric).upper()  # type: ignore[attr-defined]
    condition_label = _condition_label(str(alert.condition))  # type: ignore[attr-defined]
    threshold = float(alert.threshold)  # type: ignore[attr-defined]
    channel = str(alert.channel)  # type: ignore[attr-defined]
    target = str(alert.channel_target)  # type: ignore[attr-defined]

    subject = (
        f"[ServerAlly] {server_name}: {metric_label} {condition_label} "
        f"{threshold:.0f}% (currently {current_value:.1f}%)"
    )
    body = (
        f"ServerAlly Alert\n"
        f"{'=' * 40}\n\n"
        f"Server:    {server_name}\n"
        f"Metric:    {metric_label}\n"
        f"Condition: {condition_label} {threshold:.0f}%\n"
        f"Value now: {current_value:.1f}%\n\n"
        f"Log in to ServerAlly to investigate.\n"
    )

    if channel == "email":
        await send_email(target, subject, body)

    elif channel in ("webhook", "slack"):
        payload: dict = {
            "text": subject,
            "server": server_name,
            "metric": alert.metric,  # type: ignore[attr-defined]
            "condition": alert.condition,  # type: ignore[attr-defined]
            "threshold": threshold,
            "current_value": round(current_value, 1),
            "source": "ServerAlly",
        }
        # Slack uses `text` at top level; generic webhooks get the full dict
        await send_webhook(target, payload)

    else:
        logger.warning("Unknown alert channel '%s' — no notification sent", channel)


def _condition_label(condition: str) -> str:
    return {
        "gt": "above",
        "gte": "at or above",
        "lt": "below",
        "lte": "at or below",
    }.get(condition, condition)
