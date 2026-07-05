"""Phase E — RDP session issuance + the Windows/enabled guard. The access gate itself
(viewer refused) is enforced by the shared `resolve_server(need_execute=True)` dependency,
which is unit-tested against Postgres for every execution path (CLAUDE.md rule 7); here we
lock the service-level guards + the short-lived signed token."""
import uuid

import pytest
from jose import jwt

from app.config import settings
from app.models.server import Server
from app.models.user import User
from app.services import rdp_service
from app.services.rdp_service import RdpError


def _win(enabled: bool) -> Server:
    return Server(id=uuid.uuid4(), user_id=uuid.uuid4(), name="win1", host="10.0.0.9", port=5985,
                  username="Administrator", auth_type="password", connection_type="winrm",
                  category="windows", encrypted_cred="x", rdp_enabled=enabled)


def _user() -> User:
    return User(id=uuid.uuid4(), email="u@x.com", password_hash="h")


def test_non_windows_asset_refused():
    linux = Server(id=uuid.uuid4(), user_id=uuid.uuid4(), name="lin", host="1.2.3.4", port=22,
                   username="root", auth_type="key", connection_type="ssh", encrypted_cred="x",
                   rdp_enabled=True)  # even if flagged, ssh transport can't RDP
    with pytest.raises(RdpError, match="Windows assets only"):
        rdp_service.ensure_available(linux)


def test_windows_asset_with_rdp_off_refused():
    with pytest.raises(RdpError, match="turned off"):
        rdp_service.ensure_available(_win(enabled=False))


def test_windows_asset_enabled_ok():
    rdp_service.ensure_available(_win(enabled=True))  # no raise


def test_issue_session_mints_short_lived_scoped_token():
    server, user = _win(enabled=True), _user()
    out = rdp_service.issue_session(server, user)
    assert out["host"] == "10.0.0.9" and out["port"] == 3389
    assert out["expires_in"] == settings.RDP_SESSION_TTL_SECONDS
    claims = jwt.decode(out["session_token"], settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert claims["type"] == "rdp"
    assert claims["server_id"] == str(server.id)
    assert claims["sub"] == str(user.id)
    assert "exp" in claims


def test_issue_session_refuses_disabled_asset():
    with pytest.raises(RdpError):
        rdp_service.issue_session(_win(enabled=False), _user())


def test_streaming_available_reflects_config(monkeypatch):
    monkeypatch.setattr(settings, "RDP_GUACD_URL", "")
    assert rdp_service.issue_session(_win(True), _user())["streaming_available"] is False
    monkeypatch.setattr(settings, "RDP_GUACD_URL", "ws://guacd:4822")
    assert rdp_service.issue_session(_win(True), _user())["streaming_available"] is True
