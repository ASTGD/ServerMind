"""Uptime checks — probe a URL from ServerAlly and decide up/down.

The judgement lives in :func:`evaluate`, which is **pure** (no network, no DB) so every
rule below is directly testable:

- A 200 is **not** proof. If the monitor declares ``expected_keyword`` it must appear in
  the body; and an empty body on a "working" page is treated as down, because a blank
  200 is what a broken PHP site serves. (Same rule as the mission verification gate.)
- One failure is **not** an outage. A monitor flips to DOWN only after
  ``failure_threshold`` consecutive failures, so a single network blip never pages anyone.
- Recovery is immediate: one good check clears the failure streak.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_MAX_BODY_SNIFF = 200_000  # don't hold a huge page in memory just to keyword-match


@dataclass
class ProbeResult:
    """What one HTTP probe observed. ``ok`` is the raw verdict for THIS check."""

    ok: bool
    http_status: int | None = None
    response_ms: int | None = None
    error: str | None = None


def evaluate(
    *,
    status_code: int | None,
    body: str | None,
    expected_status: int,
    expected_keyword: str | None,
    transport_error: str | None = None,
) -> ProbeResult:
    """Decide whether one response counts as UP. Pure — no I/O."""
    if transport_error:
        return ProbeResult(ok=False, error=transport_error[:500])

    if status_code is None:
        return ProbeResult(ok=False, error="No response from the site.")

    if status_code != expected_status:
        return ProbeResult(
            ok=False,
            http_status=status_code,
            error=f"Returned HTTP {status_code} (expected {expected_status}).",
        )

    text = body or ""
    if expected_keyword:
        if expected_keyword not in text:
            return ProbeResult(
                ok=False,
                http_status=status_code,
                error=f"Page loaded but the expected text “{expected_keyword}” was missing.",
            )
    elif not text.strip():
        # A COMPLETELY blank body is the classic signature of a broken PHP site.
        # Deliberately not "suspiciously short": a redirect stub, an API health endpoint
        # ({"ok":true}) and a plain "OK" are all valid, and a false DOWN alert destroys
        # trust in every other alert we send. Owners who need stricter proof set
        # ``expected_keyword``.
        return ProbeResult(
            ok=False,
            http_status=status_code,
            error="Page returned an empty response.",
        )

    return ProbeResult(ok=True, http_status=status_code)


def next_state(
    *, current_status: str, consecutive_failures: int, ok: bool, failure_threshold: int
) -> tuple[str, int, bool]:
    """Fold one probe into the monitor's state.

    Returns ``(new_status, new_consecutive_failures, changed)`` where ``changed`` means a
    real up↔down transition worth announcing. Pure — no I/O.
    """
    threshold = max(1, failure_threshold)

    if ok:
        new_status = "up"
        new_failures = 0
    else:
        new_failures = consecutive_failures + 1
        # Stay in the previous state until the streak proves it's a real outage.
        new_status = "down" if new_failures >= threshold else current_status
        if new_status == "unknown":
            new_status = "unknown" if new_failures < threshold else "down"

    changed = new_status != current_status and new_status in ("up", "down")
    return new_status, new_failures, changed


async def probe(monitor) -> ProbeResult:
    """Run one real HTTP check for ``monitor``. Never raises."""
    import time

    import httpx

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=monitor.timeout_seconds or 15,
            follow_redirects=True,
            headers={"User-Agent": "ServerAlly-Uptime/1.0 (+https://serverally.firevps.net)"},
        ) as client:
            resp = await client.request(monitor.method or "GET", monitor.url)
            elapsed = int((time.perf_counter() - started) * 1000)
            # Always read the body: even without a keyword we check it isn't blank.
            body = resp.text[:_MAX_BODY_SNIFF]
            result = evaluate(
                status_code=resp.status_code,
                body=body,
                expected_status=monitor.expected_status or 200,
                expected_keyword=monitor.expected_keyword,
            )
            result.response_ms = elapsed
            return result
    except Exception as exc:  # noqa: BLE001 — a probe must never break the sweep
        elapsed = int((time.perf_counter() - started) * 1000)
        result = evaluate(
            status_code=None, body=None,
            expected_status=monitor.expected_status or 200,
            expected_keyword=monitor.expected_keyword,
            transport_error=_friendly_transport_error(exc),
        )
        result.response_ms = elapsed
        return result


def _friendly_transport_error(exc: Exception) -> str:
    """Say what an owner can act on, not the exception class name."""
    name = type(exc).__name__
    text = str(exc)
    if "Timeout" in name or "timeout" in text.lower():
        return "The site did not respond in time."
    # DNS must be distinguished from a refused connection — they need completely different
    # fixes (point the domain vs fix the server). The wording differs per platform, so
    # match all the common forms rather than one.
    _DNS_SIGNS = (
        "nameresolution", "getaddrinfo", "name or service not known",
        "nodename nor servname", "temporary failure in name resolution",
        "[errno -2]", "[errno -3]", "[errno 8]", "no address associated",
    )
    low = text.lower()
    if "NameResolution" in name or any(sign in low for sign in _DNS_SIGNS):
        return "The domain name could not be resolved — check the site's DNS."
    if "SSL" in name or "certificate" in text.lower():
        return "The HTTPS certificate could not be verified."
    if "Connect" in name or "Connection" in name:
        return "Could not connect to the server (it may be down or blocking us)."
    if "TooManyRedirects" in name:
        return "The site redirected too many times."
    return f"Could not reach the site ({name})."


def uptime_percentage(up_count: int, total: int) -> float:
    """Uptime over a window, rounded to 2dp. 100.0 when nothing has been checked yet —
    an unmonitored site is not a failing one."""
    if total <= 0:
        return 100.0
    return round((up_count / total) * 100, 2)
