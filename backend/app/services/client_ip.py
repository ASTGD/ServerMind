"""Work out who is actually calling, when there are proxies in front of us.

This matters in two places and was wrong in both.

**Rate limiting** keyed on the raw peer address. In production the backend sits behind
Caddy *and* the frontend nginx container, so every visitor arrives looking like
`172.18.0.7` — one shared bucket for the entire customer base. One person fumbling their
password, or one attacker deliberately, could exhaust the login limit for everybody.

**The audit log** took the *first* `X-Forwarded-For` entry, which is the one a client can
write themselves. An audit trail whose addresses can be forged by the person being audited
is worse than none, because it is believed.

Both come from the same question, so both now ask it here.

**How the answer is derived.** `X-Forwarded-For` is append-only: each proxy adds the
address it received the connection from. Caddy appends, and nginx's
`$proxy_add_x_forwarded_for` appends. So whatever a client writes into the header, our own
proxies append the truth *after* it — and the rightmost entry that is not one of our own
hops is the real client. Walking from the right also means we never have to hardcode how
many proxies are in front of us.

**And the header is only believed when the connection came from a proxy we trust.** If
someone reaches the backend directly, the header is ignored completely — otherwise
supplying a header would be all it takes to get a fresh rate-limit bucket per request.
"""
from __future__ import annotations

import ipaddress
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Loopback and the private ranges. A packet from the public internet cannot legitimately
# arrive with one of these as its source, so treating them as "our own infrastructure" is
# safe; and in a container deployment the proxy hop is always one of them.
DEFAULT_TRUSTED = "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"

_cache: tuple[str, list] | None = None


def _networks() -> list:
    """Parsed trusted ranges, rebuilt only when the setting changes."""
    global _cache
    raw = (getattr(settings, "TRUSTED_PROXIES", "") or DEFAULT_TRUSTED).strip()
    if _cache and _cache[0] == raw:
        return _cache[1]
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            logger.warning("TRUSTED_PROXIES entry %r is not an address or range — ignored",
                           part)
    _cache = (raw, nets)
    return nets


def _parse(value: str):
    """An address from a header, tolerating the shapes proxies actually emit."""
    v = (value or "").strip()
    if not v:
        return None
    if v.startswith("["):                      # [::1]:1234
        v = v[1:].split("]")[0]
    elif v.count(":") == 1:                    # 1.2.3.4:5678 — but never bare IPv6
        v = v.split(":")[0]
    try:
        return ipaddress.ip_address(v)
    except ValueError:
        return None


def is_trusted(value) -> bool:
    ip = value if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)) \
        else _parse(str(value))
    if ip is None:
        return False
    return any(ip in net for net in _networks())


def resolve(request) -> str | None:
    """The caller's address, or None if it cannot be determined."""
    peer_raw = getattr(getattr(request, "client", None), "host", None)
    peer = _parse(peer_raw) if peer_raw else None
    if peer is None:
        return None

    # The connection did not come through our own proxy, so nothing in the request may be
    # believed about where it came from. Use what the socket says.
    if not is_trusted(peer):
        return str(peer)

    header = ""
    try:
        header = request.headers.get("x-forwarded-for") or ""
    except Exception:  # noqa: BLE001  — a malformed request must not break a limiter
        header = ""
    if not header:
        return str(peer)

    # Right to left: skip our own hops, and the first address we did not append is the
    # client. Anything the client wrote themselves sits further left than that and can
    # never win.
    for part in reversed(header.split(",")[-20:]):
        ip = _parse(part)
        if ip is None or is_trusted(ip):
            continue
        return str(ip)

    # Every hop was internal — an internal call, or a proxy chain we entirely own.
    return str(peer)


def key_func(request) -> str:
    """Rate-limit key. Falls back to a constant rather than crashing a request.

    A shared bucket is a bad outcome, but it is the *safe* bad outcome: it throttles more
    than intended rather than less, and it never lets an unresolvable request through
    unlimited.
    """
    return resolve(request) or "unknown"
