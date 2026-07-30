"""Sending a page — SMS, Telegram, and the money rail around SMS.

Email, Slack and webhooks already exist in ``notification_service``. This module adds the
two channels that actually wake somebody up, and the guard rails that make it safe to offer
them:

- **SMS costs real money on every message.** Every other channel in the product is free, so
  this is the first place where a bug could produce a bill. It gets a hard per-calendar-month
  ceiling, checked and incremented under the same transaction that sends, and a page that
  would exceed it is refused rather than queued.
- **Provider credentials are AES-256-GCM at rest** and never returned by any endpoint —
  the same rule as server credentials and backup destinations.
- **A failure never raises.** A channel that is down must not stop the rest of the ladder;
  the point of having three rungs is that one of them working is enough.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import requests as _requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escalation import NotificationProvider
from app.services import crypto_service, notification_service

logger = logging.getLogger(__name__)

_TIMEOUT = 15
TWILIO_API = "https://api.twilio.com/2010-04-01"
TELEGRAM_API = "https://api.telegram.org"

# SMS bodies are billed per 160-character segment, so a long incident message becomes
# several messages. Truncating keeps one page to one segment and one charge.
SMS_MAX = 320


class PagingError(Exception):
    """A page could not be delivered. Carries a message an owner can act on."""


# ── Provider credentials ─────────────────────────────────────────────────────

async def get_provider(db: AsyncSession, user_id, provider: str) -> NotificationProvider | None:
    return (await db.execute(
        select(NotificationProvider).where(
            NotificationProvider.user_id == user_id,
            NotificationProvider.provider == provider,
        ).limit(1)
    )).scalar_one_or_none()


def decode_config(row: NotificationProvider) -> dict:
    """Decrypt a provider's config. Never let a decrypt failure leak the ciphertext."""
    try:
        return json.loads(crypto_service.decrypt(row.encrypted_config))
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not read %s credentials for user %s: %s",
                     row.provider, row.user_id, type(exc).__name__)
        raise PagingError(
            f"Your {row.provider} settings could not be read. Please re-enter them."
        ) from None


def encode_config(config: dict) -> str:
    return crypto_service.encrypt(json.dumps(config))


def public_provider(row: NotificationProvider | None, provider: str) -> dict:
    """What the API may say about a provider. An allowlist — the config is never included,
    only enough for the UI to show that it is set up and how much of the month is left."""
    if row is None:
        return {"provider": provider, "configured": False, "verified": False,
                "monthly_limit": None, "sent_this_month": 0}
    return {
        "provider": provider,
        "configured": True,
        "verified": row.verified_at is not None,
        "monthly_limit": row.monthly_limit,
        "sent_this_month": _sent_this_month(row),
    }


# ── The money rail ───────────────────────────────────────────────────────────

def _period_key(when: datetime) -> tuple[int, int]:
    return when.year, when.month


def _sent_this_month(row: NotificationProvider, now: datetime | None = None) -> int:
    """The counter, ignoring a stale period.

    Reading rather than writing here matters: a user checking their usage on the 1st must
    see 0 without that read being what resets the counter.
    """
    now = now or datetime.now(tz=timezone.utc)
    if row.period_start is None:
        return row.sent_this_month
    start = row.period_start
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return row.sent_this_month if _period_key(start) == _period_key(now) else 0


def sms_budget_left(row: NotificationProvider, now: datetime | None = None) -> int:
    return max(0, row.monthly_limit - _sent_this_month(row, now))


async def _charge_sms(db: AsyncSession, row: NotificationProvider) -> None:
    """Count one SMS against the month, rolling the period over if needed.

    Called *before* the send, so a provider error costs the budget rather than risking an
    uncounted message: over-counting is a smaller failure than an unbounded bill.
    """
    now = datetime.now(tz=timezone.utc)
    if row.period_start is None or _period_key(row.period_start.replace(
            tzinfo=row.period_start.tzinfo or timezone.utc)) != _period_key(now):
        row.period_start = now
        row.sent_this_month = 0
    row.sent_this_month += 1
    await db.commit()


# ── Twilio SMS ───────────────────────────────────────────────────────────────

def _twilio_send_sync(sid: str, auth_token: str, from_number: str, to: str, body: str) -> str:
    """Blocking Twilio call — runs in a thread pool. Returns the message SID."""
    resp = _requests.post(
        f"{TWILIO_API}/Accounts/{sid}/Messages.json",
        auth=(sid, auth_token),
        data={"From": from_number, "To": to, "Body": body[:SMS_MAX]},
        timeout=_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise PagingError(_twilio_error(resp))
    return str(resp.json().get("sid", ""))


def _twilio_error(resp) -> str:
    """Turn a Twilio error into something an owner can act on.

    A raw "HTTP 400" tells a non-technical owner nothing about whether they typed the
    number wrong, ran out of credit, or need to verify the recipient.
    """
    try:
        code = int(resp.json().get("code") or 0)
        detail = str(resp.json().get("message") or "").strip()
    except Exception:  # noqa: BLE001
        code, detail = 0, ""

    known = {
        20003: "Twilio rejected your Account SID or Auth Token. Please re-enter them.",
        21211: "That phone number isn't valid. Use the full international form, like +8801712345678.",
        21212: "The 'from' number isn't a valid Twilio number.",
        21408: "Your Twilio account isn't allowed to send to that country yet — enable it in Twilio.",
        21606: "That 'from' number isn't owned by your Twilio account.",
        21610: "That number has unsubscribed from your messages and can't be texted.",
        21614: "That number can't receive SMS.",
    }
    if code in known:
        return known[code]
    if resp.status_code == 401:
        return "Twilio rejected your credentials. Please re-enter your Account SID and Auth Token."
    if resp.status_code == 429:
        return "Twilio is rate-limiting us right now. The next step in your policy will still run."
    return detail or f"Twilio refused the message (HTTP {resp.status_code})."


async def send_sms(db: AsyncSession, user_id, to: str, body: str) -> None:
    """Text someone. Raises PagingError with a readable reason if it can't."""
    row = await get_provider(db, user_id, "twilio")
    if row is None:
        raise PagingError("SMS isn't set up yet — add your Twilio details in Settings.")

    if sms_budget_left(row) <= 0:
        # Refusing is right: silently sending past a ceiling the user set is how a paging
        # loop becomes a surprise invoice.
        raise PagingError(
            f"Monthly SMS limit reached ({row.monthly_limit}). Raise it in Settings if you "
            f"need more — other steps in your policy still ran."
        )

    config = decode_config(row)
    sid, token, from_number = config.get("account_sid"), config.get("auth_token"), config.get("from_number")
    if not (sid and token and from_number):
        raise PagingError("Your Twilio details are incomplete. Please re-enter them in Settings.")

    await _charge_sms(db, row)
    try:
        await asyncio.to_thread(_twilio_send_sync, sid, token, from_number, to, body)
    except PagingError:
        raise
    except _requests.exceptions.Timeout:
        raise PagingError("Twilio didn't respond in time.") from None
    except Exception as exc:  # noqa: BLE001
        raise PagingError(f"Could not reach Twilio: {type(exc).__name__}") from None
    logger.info("SMS paged %s (user %s)", _mask(to), user_id)


def _mask(number: str) -> str:
    """Never write a full phone number to the log."""
    return f"{number[:4]}…{number[-2:]}" if len(number) > 6 else "…"


# ── Telegram ─────────────────────────────────────────────────────────────────

def _telegram_send_sync(bot_token: str, chat_id: str, text: str) -> None:
    resp = _requests.post(
        f"{TELEGRAM_API}/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise PagingError(_telegram_error(resp))


def _telegram_error(resp) -> str:
    try:
        detail = str(resp.json().get("description") or "")
    except Exception:  # noqa: BLE001
        detail = ""
    low = detail.lower()
    if "chat not found" in low:
        return ("Telegram doesn't know that chat. Send your bot a message first, then use the "
                "chat ID it reports.")
    if "unauthorized" in low or resp.status_code == 401:
        return "Telegram rejected your bot token. Check it in Settings."
    if "bot was blocked" in low:
        return "That Telegram user has blocked the bot, so it can't be messaged."
    return detail or f"Telegram refused the message (HTTP {resp.status_code})."


async def send_telegram_direct(*, bot_token: str, chat_id: str, text: str) -> None:
    """Send with a bot token supplied by the caller, not the account-level provider.

    A named Telegram channel carries its own bot and chat, so an agency can point one
    channel at a client's group and another at their own — which one account-wide bot
    token cannot express. Shares `_telegram_send_sync` with `send_telegram`, so there is
    one implementation of talking to Telegram and one set of error messages.
    """
    try:
        await asyncio.to_thread(_telegram_send_sync, bot_token, chat_id, text)
    except PagingError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PagingError(f"Could not reach Telegram: {type(exc).__name__}") from None


async def send_telegram(db: AsyncSession, user_id, chat_id: str, text: str) -> None:
    row = await get_provider(db, user_id, "telegram")
    if row is None:
        raise PagingError("Telegram isn't set up yet — add your bot token in Settings.")
    config = decode_config(row)
    bot_token = config.get("bot_token")
    if not bot_token:
        raise PagingError("Your Telegram bot token is missing. Please re-enter it in Settings.")
    try:
        await asyncio.to_thread(_telegram_send_sync, bot_token, chat_id, text)
    except PagingError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PagingError(f"Could not reach Telegram: {type(exc).__name__}") from None
    logger.info("Telegram paged chat %s (user %s)", chat_id, user_id)


# ── Verification ─────────────────────────────────────────────────────────────

async def verify(db: AsyncSession, user_id, provider: str, test_target: str) -> None:
    """Prove the credentials work by actually delivering a test message.

    Checking credentials without sending would pass on an account that cannot send to the
    user's own country — and the first time they found out would be during a real outage.
    """
    message = "ServerAlly test — your on-call alerts are set up correctly."
    if provider == "twilio":
        await send_sms(db, user_id, test_target, message)
    elif provider == "telegram":
        await send_telegram(db, user_id, test_target, message)
    else:
        raise PagingError(f"Unknown provider '{provider}'.")

    row = await get_provider(db, user_id, provider)
    if row is not None:
        row.verified_at = datetime.now(tz=timezone.utc)
        await db.commit()


# ── Dispatch ─────────────────────────────────────────────────────────────────

async def deliver(
    db: AsyncSession, user_id, channel: str, target: str, subject: str, body: str,
) -> tuple[bool, str]:
    """Send one page through one channel. Returns ``(delivered, detail)``.

    Never raises: one dead channel must not stop the rest of the ladder, which is the whole
    reason for having more than one rung.
    """
    try:
        if channel == "email":
            await notification_service.send_email(target, subject, body)
        elif channel == "sms":
            await send_sms(db, user_id, target, body)
        elif channel == "telegram":
            await send_telegram(db, user_id, target, body)
        elif channel in ("slack", "webhook"):
            await notification_service.send_webhook(target, {"text": subject, "body": body,
                                                            "source": "ServerAlly"})
        else:
            return False, f"Unknown channel '{channel}'"
    except PagingError as exc:
        logger.warning("Page via %s failed: %s", channel, exc)
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Page via %s failed: %s", channel, exc)
        return False, f"{type(exc).__name__}"
    return True, "sent"
