"""SMS and Telegram paging, and the money rail around SMS.

SMS is the first thing in the product that costs money on every use, so the tests that
matter here are about the ceiling rather than the happy path.

The senders are exercised against a **real local HTTP server** rather than a mock, so what
is verified is the actual request Twilio and Telegram would receive — method, path, auth,
and form fields. That is the strongest check available without the user's own provider
credentials, which only they can create.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest

from app.models.escalation import NotificationProvider
from app.services import paging_service
from app.services.paging_service import PagingError

# Every test that reasons about the budget passes this in explicitly, so those stay fixed
# and readable. But send_sms() reads the real clock, so a provider handed a hardcoded date
# is in "last month" the moment the month turns — the counter resets, the limit stops
# applying, and a test about refusing past the limit starts failing at midnight on the 1st
# for reasons that have nothing to do with the code. It happened: this file went red on
# 1 August. So the default period is the CURRENT month, and only the tests that are
# deliberately about a rollover say otherwise.
NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def this_month() -> datetime:
    """The start of the month the real clock is in, whenever the suite happens to run."""
    now = datetime.now(tz=timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class FakeSession:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None


def provider(**kw) -> NotificationProvider:
    row = NotificationProvider(
        user_id="u1", provider=kw.get("provider", "twilio"),
        encrypted_config=kw.get("encrypted_config", ""),
    )
    row.monthly_limit = kw.get("monthly_limit", 100)
    row.sent_this_month = kw.get("sent_this_month", 0)
    row.period_start = kw.get("period_start", this_month())
    row.verified_at = kw.get("verified_at")
    return row


# ── The money rail ───────────────────────────────────────────────────────────

def test_budget_counts_down_within_the_month():
    row = provider(monthly_limit=10, sent_this_month=4)
    row.period_start = NOW
    assert paging_service.sms_budget_left(row, NOW) == 6


def test_a_new_month_restores_the_budget():
    """The counter is per calendar month, so a spent month must not silence the next one."""
    row = provider(monthly_limit=10, sent_this_month=10,
                   period_start=NOW - timedelta(days=40))
    assert paging_service.sms_budget_left(row, NOW) == 10


def test_reading_the_counter_does_not_reset_it():
    """A user checking usage on the 1st must see 0 without that read being what performs
    the reset — otherwise the reset depends on somebody looking."""
    row = provider(sent_this_month=7, period_start=NOW - timedelta(days=40))
    assert paging_service.sms_budget_left(row, NOW) == row.monthly_limit
    assert row.sent_this_month == 7, "reading must not mutate the row"


def test_a_naive_period_start_is_still_compared_correctly():
    row = provider(monthly_limit=5, sent_this_month=5,
                   period_start=datetime(2026, 7, 1, 0, 0))
    row.period_start = NOW
    assert paging_service.sms_budget_left(row, NOW) == 0


@pytest.mark.asyncio
async def test_sms_is_refused_once_the_monthly_limit_is_reached(monkeypatch):
    """The rail that matters: a paging loop must not become a surprise invoice. Refusing is
    correct — silently sending past a ceiling the user set would be worse than not paging."""
    row = provider(monthly_limit=5, sent_this_month=5)
    monkeypatch.setattr(paging_service, "get_provider", _async_fn(row))

    sent = []
    monkeypatch.setattr(paging_service, "_twilio_send_sync",
                        lambda *a, **k: sent.append(a) or "SM1")

    with pytest.raises(PagingError) as exc:
        await paging_service.send_sms(FakeSession(), "u1", "+8801", "page")
    assert "limit reached" in str(exc.value).lower()
    assert not sent, "no message may be sent past the ceiling"


@pytest.mark.asyncio
async def test_the_budget_is_charged_before_the_send(monkeypatch):
    """Charging first means a provider error costs the budget rather than risking an
    uncounted message — over-counting is a far smaller failure than an unbounded bill."""
    row = provider(monthly_limit=5, sent_this_month=0,
                   encrypted_config=paging_service.encode_config(
                       {"account_sid": "AC1", "auth_token": "t", "from_number": "+1"}))
    monkeypatch.setattr(paging_service, "get_provider", _async_fn(row))

    def explode(*_a, **_k):
        raise PagingError("Twilio is down")

    monkeypatch.setattr(paging_service, "_twilio_send_sync", explode)

    with pytest.raises(PagingError):
        await paging_service.send_sms(FakeSession(), "u1", "+8801", "page")
    assert row.sent_this_month == 1


@pytest.mark.asyncio
async def test_sms_without_credentials_says_so_plainly(monkeypatch):
    monkeypatch.setattr(paging_service, "get_provider", _async_fn(None))
    with pytest.raises(PagingError) as exc:
        await paging_service.send_sms(FakeSession(), "u1", "+8801", "page")
    assert "isn't set up" in str(exc.value)


# ── Credentials never leave ──────────────────────────────────────────────────

def test_the_public_view_never_includes_the_credentials():
    """Same rule as server credentials and backup destinations: the secret is write-only."""
    secret = {"account_sid": "AC_secret", "auth_token": "super_secret", "from_number": "+1555"}
    row = provider(encrypted_config=paging_service.encode_config(secret))
    payload = json.dumps(paging_service.public_provider(row, "twilio"))
    for value in secret.values():
        assert value not in payload
    assert "encrypted_config" not in payload
    assert row.encrypted_config not in payload


def test_the_config_round_trips_but_is_encrypted_at_rest():
    config = {"bot_token": "123:ABC"}
    row = provider(provider="telegram", encrypted_config=paging_service.encode_config(config))
    assert "123:ABC" not in row.encrypted_config
    assert paging_service.decode_config(row) == config


def test_unreadable_credentials_produce_a_fixable_message_not_a_crash():
    row = provider(encrypted_config="garbage")
    with pytest.raises(PagingError) as exc:
        paging_service.decode_config(row)
    assert "re-enter" in str(exc.value)


def test_the_public_view_of_a_missing_provider_is_still_usable():
    out = paging_service.public_provider(None, "twilio")
    assert out == {"provider": "twilio", "configured": False, "verified": False,
                   "monthly_limit": None, "sent_this_month": 0}


def test_a_phone_number_is_masked_for_the_log():
    """A page's destination is personal data; logs are the easiest place to leak it."""
    assert paging_service._mask("+8801712345678") == "+880…78"
    assert "1712345" not in paging_service._mask("+8801712345678")


# ── One dead channel never stops the ladder ──────────────────────────────────

@pytest.mark.asyncio
async def test_deliver_reports_failure_instead_of_raising(monkeypatch):
    """`deliver` is the worker's only sending path, and the worker must keep climbing."""
    monkeypatch.setattr(paging_service, "get_provider", _async_fn(None))
    ok, detail = await paging_service.deliver(FakeSession(), "u1", "sms", "+880", "s", "b")
    assert ok is False and "set up" in detail


@pytest.mark.asyncio
async def test_deliver_rejects_an_unknown_channel_without_raising():
    ok, detail = await paging_service.deliver(FakeSession(), "u1", "carrier-pigeon", "x", "s", "b")
    assert ok is False and "Unknown channel" in detail


@pytest.mark.asyncio
async def test_an_unexpected_exception_is_still_only_a_failed_step(monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("socket exploded")

    monkeypatch.setattr(paging_service.notification_service, "send_email", boom)
    ok, detail = await paging_service.deliver(FakeSession(), "u1", "email", "a@b.c", "s", "b")
    assert ok is False and "RuntimeError" in detail


# ── Provider errors a non-technical owner can act on ─────────────────────────

class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.parametrize("code,expect", [
    (20003, "re-enter"),
    (21211, "international"),
    (21606, "owned by your Twilio account"),
    (21610, "unsubscribed"),
])
def test_twilio_errors_name_the_actual_fix(code, expect):
    """"HTTP 400" tells an owner nothing about whether they mistyped the number, ran out of
    credit, or need to enable their country."""
    assert expect in paging_service._twilio_error(_Resp(400, {"code": code, "message": "x"}))


def test_an_unmapped_twilio_error_still_says_something_useful():
    assert "HTTP 500" in paging_service._twilio_error(_Resp(500, {}))


def test_a_twilio_rate_limit_reassures_that_the_ladder_continues():
    assert "next step" in paging_service._twilio_error(_Resp(429, {}))


def test_telegram_chat_not_found_explains_the_first_message_requirement():
    detail = paging_service._telegram_error(_Resp(400, {"description": "Bad Request: chat not found"}))
    assert "Send your bot a message first" in detail


def test_telegram_bad_token_points_at_settings():
    assert "Settings" in paging_service._telegram_error(_Resp(401, {"description": "Unauthorized"}))


# ── The real request, against a real local server ────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    captured: dict = {}

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        _Handler.captured = {
            "path": self.path,
            "auth": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type", ""),
            "raw": body.decode(),
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"sid": "SM_test", "ok": true}')

    def log_message(self, *_a):
        return


@pytest.fixture
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.mark.asyncio
async def test_twilio_request_is_shaped_the_way_twilio_expects(monkeypatch, local_server):
    """Exercises the real sender against a real socket: the account path, HTTP basic auth,
    and the From/To/Body form fields."""
    monkeypatch.setattr(paging_service, "TWILIO_API", local_server)
    row = provider(encrypted_config=paging_service.encode_config(
        {"account_sid": "AC123", "auth_token": "tok", "from_number": "+15550001"}))
    monkeypatch.setattr(paging_service, "get_provider", _async_fn(row))

    await paging_service.send_sms(FakeSession(), "u1", "+8801712345678", "Shop is down")

    cap = _Handler.captured
    assert cap["path"] == "/Accounts/AC123/Messages.json"
    assert cap["auth"].startswith("Basic ")
    form = parse_qs(cap["raw"])
    assert form["From"] == ["+15550001"]
    assert form["To"] == ["+8801712345678"]
    assert form["Body"] == ["Shop is down"]


@pytest.mark.asyncio
async def test_a_long_page_is_truncated_to_one_billed_segment(monkeypatch, local_server):
    """SMS bills per 160-character segment, so an unbounded body multiplies the cost of
    every page."""
    monkeypatch.setattr(paging_service, "TWILIO_API", local_server)
    row = provider(encrypted_config=paging_service.encode_config(
        {"account_sid": "AC1", "auth_token": "t", "from_number": "+1"}))
    monkeypatch.setattr(paging_service, "get_provider", _async_fn(row))

    await paging_service.send_sms(FakeSession(), "u1", "+880", "x" * 5000)
    assert len(parse_qs(_Handler.captured["raw"])["Body"][0]) == paging_service.SMS_MAX


@pytest.mark.asyncio
async def test_telegram_request_is_shaped_the_way_telegram_expects(monkeypatch, local_server):
    monkeypatch.setattr(paging_service, "TELEGRAM_API", local_server)
    row = provider(provider="telegram",
                   encrypted_config=paging_service.encode_config({"bot_token": "123:ABC"}))
    monkeypatch.setattr(paging_service, "get_provider", _async_fn(row))

    await paging_service.send_telegram(FakeSession(), "u1", "-100999", "Shop is down")

    cap = _Handler.captured
    assert cap["path"] == "/bot123:ABC/sendMessage"
    assert "application/json" in cap["content_type"]
    payload = json.loads(cap["raw"])
    assert payload["chat_id"] == "-100999"
    assert payload["text"] == "Shop is down"


def _async_fn(value):
    async def _inner(*_a, **_k):
        return value
    return _inner
