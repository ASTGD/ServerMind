"""Certificate expiry — warn before HTTPS breaks, not after.

An expired certificate takes a site down as completely as a dead server, and it is the most
*preventable* outage there is: it always announces itself weeks in advance. servermind.dev
alerts on it and we did not (docs/PRO-FEATURES-PLAN.md §4 #9).

Checked from ServerAlly, against the same URL an uptime monitor already watches, so the
certificate we inspect is the one a visitor actually receives — not whatever file happens
to sit on disk. Certificates change rarely, so this runs **daily**, not on the uptime sweep.

The decision logic (:func:`severity`, :func:`should_alert`) is pure, so the rules are
directly testable and the alerting is quiet: we speak up when things get *worse*, not once
per day for three weeks.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default warning window. Let's Encrypt renews at 30 days and certbot retries for weeks, so
# 14 days means "automation has already failed twice" — worth a human's attention.
DEFAULT_WARN_DAYS = 14
# Below this, it is no longer a warning.
CRITICAL_DAYS = 3

# Worst → best, for comparing states.
_ORDER = {"expired": 3, "critical": 2, "warning": 1, "ok": 0, "unknown": -1}


def host_and_port(url: str) -> tuple[str, int] | None:
    """(host, port) for an HTTPS URL, or None when there is no certificate to check.

    A plain-``http://`` monitor has no certificate — that is not a failure, there is simply
    nothing to inspect.
    """
    try:
        parsed = urlparse(url or "")
    except Exception:  # noqa: BLE001
        return None
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    return parsed.hostname, parsed.port or 443


def days_left(expires_at: datetime | None, now: datetime | None = None) -> int | None:
    """Whole days until expiry; negative once expired. None if unknown."""
    if expires_at is None:
        return None
    now = now or datetime.now(tz=timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    # Round toward zero on the day boundary: 23 hours left is "0 days", not "1".
    return (expires_at - now).days


def severity(days: int | None, warn_days: int = DEFAULT_WARN_DAYS) -> str:
    """'expired' | 'critical' | 'warning' | 'ok' | 'unknown'. Pure."""
    if days is None:
        return "unknown"
    if days < 0:
        return "expired"
    if days <= CRITICAL_DAYS:
        return "critical"
    if days <= max(warn_days, CRITICAL_DAYS):
        return "warning"
    return "ok"


def should_alert(previous: str | None, current: str) -> bool:
    """Only when it gets WORSE.

    A certificate 10 days from expiry must not email every day for 10 days — that is how
    people learn to ignore alerts. We speak up crossing into warning, again crossing into
    critical, again on expiry, and never in between. Recovery (a renewal) is silent: the
    owner does not need congratulating, and the next worsening will alert again because the
    stored state went back to 'ok'.
    """
    if current in ("unknown", "ok"):
        return False
    return _ORDER[current] > _ORDER.get(previous or "unknown", -1)


def message(host: str, days: int | None, level: str) -> tuple[str, str]:
    """(subject, body) in an owner's words — no jargon, and say what to do."""
    if level == "expired":
        subject = f"🔴 HTTPS certificate for {host} has EXPIRED"
        body = (
            f"The HTTPS certificate for {host} expired {abs(days or 0)} day(s) ago.\n\n"
            "Visitors are now seeing a security warning instead of your site. This needs "
            "fixing today.\n\nIf you use Let's Encrypt, renewing is usually one command — "
            "ask Ally to do it."
        )
    elif level == "critical":
        subject = f"⚠️ HTTPS certificate for {host} expires in {days} day(s)"
        body = (
            f"The HTTPS certificate for {host} expires in {days} day(s).\n\n"
            "Automatic renewal has not happened. If it expires, visitors will see a security "
            "warning instead of your site.\n\nAsk Ally to renew it."
        )
    else:
        subject = f"HTTPS certificate for {host} expires in {days} days"
        body = (
            f"The HTTPS certificate for {host} expires in {days} days.\n\n"
            "This is usually renewed automatically, so there is probably nothing to do — but "
            "if it has not renewed in the next week, it is worth a look."
        )
    return subject, body


async def inspect(url: str, timeout: float = 10.0) -> dict:
    """Fetch the live certificate for ``url``.

    Returns ``{expires_at, issuer, error}``. Never raises — a check that cannot complete
    reports ``error`` and leaves expiry unknown, rather than pretending the cert is fine.
    """
    import asyncio

    target = host_and_port(url)
    if target is None:
        return {"expires_at": None, "issuer": None, "error": None, "skipped": True}
    host, port = target

    def _fetch() -> dict:
        import socket
        import ssl

        context = ssl.create_default_context()
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                with context.wrap_socket(sock, server_hostname=host) as tls:
                    cert = tls.getpeercert()
        except ssl.SSLCertVerificationError as exc:
            # An EXPIRED certificate fails verification — which is exactly the case we most
            # need to report, so it must not be swallowed as a generic connection error.
            text = str(exc)
            if "certificate has expired" in text.lower():
                return {"expires_at": None, "issuer": None, "error": "The certificate has expired.",
                        "expired": True}
            return {"expires_at": None, "issuer": None, "error": f"Certificate problem: {text[:200]}"}
        except socket.timeout:
            return {"expires_at": None, "issuer": None, "error": "Timed out reading the certificate."}
        except Exception as exc:  # noqa: BLE001
            return {"expires_at": None, "issuer": None,
                    "error": f"Could not read the certificate ({type(exc).__name__})."}

        return {
            "expires_at": parse_not_after(cert.get("notAfter")),
            "issuer": issuer_name(cert),
            "error": None,
        }

    result = await asyncio.to_thread(_fetch)
    result.setdefault("skipped", False)
    return result


def parse_not_after(value: str | None) -> datetime | None:
    """OpenSSL's ``'Jul 25 12:00:00 2026 GMT'`` → an aware datetime."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        logger.debug("Unparseable certificate notAfter: %r", value)
        return None


def issuer_name(cert: dict) -> str | None:
    """The human-recognisable issuer ("Let's Encrypt"), from the RDN tuples."""
    for rdn in cert.get("issuer") or ():
        for key, val in rdn:
            if key == "organizationName":
                return val
    for rdn in cert.get("issuer") or ():
        for key, val in rdn:
            if key == "commonName":
                return val
    return None


# --- Turning HTTPS on for a site ----------------------------------------------------------
#
# A certificate can only be issued if the domain ALREADY points at the server: Let's Encrypt
# proves ownership by fetching a file over the public internet. That is the one part of this
# nobody here controls — the customer may have bought the domain an hour ago — so it is
# checked first and answered plainly, rather than attempted and failed with a certbot error
# nobody can read.

import asyncio
import ipaddress
import socket


class SslError(Exception):
    """Something the customer can read and act on."""


async def resolve(name: str) -> set[str]:
    """Every address a name currently answers with. Empty when it does not resolve.

    Resolved from here rather than from the server, deliberately: Let's Encrypt will look
    it up from the public internet too, and a server's own resolver can be pointed at
    something local that would give a different — and wrong — answer.
    """
    def _lookup() -> set[str]:
        try:
            infos = socket.getaddrinfo(name, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            return set()
        return {info[4][0] for info in infos}

    try:
        return await asyncio.wait_for(asyncio.to_thread(_lookup), timeout=10)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001 — a lookup failure is "no answer"
        return set()


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


async def server_addresses(host: str) -> set[str]:
    """The addresses this server answers on, whether it was added by IP or by name."""
    return {host} if _is_ip(host) else await resolve(host)


async def check_dns(domain: str, server_host: str) -> dict:
    """Does this domain point at this server yet?

    Returns what the customer needs to know either way: whether it is ready, where the
    domain currently points, and the record to create if it does not point here. A "no"
    here is not a failure — it is the normal state of a domain someone just bought.
    """
    theirs = await resolve(domain)
    ours = await server_addresses(server_host)
    ready = bool(theirs and ours and (theirs & ours))

    target = sorted(a for a in ours if _is_ip(a)) or sorted(ours)
    return {
        "ready": ready,
        "points_to": sorted(theirs),
        "server_addresses": sorted(ours),
        "record": {"type": "A", "name": domain, "value": target[0] if target else server_host},
        "reason": (
            None if ready
            else "does not resolve" if not theirs
            else "points somewhere else"
        ),
    }


def dns_message(domain: str, check: dict) -> str:
    """Why HTTPS cannot be turned on yet, in words, with the fix."""
    record = check["record"]
    fix = (f'Create a DNS record for it: type {record["type"]}, name {record["name"]}, '
           f'value {record["value"]}. It can take a few minutes to take effect.')
    if check["reason"] == "does not resolve":
        return (f"{domain} does not point anywhere yet, so a certificate cannot be issued "
                f"for it — the authority has to reach this server through that name to "
                f"prove it is yours. {fix}")
    where = ", ".join(check["points_to"][:3])
    return (f"{domain} currently points to {where}, not to this server, so a certificate "
            f"cannot be issued for it yet. {fix}")
