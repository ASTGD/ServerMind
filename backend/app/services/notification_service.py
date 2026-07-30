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
from email.utils import formatdate, make_msgid

import requests as _requests

from app.config import settings
from app.services import outbound_guard

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

#: Hosts we treat as our own mail server, reached over the loopback interface.
#:
#: A relay on localhost needs no username or password — the trust boundary is the machine
#: itself, not a credential — and typically offers no STARTTLS, because there is no network
#: hop to protect. Requiring both is what made our own mail server unusable.
_LOCAL_RELAY_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "mail", "postfix"})


def email_relay() -> str | None:
    """Which relay we would send through, or ``None`` if email cannot be delivered.

    Exposed so the product can SAY so. The old code logged a warning and returned, which
    meant a customer with no mail configured believed they were covered while every alert
    went nowhere — worse than having no alerting at all, because it is silent.
    """
    host = (settings.SMTP_HOST or "").strip()
    if not host:
        return None
    if host.lower() in _LOCAL_RELAY_HOSTS:
        return host
    # A remote relay is only usable with credentials.
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        return None
    return host


def _send_email_sync(to: str, subject: str, body_text: str, body_html: str | None = None) -> None:
    """Blocking SMTP send — runs in a thread pool. When ``body_html`` is given the
    message is multipart/alternative (plain + HTML); clients that can render HTML show
    it, the rest fall back to the plain text."""
    host = email_relay()
    if host is None:
        # ERROR, not WARNING: an alert that cannot be delivered is a failure of the thing
        # the customer is paying for, not a routine condition.
        logger.error("Email is not configured — could not deliver to %s: %s", to, subject)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    # Date and Message-ID are not optional in practice. Spam filters score mail missing
    # either of them as suspicious, and our queued messages were going out with
    # `message-id=<>` — visible in the relay's own log. The Message-ID domain is taken from
    # the sending address so it matches the DKIM signing domain.
    msg["Date"] = formatdate(localtime=False)
    _domain = settings.EMAIL_FROM.rpartition("@")[2] or "serverally.firevps.net"
    msg["Message-ID"] = make_msgid(domain=_domain)
    # Per RFC 2046, the LAST alternative is the most-preferred — attach plain first.
    msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(host, settings.SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo()
            # Upgrade only when the server actually offers it. Calling starttls() on a
            # relay that does not advertise it raises, which is how an unconditional call
            # turns a working local mail server into "SMTP error" on every send.
            if smtp.has_extn("starttls"):
                smtp.starttls()
                smtp.ehlo()
            # Only authenticate when we have something to authenticate with.
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        logger.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        logger.error("SMTP error sending to %s: %s", to, exc)
        raise


async def send_email(to: str, subject: str, body: str, html: str | None = None) -> None:
    """Async email notification. Pass ``html`` for a rich HTML alternative."""
    await asyncio.to_thread(_send_email_sync, to, subject, body, html)


# ── Webhook / Slack ───────────────────────────────────────────────────────────

def _send_webhook_sync(url: str, payload: dict) -> None:
    """Blocking HTTP POST — runs in a thread pool.

    The URL comes from the customer (an alert channel, an escalation step), so it is
    SSRF-checked immediately before the request rather than only when it was saved — see
    ``outbound_guard``. Without this, an alert target of
    ``http://169.254.169.254/latest/meta-data/`` would make our own server fetch cloud
    credentials, and ``http://postgres:5432/`` would reach the internal Docker network.
    """
    try:
        outbound_guard.check_url(url)
    except outbound_guard.BlockedURL as exc:
        logger.error("Refusing to send a webhook to %s: %s", url, exc)
        raise

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


async def fire_recovery(
    alert: object,  # Alert model instance — typed loosely to avoid circular import
    server_name: str,
    current_value: float,
) -> None:
    """Tell the customer the metric came back inside its threshold.

    Sent once, on the way down. An alert without a matching all-clear is worse than no
    alert: the person who was told the disk was filling has to go and check for themselves
    whether it still is, which is exactly the work they bought this to avoid.

    Deliberately worded as good news and marked "Resolved" in the subject, so it is
    obviously not another warning at a glance in a phone notification.
    """
    metric_label = str(alert.metric).upper()  # type: ignore[attr-defined]
    threshold = float(alert.threshold)  # type: ignore[attr-defined]
    channel = str(alert.channel)  # type: ignore[attr-defined]
    target = str(alert.channel_target)  # type: ignore[attr-defined]

    subject = (
        f"[ServerAlly] Resolved — {server_name}: {metric_label} is back to normal "
        f"({current_value:.1f}%)"
    )
    body = (
        f"ServerAlly — Resolved\n"
        f"{'=' * 40}\n\n"
        f"Server:    {server_name}\n"
        f"Metric:    {metric_label}\n"
        f"Value now: {current_value:.1f}%\n"
        f"Threshold: {threshold:.0f}%\n\n"
        f"{metric_label} is back inside your threshold. Nothing to do.\n"
    )

    if channel == "email":
        await send_email(target, subject, body)
    elif channel in ("webhook", "slack"):
        await send_webhook(target, {
            "text": subject,
            "server": server_name,
            "metric": alert.metric,          # type: ignore[attr-defined]
            "threshold": threshold,
            "current_value": round(current_value, 1),
            "status": "resolved",
            "source": "ServerAlly",
        })
    else:
        logger.warning("Unknown alert channel '%s' — no recovery notice sent", channel)


def _condition_label(condition: str) -> str:
    return {
        "gt": "above",
        "gte": "at or above",
        "lt": "below",
        "lte": "at or below",
    }.get(condition, condition)
