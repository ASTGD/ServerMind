"""Remote Desktop (RDP) service — Assets Phase E.

RDP is a human-driven capability (a person moves the mouse), so it sits OUTSIDE the
AI-safety envelope. This module does NOT stream pixels itself; a purpose-built Apache
Guacamole (`guacd`) service does that (matches our near-zero-infra pattern). What lives
here is the security-critical part: (1) it only offers a desktop for a Windows asset that
has RDP explicitly enabled, and (2) it issues a short-lived, signed session token that the
browser hands to the desktop viewer. Every caller is access-checked by the router via
`resolve_server(need_execute=True)` — a viewer role can never open a live desktop.

The actual guacd tunnel + guacamole-common-js client is the remaining piece (needs a live
Windows/RDP host to validate); until `RDP_GUACD_URL` is set, `streaming_available` is False
and the viewer says so honestly instead of showing a broken canvas.
"""
from __future__ import annotations

import asyncio
import time
from datetime import timedelta

from app.config import settings
from app.models.server import Server
from app.models.user import User
from app.services.auth_service import _create_token

RDP_PORT = 3389
_REACH_TIMEOUT_S = 8.0


class RdpError(Exception):
    """RDP isn't available for this asset (not Windows, or not enabled)."""


# A pure-RDP asset (connection_type 'rdp') is enabled for the desktop by design — you added
# it precisely to reach its desktop. A WinRM-managed Windows box must opt in via rdp_enabled.
_RDP_CAPABLE = ("winrm", "rdp")


def ensure_available(server: Server) -> None:
    """Raise RdpError unless this asset can offer a remote desktop."""
    if server.connection_type not in _RDP_CAPABLE:
        raise RdpError("Remote Desktop is available on Windows assets only.")
    if server.connection_type == "winrm" and not server.rdp_enabled:
        raise RdpError("Remote Desktop is turned off for this asset. Enable it first.")


async def test_connection(host: str, port: int) -> dict:
    """RDP has no command channel to 'log in' to from here, so the meaningful check is
    whether the Remote Desktop service is actually LISTENING and reachable. Do a bounded
    TCP connect to host:port — success means the desktop is reachable (the guacd viewer can
    then take over with the stored credentials). Returns the ConnectionResult dict shape."""
    start = time.monotonic()

    def _ms() -> int:
        return int((time.monotonic() - start) * 1000)

    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=_REACH_TIMEOUT_S)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 — the reachability answer is already "yes"
            pass
        return {"ok": True, "latency_ms": _ms()}
    except asyncio.TimeoutError:
        return {
            "ok": False, "latency_ms": _ms(),
            "error": f"RDP port {port} did not respond (timed out). Is the server on and Remote Desktop enabled?",
        }
    except (ConnectionRefusedError, OSError) as exc:
        return {
            "ok": False, "latency_ms": _ms(),
            "error": f"Couldn't reach Remote Desktop on {host}:{port} — {exc.__class__.__name__}. "
                     "Check the host/IP, the port, and that Remote Desktop is turned on.",
        }


def streaming_available() -> bool:
    """Whether the guacd desktop-streaming service is deployed."""
    return bool(settings.RDP_GUACD_URL)


def issue_session(server: Server, user: User) -> dict:
    """Validate + mint a short-lived session for the desktop viewer. The RDP credentials
    are NEVER returned to the browser — the token references a server-side session the guacd
    tunnel resolves; the client only gets a bearer token + where to connect."""
    ensure_available(server)
    token = _create_token(
        {"sub": str(user.id), "type": "rdp", "server_id": str(server.id)},
        timedelta(seconds=settings.RDP_SESSION_TTL_SECONDS),
    )
    return {
        "session_token": token,
        "host": server.host,
        "port": RDP_PORT,
        "expires_in": settings.RDP_SESSION_TTL_SECONDS,
        "streaming_available": streaming_available(),
    }
