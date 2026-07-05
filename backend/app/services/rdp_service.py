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

from datetime import timedelta

from app.config import settings
from app.models.server import Server
from app.models.user import User
from app.services.auth_service import _create_token

RDP_PORT = 3389


class RdpError(Exception):
    """RDP isn't available for this asset (not Windows, or not enabled)."""


def ensure_available(server: Server) -> None:
    """Raise RdpError unless this asset can offer a remote desktop."""
    if server.connection_type != "winrm":
        raise RdpError("Remote Desktop is available on Windows assets only.")
    if not server.rdp_enabled:
        raise RdpError("Remote Desktop is turned off for this asset. Enable it first.")


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
