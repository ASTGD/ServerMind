"""Phase B — the DirectAdmin hosting adapter. No live DA panel at build time, so lock the
auth / URL-encoded-parse / error / list / create paths against mocked HTTP responses
(the same discipline the other panel adapters were built with)."""
from unittest.mock import MagicMock, patch

import pytest

from app.services import hosting_service as hs
from app.services.hosting_service import DirectAdminAdapter, HostingError


def _resp(text: str = "", status: int = 200) -> MagicMock:
    m = MagicMock()
    m.text = text
    m.status_code = status
    return m


def _adapter() -> DirectAdminAdapter:
    return DirectAdminAdapter("da.example.com", 2222, "admin", "secret")


def test_registered_with_default_port():
    assert hs._ADAPTERS["directadmin"] is DirectAdminAdapter
    assert hs.DEFAULT_PORTS["directadmin"] == 2222


@patch("app.services.hosting_service.requests.request")
def test_connection_ok_and_uses_basic_auth(mreq):
    mreq.return_value = _resp("")  # 0 domains, no error → healthy
    assert _adapter().test_connection() == {"ok": True}
    _, kwargs = mreq.call_args
    url = mreq.call_args.args[1]
    assert url.endswith("/CMD_API_SHOW_DOMAINS")
    assert kwargs["auth"].username == "admin" and kwargs["auth"].password == "secret"


@patch("app.services.hosting_service.requests.request")
def test_auth_failure(mreq):
    mreq.return_value = _resp("", 401)
    with pytest.raises(HostingError, match="authentication failed"):
        _adapter().test_connection()


@patch("app.services.hosting_service.requests.request")
def test_html_login_page_rejected(mreq):
    # wrong port / rejected creds sometimes return the UI HTML with a 200
    mreq.return_value = _resp("<html><body>login</body></html>")
    with pytest.raises(HostingError, match="non-API"):
        _adapter().test_connection()


@patch("app.services.hosting_service.requests.request")
def test_command_error_in_body(mreq):
    mreq.return_value = _resp("error=1&text=cannot_create&details=already_exists")
    with pytest.raises(HostingError, match="cannot create"):
        _adapter().list_databases()


@patch("app.services.hosting_service.requests.request")
def test_list_websites_parses_list_keys(mreq):
    mreq.return_value = _resp("list[]=a.com&list[]=b.com")
    assert [s["domain"] for s in _adapter().list_websites()] == ["a.com", "b.com"]


@patch("app.services.hosting_service.requests.request")
def test_list_databases(mreq):
    mreq.return_value = _resp("list[]=shop_db&list[]=blog_db")
    assert [d["db_name"] for d in _adapter().list_databases()] == ["shop_db", "blog_db"]


@patch("app.services.hosting_service.requests.request")
def test_create_database_sends_expected_params(mreq):
    mreq.return_value = _resp("")
    out = _adapter().create_database({"db_name": "shop", "db_user": "shopu", "db_password": "p@ss"})
    assert out == {"status": "created", "db_name": "shop"}
    _, kwargs = mreq.call_args
    data = kwargs["data"]
    assert data["action"] == "create" and data["name"] == "shop"
    assert data["user"] == "shopu" and data["passwd"] == "p@ss" and data["passwd2"] == "p@ss"


@patch("app.services.hosting_service.requests.request")
def test_list_email_needs_a_domain(mreq):
    with pytest.raises(HostingError, match="needs a domain"):
        _adapter().list_email(None)


@patch("app.services.hosting_service.requests.request")
def test_create_email(mreq):
    mreq.return_value = _resp("")
    out = _adapter().create_email({"user": "info", "domain": "a.com", "password": "pw"})
    assert out["email"] == "info@a.com"
    _, kwargs = mreq.call_args
    assert kwargs["data"]["action"] == "create" and kwargs["data"]["domain"] == "a.com"


def test_dispatch_builds_directadmin_adapter_on_default_port():
    from app.models.server import Server
    from app.services.crypto_service import encrypt
    s = Server(host="h", port=None, username="admin", panel_type="directadmin",
               connection_type="hosting", encrypted_cred=encrypt("pw"))
    a = hs._adapter(s)
    assert isinstance(a, DirectAdminAdapter)
    assert a.port == 2222 and a.secret == "pw"
