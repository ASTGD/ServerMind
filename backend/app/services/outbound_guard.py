"""Guard for HTTP requests we make to a URL the *customer* chose.

Webhooks invert the usual trust direction: normally the customer's browser calls us, but
here **our server calls an address they typed**. That makes every such URL a
server-side-request-forgery vector, and this backend is a particularly rewarding target —
it sits on a Docker network with Postgres, Redis and guacd, and on a cloud instance the
metadata endpoint hands out IAM credentials to anything that asks.

So a webhook URL must be checked against where it actually *resolves*, not merely how it
looks. Blocked:

- anything that isn't ``http``/``https`` (``file://``, ``gopher://``, ``ftp://`` …)
- loopback, private, link-local, and reserved address space
- the cloud metadata addresses every major provider uses
- hostnames that resolve to any of the above, including via a CNAME

**Checked at request time, not only when saved.** A save-time-only check is defeated by
pointing a hostname at a public IP while it is being validated and moving it to
169.254.169.254 afterwards. Re-resolving on every delivery closes that. What remains is a
narrow race — the address could change between our check and the socket connecting — which
is noted here rather than papered over; eliminating it entirely means pinning the connection
to the validated IP, which breaks TLS hostname verification unless carefully rebuilt.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ALLOWED_SCHEMES = ("http", "https")

# Instance-metadata services. Reaching any of these from inside a cloud VM typically yields
# credentials, so they are named explicitly even though most already fall inside the
# link-local range.
_METADATA_HOSTS = {
    "169.254.169.254",          # AWS, Azure, DigitalOcean, Oracle
    "metadata.google.internal",  # GCP
    "100.100.100.200",          # Alibaba
    "169.254.169.253",
    "fd00:ec2::254",            # AWS IMDS over IPv6
}

# Ports that are never a webhook receiver but are attractive to reach internally.
_BLOCKED_PORTS = {22, 23, 25, 3306, 5432, 6379, 11211, 27017, 4822}


class BlockedURL(Exception):
    """The URL is not somewhere we are willing to send a request.

    The message is written for the person who typed the URL, because the most common cause
    is an honest mistake (a localhost address from their own machine) rather than an attack.
    """


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    """Return a reason when this address must not be contacted, else None."""
    if str(ip) in _METADATA_HOSTS:
        return "that address is a cloud metadata service"
    if ip.is_loopback:
        return "that address points back at our own server"
    if ip.is_link_local:
        return "link-local addresses aren't reachable from here"
    if ip.is_private:
        return "that's a private network address, not reachable from the internet"
    if ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return "that address is reserved"
    # An IPv4-mapped IPv6 address (::ffff:127.0.0.1) must be judged on its IPv4 value.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return _is_forbidden_ip(mapped)
    return None


def _resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Every address the hostname currently resolves to. Raises BlockedURL if it cannot."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise BlockedURL(f"We couldn't find '{host}'. Check the address is spelled correctly.")
    out = []
    for info in infos:
        try:
            out.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    if not out:
        raise BlockedURL(f"We couldn't find '{host}'. Check the address is spelled correctly.")
    return out


def check_url(url: str) -> str:
    """Validate a customer-supplied URL, resolving it. Returns the normalised URL.

    Raises ``BlockedURL`` with a message the customer can act on.
    """
    if not url or len(url) > 2000:
        raise BlockedURL("Please enter a web address.")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise BlockedURL("The address must start with http:// or https://.")
    if not parsed.hostname:
        raise BlockedURL("That address is missing a host name.")

    port = parsed.port
    if port is not None and port in _BLOCKED_PORTS:
        raise BlockedURL(f"Port {port} isn't a web address we can send to.")

    host = parsed.hostname.lower().rstrip(".")
    if host in _METADATA_HOSTS:
        raise BlockedURL("That address is a cloud metadata service.")

    # A literal IP is judged directly; a hostname is judged by what it resolves to, so a
    # name pointing at an internal address is caught too.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None

    addresses = [literal] if literal is not None else _resolve(host)
    for ip in addresses:
        reason = _is_forbidden_ip(ip)
        if reason:
            raise BlockedURL(
                f"We can't send to {host} — {reason}. Use a public address your server "
                f"can reach from the internet."
            )

    return url.strip()


def is_safe(url: str) -> bool:
    """Convenience for callers that only need a yes/no."""
    try:
        check_url(url)
        return True
    except BlockedURL:
        return False
