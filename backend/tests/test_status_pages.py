"""Status page guarantees (docs/PRO-FEATURES-PLAN.md §4 #4).

This is the **only unauthenticated read surface in the app**, so the tests that matter are
leak tests: a stranger who loads a status page must learn nothing except what the owner
chose to publish.

The dangerous fields all live on the monitor: the URL it probes (which may be an internal
admin path), the internal error text (which reveals what we check for), the server behind
it, and the keyword. ``public_item`` is an allowlist precisely so none of them can escape;
these tests run a monitor stuffed with sentinels through it and assert on the serialised
JSON — the same approach as ``test_user_detail_never_exposes_a_credential``.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.models.uptime import UptimeMonitor
from app.services import status_page_service
from app.services.status_page_service import (
    overall_message,
    overall_status,
    public_item,
    slugify,
    valid_slug,
)

# Sentinels that must NEVER reach a visitor.
_SECRET_URL = "https://internal-admin.example.com/secret-console?token=DO-NOT-LEAK"
_SECRET_KEYWORD = "Welcome to my private admin"
_SECRET_ERROR = "Page loaded but the expected text “Welcome to my private admin” was missing."
_SECRET_HOST = "10.0.0.44"


def _monitor() -> UptimeMonitor:
    return UptimeMonitor(
        id=uuid.uuid4(), user_id=uuid.uuid4(), server_id=uuid.uuid4(),
        name=f"prod-web-01 ({_SECRET_HOST})",   # internal naming, deliberately ugly
        url=_SECRET_URL,
        expected_keyword=_SECRET_KEYWORD,
        current_status="down",
        last_error=_SECRET_ERROR,
        last_response_ms=1234,
        interval_seconds=300, timeout_seconds=15, failure_threshold=2,
        channel="email", channel_target="owner@example.com",
        created_at=datetime.now(tz=timezone.utc),
    )


# ── The leak tests ───────────────────────────────────────────────────────────

def test_public_item_never_leaks_private_details():
    payload = json.dumps(public_item(_monitor(), "Website", [], 99.9, 99.5))
    for secret, what in (
        (_SECRET_URL, "the monitored URL"),
        ("DO-NOT-LEAK", "a token in the URL"),
        (_SECRET_KEYWORD, "the expected keyword"),
        (_SECRET_ERROR, "the internal error text"),
        (_SECRET_HOST, "the server address"),
        ("owner@example.com", "the owner's email"),
    ):
        assert secret not in payload, f"LEAK: {what} reached the public payload"


def test_public_item_exposes_only_the_allowlisted_fields():
    """A new field on the monitor must never appear here by accident."""
    item = public_item(_monitor(), "Website", [], 99.9, 99.5)
    assert set(item) == {"name", "status", "uptime_24h", "uptime_window", "history"}


def test_display_name_replaces_the_internal_monitor_name():
    """The owner renames 'prod-web-01 (10.0.0.44)' to 'Website' — the internal name, which
    contains the host, must not be what visitors see."""
    item = public_item(_monitor(), "Website", [], 100.0, 100.0)
    assert item["name"] == "Website"
    assert _SECRET_HOST not in item["name"]


def test_history_carries_no_error_detail():
    """The bar says up/down per day and nothing about WHY."""
    history = [{"date": "2026-07-25", "status": "down"}]
    item = public_item(_monitor(), "Website", history, 50.0, 90.0)
    assert item["history"] == history
    assert all(set(entry) == {"date", "status"} for entry in item["history"])


def test_falls_back_to_the_monitor_name_when_not_renamed():
    """Honest trade-off: with no display name we must show something, so the monitor's own
    name is used — which is why the UI defaults the field and tells the owner it is public."""
    item = public_item(_monitor(), None, [], 100.0, 100.0)
    assert item["name"].startswith("prod-web-01")


# ── The visitor-facing headline ──────────────────────────────────────────────

def test_overall_status_is_down_if_anything_is_down():
    assert overall_status([{"status": "up"}, {"status": "down"}]) == "down"
    assert overall_status([{"status": "up"}, {"status": "up"}]) == "up"
    assert overall_status([]) == "unknown"
    assert overall_status([{"status": "unknown"}]) == "unknown"


def test_overall_message_is_never_technical():
    assert overall_message("up", 0, 3) == "All systems operational"
    assert overall_message("down", 3, 3) == "We are experiencing an outage"
    assert "1 of 3" in overall_message("down", 1, 3)


# ── Slugs (the public address) ───────────────────────────────────────────────

def test_valid_slugs():
    for good in ("myshop", "my-shop", "shop123", "a"):
        assert valid_slug(good), good


def test_invalid_slugs():
    for bad in ("", "My-Shop", "shop_1", "-shop", "shop-", "sh op", "shop!", "a" * 65,
                "../etc/passwd", "shop/../admin"):
        assert not valid_slug(bad), bad


def test_reserved_slugs_are_refused():
    """A page at /status/api or /status/admin would be confusing at best."""
    for reserved in ("api", "admin", "login", "settings", "status"):
        assert not valid_slug(reserved), reserved
    assert "api" in status_page_service.RESERVED_SLUGS


def test_slugify_produces_a_valid_slug():
    for title in ("My Shop!", "  Acme  Corp  ", "café", "###", "A very " + "long " * 30 + "title"):
        assert valid_slug(slugify(title)), f"{title!r} → {slugify(title)!r}"


def test_slugify_never_suggests_a_reserved_word():
    """Regression: the fallback used to be 'status', which is itself reserved — so the
    default suggestion was invalid and the user hit an error they did not cause."""
    assert slugify("###") not in status_page_service.RESERVED_SLUGS
    assert valid_slug(slugify("###"))
    assert valid_slug(slugify(""))
    assert valid_slug(slugify("status"))  # a title of exactly the reserved word


def test_valid_slug_does_not_silently_lowercase():
    """Regression: it lowercased its input, so it approved 'My-Shop' while its own error
    message said lowercase-only — and a caller could store an unchecked slug."""
    assert not valid_slug("My-Shop")
    assert valid_slug("my-shop")
