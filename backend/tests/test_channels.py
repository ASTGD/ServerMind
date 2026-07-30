"""Named notification channels.

Two things are worth pinning: a channel's credentials must never leave the server, and a
channel that cannot possibly deliver must be refused at the moment it is saved rather than
at 2am when it matters.
"""
from __future__ import annotations

import json
import uuid

import pytest

from app.models.notification_channel import CHANNEL_KINDS, NotificationChannel
from app.services import channel_service as cs
from app.services.channel_service import ChannelError


def _channel(kind: str, cfg: dict) -> NotificationChannel:
    from app.services import crypto_service
    ch = NotificationChannel(
        kind=kind, label=f"test {kind}",
        encrypted_config=crypto_service.encrypt(json.dumps(cfg)),
    )
    ch.id = uuid.uuid4()
    ch.user_id = uuid.uuid4()
    ch.is_active = True
    ch.verified_at = None
    ch.last_error = None
    ch.last_used_at = None
    ch.created_at = None
    return ch


# ── The secrets must not leak ────────────────────────────────────────────────

def test_a_channels_credentials_never_reach_an_api_payload():
    """A Slack webhook lets anyone post into the workspace; a bot token IS the bot.

    Built the same way as the credential audit on the admin console: serialise a REAL
    payload containing real secrets and assert none of them appear anywhere in it.
    """
    secrets = {
        "slack": ("https://hooks.slack.com/services/T00/B00/SUPERSECRETTOKEN",
                  {"webhook_url": "https://hooks.slack.com/services/T00/B00/SUPERSECRETTOKEN"}),
        "telegram": ("123456789:AAEsuperSECRETbotTOKENxxxxxxxx",
                     {"bot_token": "123456789:AAEsuperSECRETbotTOKENxxxxxxxx",
                      "chat_id": "-1001234567890"}),
    }
    for kind, (secret, cfg) in secrets.items():
        payload = json.dumps(cs.public(_channel(kind, cfg)))
        assert secret not in payload, f"{kind}: the credential leaked into the API payload"
        assert "encrypted_config" not in payload, f"{kind}: the encrypted blob leaked"


def test_the_safe_fields_are_an_allowlist_covering_every_kind():
    """A blocklist silently publishes whatever field is added next."""
    for kind in CHANNEL_KINDS:
        assert kind in cs.SAFE_FIELDS, f"{kind} has no allowlist — its config would be a guess"
        for field in cs.SAFE_FIELDS[kind]:
            assert field in cs.REQUIRED_FIELDS[kind], (
                f"{kind}: '{field}' is exposed but is not even a field we store"
            )


def test_a_destination_the_customer_chose_is_still_visible():
    """Hiding everything would be safe and useless — you could not tell channels apart."""
    d = cs.public(_channel("email", {"address": "ops@example.com"}))["details"]
    assert d["address"] == "ops@example.com"
    d = cs.public(_channel("sms", {"phone": "+8801712345678"}))["details"]
    assert d["phone"] == "+8801712345678"


# ── Refuse what cannot work, at save time ────────────────────────────────────

@pytest.mark.parametrize("kind,cfg,expect", [
    ("email", {"address": "not-an-address"}, "email address"),
    ("email", {}, "missing"),
    ("slack", {"webhook_url": "https://example.com/hook"}, "Slack webhook"),
    ("slack", {}, "missing"),
    ("telegram", {"bot_token": "short", "chat_id": "1"}, "bot token"),
    ("telegram", {"bot_token": "123456789:AAEreallylongtokenvalue"}, "missing"),
    ("sms", {"phone": "01712345678"}, "international format"),
    ("sms", {"phone": "+1"}, "international format"),
])
def test_a_channel_that_cannot_deliver_is_refused_when_saved(kind, cfg, expect):
    """Saving a typo'd destination looks configured and fails silently when it matters."""
    with pytest.raises(ChannelError) as exc:
        cs.clean_config(kind, cfg)
    assert expect.lower() in str(exc.value).lower(), f"unhelpful message: {exc.value}"


@pytest.mark.parametrize("kind,cfg", [
    ("email", {"address": "ops@example.com"}),
    ("slack", {"webhook_url": "https://hooks.slack.com/services/T/B/x"}),
    ("telegram", {"bot_token": "123456789:AAEreallylongtokenvalue", "chat_id": "-100123"}),
    ("sms", {"phone": "+8801712345678"}),
])
def test_a_valid_channel_of_every_kind_is_accepted(kind, cfg):
    cleaned = cs.clean_config(kind, cfg)
    assert set(cleaned) == set(cs.REQUIRED_FIELDS[kind])


def test_unknown_fields_are_dropped_rather_than_stored():
    """Storing a field we never read is how a stray secret ends up in the database."""
    cleaned = cs.clean_config("email", {"address": "o@example.com",
                                        "password": "hunter2", "note": "x"})
    assert cleaned == {"address": "o@example.com"}


def test_an_unsupported_kind_is_refused():
    with pytest.raises(ChannelError) as exc:
        cs.valid_kind("carrier-pigeon")
    for kind in CHANNEL_KINDS:
        assert kind in str(exc.value), "the message should list what IS supported"


def test_a_channel_needs_a_name():
    with pytest.raises(ChannelError):
        cs.valid_label("   ")


# ── Verification state ───────────────────────────────────────────────────────

class _FakeDb:
    async def commit(self):
        pass


@pytest.mark.asyncio
async def test_a_channel_is_not_verified_until_a_message_actually_arrives():
    """"Probably fine" is not a state. Silently-broken alerting is the failure we are
    removing, so a channel is unproven until something really got through."""
    ch = _channel("email", {"address": "o@example.com"})
    assert ch.verified_at is None

    await cs.record_result(_FakeDb(), ch, error="Connection refused")
    assert ch.verified_at is None, "a FAILED send must never mark a channel verified"
    assert "Connection refused" in ch.last_error

    await cs.record_result(_FakeDb(), ch, error=None)
    assert ch.verified_at is not None
    assert ch.last_error is None, "a success should clear the previous failure"


@pytest.mark.asyncio
async def test_a_long_error_is_truncated_rather_than_overflowing_the_column():
    ch = _channel("email", {"address": "o@example.com"})
    await cs.record_result(_FakeDb(), ch, error="x" * 5000)
    assert len(ch.last_error) <= 300


@pytest.mark.asyncio
async def test_an_email_channel_is_not_marked_working_when_mail_is_unconfigured(monkeypatch):
    """The exact failure this feature exists to prevent, one level down.

    `send_email` does not raise when no mail server is configured — every other caller
    treats email as best-effort and must keep working that way. But a channel test that
    "succeeds" because the send was silently skipped reports Working while delivering
    nothing, which is worse than reporting nothing at all.

    Found by pressing Send test on a machine with no mail configured — the same state
    production was in.
    """
    from app.services import notification_service

    monkeypatch.setattr(notification_service, "email_relay", lambda: None)
    sent: list = []

    async def should_not_be_called(*a, **k):
        sent.append(a)

    monkeypatch.setattr(notification_service, "send_email", should_not_be_called)

    ch = _channel("email", {"address": "o@example.com"})
    with pytest.raises(ChannelError) as exc:
        await cs.deliver(_FakeDb(), ch, subject="s", body="b")

    assert "not set up" in str(exc.value).lower(), f"unhelpful message: {exc.value}"
    assert sent == [], "must not even attempt a send it knows cannot happen"


@pytest.mark.asyncio
async def test_an_email_channel_works_when_mail_IS_configured(monkeypatch):
    """The guard must not block the working case."""
    from app.services import notification_service

    monkeypatch.setattr(notification_service, "email_relay", lambda: "mail")
    sent: list = []

    async def fake_send(to, subject, body, html=None):
        sent.append(to)

    monkeypatch.setattr(notification_service, "send_email", fake_send)
    ch = _channel("email", {"address": "o@example.com"})
    await cs.deliver(_FakeDb(), ch, subject="s", body="b")
    assert sent == ["o@example.com"]
