"""Named notification channels — validate, store, and deliver to them.

The delivery functions themselves already existed and are reused unchanged; what is new is
that a destination is configured ONCE and referred to by name.

Two properties this file is responsible for:

* **A channel's settings never leave the server.** A Slack webhook URL lets anyone post into
  the customer's workspace and a Telegram bot token is full control of the bot, so the
  config is encrypted at rest and every API payload is built from an explicit allowlist —
  never a model dump, which would publish the next field somebody adds.
* **A channel is not assumed to work.** It is unverified until a real test message has been
  delivered. Alerting that silently goes nowhere is the failure this whole feature exists to
  prevent, so "probably fine" is not a state we record.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_channel import CHANNEL_KINDS, NotificationChannel
from app.services import crypto_service

logger = logging.getLogger(__name__)


class ChannelError(Exception):
    """Something the customer can read and act on."""


#: What each kind needs before it can possibly work. Checked at the write boundary, so a
#: channel that cannot deliver can never be saved in the first place.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "email": ("address",),
    "slack": ("webhook_url",),
    "telegram": ("bot_token", "chat_id"),
    # Twilio's account credentials are account-wide and live in `notification_providers`;
    # only the destination belongs here.
    "sms": ("phone",),
}

#: Which parts of a config may be shown back to the customer.
#:
#: An allowlist, not a blocklist. The reason is that a blocklist silently leaks whatever
#: field is added next, and the fields at stake here — a webhook URL, a bot token — are
#: credentials, not settings.
SAFE_FIELDS: dict[str, tuple[str, ...]] = {
    "email": ("address",),
    "slack": (),        # the webhook URL IS the credential
    "telegram": ("chat_id",),
    "sms": ("phone",),
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PHONE_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def valid_kind(kind: str) -> str:
    k = (kind or "").strip().lower()
    if k not in CHANNEL_KINDS:
        raise ChannelError(
            f"'{kind}' is not a channel type we support. Choose one of: "
            + ", ".join(CHANNEL_KINDS) + "."
        )
    return k


def valid_label(label: str) -> str:
    v = (label or "").strip()
    if not v:
        raise ChannelError("Give this channel a name so you can recognise it later.")
    if len(v) > 80:
        raise ChannelError("That name is too long — keep it under 80 characters.")
    return v


def clean_config(kind: str, config: dict[str, Any]) -> dict[str, str]:
    """Validate and normalise a channel's settings, or explain what is wrong.

    Refusing here rather than at send time is deliberate: a channel saved with a typo'd
    address looks configured on screen and fails silently at 2am, which is the exact
    failure mode this feature is meant to remove.
    """
    kind = valid_kind(kind)
    cfg = {k: str(v).strip() for k, v in (config or {}).items() if v is not None}

    missing = [f for f in REQUIRED_FIELDS[kind] if not cfg.get(f)]
    if missing:
        raise ChannelError(
            "This channel is missing " + ", ".join(missing.__iter__()) + "."
        )

    if kind == "email":
        if not _EMAIL_RE.match(cfg["address"]):
            raise ChannelError(f"'{cfg['address']}' does not look like an email address.")

    elif kind == "slack":
        url = cfg["webhook_url"]
        if not url.startswith("https://hooks.slack.com/"):
            raise ChannelError(
                "That is not a Slack webhook URL. In Slack, create an Incoming Webhook — "
                "the URL starts with https://hooks.slack.com/."
            )

    elif kind == "telegram":
        # A bot token looks like 123456789:AAE... — catching the shape here saves the
        # customer a silent failure later.
        if ":" not in cfg["bot_token"] or len(cfg["bot_token"]) < 20:
            raise ChannelError(
                "That does not look like a Telegram bot token. BotFather gives you one "
                "that looks like 123456789:AAExxxxxxxxxxxxxxxxxxxxxxxx."
            )

    elif kind == "sms":
        if not _PHONE_RE.match(cfg["phone"]):
            raise ChannelError(
                "Write the phone number in international format, starting with + and the "
                "country code — for example +8801712345678."
            )

    # Drop anything we did not ask for rather than storing a field we will never read.
    return {f: cfg[f] for f in REQUIRED_FIELDS[kind]}


def load_config(channel: NotificationChannel) -> dict[str, str]:
    try:
        return json.loads(crypto_service.decrypt(channel.encrypted_config))
    except Exception as exc:  # noqa: BLE001
        raise ChannelError("This channel's settings could not be read.") from exc


def public(channel: NotificationChannel) -> dict:
    """What an endpoint may return — an allowlist, never a model dump."""
    try:
        cfg = load_config(channel)
    except ChannelError:
        cfg = {}
    return {
        "id": str(channel.id),
        "kind": channel.kind,
        "label": channel.label,
        "is_active": channel.is_active,
        "verified_at": channel.verified_at.isoformat() if channel.verified_at else None,
        "last_error": channel.last_error,
        "last_used_at": channel.last_used_at.isoformat() if channel.last_used_at else None,
        "created_at": channel.created_at.isoformat() if channel.created_at else None,
        # Only the parts that are a destination rather than a credential.
        "details": {f: cfg.get(f, "") for f in SAFE_FIELDS[channel.kind]},
    }


async def list_for_user(db: AsyncSession, user_id) -> list[NotificationChannel]:
    rows = await db.execute(
        select(NotificationChannel)
        .where(NotificationChannel.user_id == user_id)
        .order_by(NotificationChannel.created_at.asc())
    )
    return list(rows.scalars().all())


async def create(db: AsyncSession, user_id, *, kind: str, label: str,
                 config: dict[str, Any]) -> NotificationChannel:
    kind = valid_kind(kind)
    label = valid_label(label)
    cfg = clean_config(kind, config)

    existing = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.user_id == user_id,
            NotificationChannel.label == label,
        )
    )
    if existing.scalar_one_or_none():
        raise ChannelError(f"You already have a channel called '{label}'.")

    ch = NotificationChannel(
        user_id=user_id, kind=kind, label=label,
        encrypted_config=crypto_service.encrypt(json.dumps(cfg)),
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)
    return ch


async def delete(db: AsyncSession, channel: NotificationChannel) -> None:
    await db.delete(channel)
    await db.commit()


# ── Delivery ──────────────────────────────────────────────────────────────────

async def deliver(db: AsyncSession, channel: NotificationChannel, *,
                  subject: str, body: str) -> None:
    """Send one message through this channel. Raises ChannelError on failure.

    Each kind reuses the sender that already existed, so there is one implementation of
    "talk to Slack", not two.
    """
    from app.services import notification_service, paging_service  # circular at import time

    cfg = load_config(channel)
    kind = channel.kind

    if kind == "email":
        # `send_email` deliberately does NOT raise when mail is unconfigured — every other
        # caller treats email as best-effort and must not be broken by it. But here silence
        # is the bug: without this check a test "succeeded", the channel was marked Working,
        # and nothing had been sent. Caught by pressing the button on a machine with no mail
        # configured, which is exactly the state production was in.
        if notification_service.email_relay() is None:
            raise ChannelError(
                "Email is not set up on this ServerAlly, so nothing could be sent. "
                "Ask your administrator to configure a mail server."
            )
        await notification_service.send_email(cfg["address"], subject, body)

    elif kind == "slack":
        await notification_service.send_webhook(cfg["webhook_url"], {"text": f"{subject}\n{body}"})

    elif kind == "telegram":
        await paging_service.send_telegram_direct(
            bot_token=cfg["bot_token"], chat_id=cfg["chat_id"], text=f"{subject}\n\n{body}")

    elif kind == "sms":
        # Costs real money, so it goes through the existing metered path rather than a
        # second one that would not count against the monthly ceiling.
        await paging_service.send_sms(db, channel.user_id, cfg["phone"], f"{subject} — {body}")

    else:  # pragma: no cover — valid_kind guards the write path
        raise ChannelError(f"Cannot send to a '{kind}' channel.")


async def record_result(db: AsyncSession, channel: NotificationChannel, *,
                        error: str | None) -> None:
    """Remember whether the last send worked, so the UI can show it."""
    now = datetime.now(tz=timezone.utc)
    channel.last_used_at = now
    channel.last_error = (error or "")[:300] or None
    if error is None:
        channel.verified_at = now
    await db.commit()


async def send_test(db: AsyncSession, channel: NotificationChannel) -> None:
    """Prove the channel really reaches somebody, and record the outcome either way."""
    try:
        await deliver(
            db, channel,
            subject="ServerAlly test message",
            body=("This is a test from ServerAlly. If you are reading it, alerts about your "
                  "servers can reach you here."),
        )
    except Exception as exc:  # noqa: BLE001 — the failure is the answer, not an error
        await record_result(db, channel, error=str(exc))
        raise ChannelError(f"Could not send to this channel: {exc}") from exc
    await record_result(db, channel, error=None)
