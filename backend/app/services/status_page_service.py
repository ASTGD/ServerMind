"""Status page rendering — build the PUBLIC payload, and nothing more.

:func:`public_item` is the security boundary of this feature. It is an explicit allowlist
built field-by-field, deliberately **not** a serialisation of the monitor object: a
``model_dump()`` would happily publish the monitored URL, the internal error text and the
server it belongs to the first time someone added a field.

What a visitor may see: the owner's chosen label, up/down/unknown, and uptime numbers.
Nothing else.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models.uptime import UptimeCheck, UptimeMonitor
from app.services import uptime_service

logger = logging.getLogger(__name__)

# How much history the daily bar shows. Matches uptime check retention (30 days), so we
# never draw a row of empty days and call it "no data".
HISTORY_DAYS = 30

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")

# Slugs that would collide with our own routes or be confusing in public.
RESERVED_SLUGS = {
    "api", "admin", "status", "auth", "login", "logout", "assets", "static",
    "dashboard", "settings", "app", "www", "mcp", "oauth", "health", "docs",
}


def valid_slug(slug: str) -> bool:
    """Lowercase letters, digits and hyphens; 1–64 chars; not reserved.

    STRICT on purpose — it does not lowercase for you. Callers normalise first (the router
    does ``.strip().lower()``), so an uppercase slug is still accepted from a user; but a
    validator that silently lowercased would contradict its own error message and would
    also let a caller store a slug it never actually checked.
    """
    slug = slug or ""
    return bool(_SLUG_RE.match(slug)) and slug not in RESERVED_SLUGS


# The suggestion used when a title has no usable characters. Deliberately NOT "status" —
# that is a reserved slug, so the default suggestion would itself have been invalid.
_FALLBACK_SLUG = "my-status"


def slugify(text: str) -> str:
    """A reasonable starting slug from a title. Always returns a VALID slug."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    s = s[:64].strip("-")
    return s if valid_slug(s) else _FALLBACK_SLUG


def public_item(monitor: UptimeMonitor, display_name: str | None, history: list[dict],
                uptime_24h: float, uptime_window: float) -> dict:
    """The ONLY shape a visitor ever receives for a monitored thing.

    Built as a literal allowlist. Note what is absent, on purpose: ``monitor.url``,
    ``monitor.last_error``, ``monitor.server_id``, ``expected_keyword`` — publishing any of
    them would leak an internal path, what we check for, or the infrastructure behind it.
    """
    return {
        "name": (display_name or monitor.name or "Service").strip(),
        "status": monitor.current_status or "unknown",
        "uptime_24h": uptime_24h,
        "uptime_window": uptime_window,
        "history": history,  # [{date, status}] — no error text, no counts of what failed
    }


def overall_status(items: list[dict]) -> str:
    """One word for the banner: down if anything is down, else up, else unknown."""
    statuses = {i.get("status") for i in items}
    if "down" in statuses:
        return "down"
    if "up" in statuses:
        return "up"
    return "unknown"


def overall_message(status: str, down_count: int, total: int) -> str:
    """The headline, in a visitor's words — never technical."""
    if status == "up":
        return "All systems operational"
    if status == "down":
        if down_count == total:
            return "We are experiencing an outage"
        return f"{down_count} of {total} services are having problems"
    return "Status is being checked"


async def daily_history(db, monitor_ids: list, days: int = HISTORY_DAYS) -> dict:
    """Per-monitor, per-day status for the history bar.

    One grouped query for every monitor (no N+1). A day is 'down' if ANY check that day
    failed — a status page should be honest about a blip rather than round it away; a day
    with no checks at all is 'none' (drawn as a gap, not as an outage).
    """
    if not monitor_ids:
        return {}
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    day = func.date_trunc("day", UptimeCheck.checked_at)
    rows = (await db.execute(
        select(
            UptimeCheck.monitor_id,
            day.label("day"),
            func.count().label("total"),
            func.count().filter(UptimeCheck.status == "down").label("down"),
        )
        .where(UptimeCheck.monitor_id.in_(monitor_ids), UptimeCheck.checked_at >= since)
        .group_by(UptimeCheck.monitor_id, day)
    )).all()

    by_monitor: dict = {mid: {} for mid in monitor_ids}
    for mid, d, total, down in rows:
        by_monitor.setdefault(mid, {})[d.date().isoformat()] = (
            "down" if (down or 0) > 0 else "up"
        )

    # Fill the window so the bar is a fixed width, with gaps where we have no data.
    today = datetime.now(tz=timezone.utc).date()
    window = [(today - timedelta(days=offset)).isoformat() for offset in range(days - 1, -1, -1)]
    return {
        mid: [{"date": d, "status": by_monitor.get(mid, {}).get(d, "none")} for d in window]
        for mid in monitor_ids
    }


async def uptime_percentages(db, monitor_ids: list, days: int = HISTORY_DAYS) -> dict:
    """(uptime_24h, uptime_window) per monitor, in two grouped queries."""
    if not monitor_ids:
        return {}
    now = datetime.now(tz=timezone.utc)
    out: dict = {mid: [100.0, 100.0] for mid in monitor_ids}
    for index, window in ((0, timedelta(hours=24)), (1, timedelta(days=days))):
        rows = (await db.execute(
            select(
                UptimeCheck.monitor_id,
                func.count().label("total"),
                func.count().filter(UptimeCheck.status == "up").label("up"),
            )
            .where(UptimeCheck.monitor_id.in_(monitor_ids), UptimeCheck.checked_at >= now - window)
            .group_by(UptimeCheck.monitor_id)
        )).all()
        for mid, total, up in rows:
            out[mid][index] = uptime_service.uptime_percentage(up or 0, total or 0)
    return out
