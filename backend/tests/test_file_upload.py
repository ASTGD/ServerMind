"""Uploading a file — the bug where it worked and said it failed.

Reported live: uploads to `vev.astgd.com` were failing. Reproducing against production found
two separate faults, and the first is the one that matters:

    fastapi.exceptions.ResponseValidationError:
    {'loc': ('response', 'size'), 'msg': 'Input should be a valid string', 'input': 900000}

The endpoint was declared `-> dict[str, str]` and returned `"size": len(data)`, an int.
FastAPI validates the response against the declared type and raised — **after** the file had
already been written over SFTP. So every upload succeeded on the server and returned HTTP
500 to the customer. A failure that is really a success is the worst kind: nothing is broken,
the customer sees an error, and retries.

The second fault was a proxy limit: `client_max_body_size` was never set, so nginx's 1 MB
default rejected anything larger with its own raw HTML page.

These tests drive the REAL app, because the fault was in FastAPI's response validation —
a unit test that called the handler directly would have returned the dict happily and proved
nothing.
"""
import io

import pytest
from fastapi.testclient import TestClient

from app.routers import files as files_router


@pytest.fixture
def client(monkeypatch):
    """The real app with only the SSH hop replaced."""
    from main import app

    async def _fake_server(server_id, current_user, db, need_execute=False):
        class _S:
            id, name, connection_type = server_id, "test", "ssh"
        return _S()

    uploaded: dict = {}

    async def _fake_upload(server, path, data):
        uploaded["path"], uploaded["bytes"] = path, len(data)

    monkeypatch.setattr(files_router, "_get_server", _fake_server)
    monkeypatch.setattr(files_router.file_service, "upload_file", _fake_upload)

    async def _no_auth():
        class _U:
            id = "00000000-0000-0000-0000-000000000001"
        return _U()

    from app.dependencies.auth import get_current_user
    app.dependency_overrides[get_current_user] = _no_auth
    try:
        c = TestClient(app)
        c.uploaded = uploaded
        yield c
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def upload(client, name="notes.txt", body=b"hello", path="/tmp"):
    return client.post(
        "/api/servers/11111111-1111-1111-1111-111111111111/files/upload",
        data={"path": path},
        files={"file": (name, io.BytesIO(body), "application/octet-stream")},
    )


# ── the bug itself ───────────────────────────────────────────────────────────

def test_a_successful_upload_reports_success(client):
    """The whole bug in one line. This returned 500 while the file sat on the server."""
    r = upload(client, body=b"x" * 900_000)
    assert r.status_code == 201, r.text
    assert client.uploaded["bytes"] == 900_000


def test_the_size_comes_back_as_a_number(client):
    """`size` is a byte count. Declaring the response as all-strings is what made FastAPI
    reject our own reply."""
    r = upload(client, body=b"x" * 42)
    assert r.json()["size"] == 42
    assert isinstance(r.json()["size"], int)


def test_the_declared_type_admits_what_the_handler_returns():
    """Read off the signature, so the annotation cannot drift back to `dict[str, str]` while
    the body still returns an int."""
    import inspect

    sig = inspect.signature(files_router.upload_file)
    assert "int" in str(sig.return_annotation), sig.return_annotation


# ── the size limit ───────────────────────────────────────────────────────────

def test_the_rule_itself(monkeypatch):
    """Tested directly, because there are two call sites and they defend different things.
    Inline, disabling either left the other to catch it, and no test could tell which had
    gone — so the rule is one named function used at two moments."""
    from fastapi import HTTPException

    files_router.refuse_if_too_big(500, limit=1000)          # under — allowed
    files_router.refuse_if_too_big(None, limit=1000)         # unknown — allowed through
    with pytest.raises(HTTPException) as exc:
        files_router.refuse_if_too_big(5000, limit=1000)
    assert exc.value.status_code == 413
    assert "MB" in exc.value.detail and "limited" in exc.value.detail


def test_an_unknown_size_is_allowed_through_rather_than_refused():
    """Plenty of clients omit a per-part length. Refusing every one of those to stop a rare
    liar would break ordinary uploads — the second check catches it after reading."""
    files_router.refuse_if_too_big(None, limit=1)


def test_the_declared_size_is_checked_BEFORE_the_body_is_read():
    """The reason the first call exists. Refusing after reading still costs the allocation
    the limit is there to prevent."""
    import inspect

    body = "\n".join(ln for ln in inspect.getsource(files_router.upload_file).splitlines()
                     if not ln.strip().startswith("#"))
    assert body.index("refuse_if_too_big(file.size)") < body.index("await file.read()")


def test_the_received_bytes_are_checked_too():
    """The reason the second call exists: a client that under-reports its own size."""
    import inspect

    body = inspect.getsource(files_router.upload_file)
    assert "refuse_if_too_big(len(data))" in body


def test_an_oversized_upload_is_refused_with_a_readable_reason(client, monkeypatch):
    """Rather than nginx's raw HTML page. The backend's cap sits BELOW the proxy's so this
    message is the one the customer actually gets."""
    monkeypatch.setattr(files_router, "MAX_UPLOAD_BYTES", 1000)
    r = upload(client, body=b"x" * 5000)
    assert r.status_code == 413
    detail = r.json()["detail"]
    assert "limit" in detail.lower() and "MB" in detail


def test_the_oversized_file_is_never_written(client, monkeypatch):
    """Refused BEFORE the SFTP write — the ordering that makes the limit a limit rather
    than a message after the fact."""
    monkeypatch.setattr(files_router, "MAX_UPLOAD_BYTES", 1000)
    upload(client, body=b"x" * 5000)
    assert client.uploaded == {}, "an oversized upload reached the server"


def test_the_backend_cap_is_below_the_proxy_limit():
    """If the proxy's limit were the lower of the two, an oversized upload would be answered
    by nginx with raw HTML instead of our sentence — which is what the customer hit."""
    import pathlib as _p
    import re

    conf = _p.Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf"
    m = re.search(r"client_max_body_size\s+(\d+)m", conf.read_text())
    assert m, "nginx has no client_max_body_size — its 1 MB default silently applies"
    proxy_mb = int(m.group(1))
    assert proxy_mb > files_router.MAX_UPLOAD_BYTES // (1024 * 1024), (
        f"the proxy allows {proxy_mb} MB but the app allows "
        f"{files_router.MAX_UPLOAD_BYTES // (1024 * 1024)} MB — the proxy must be the "
        f"looser of the two so the app's message wins")


# ── the ordinary path still works ────────────────────────────────────────────

def test_the_file_lands_where_it_was_asked_to(client):
    upload(client, name="report.pdf", path="/var/www/html")
    assert client.uploaded["path"] == "/var/www/html/report.pdf"


def test_a_path_cannot_climb_out_of_the_directory(client):
    """`..` in the destination is normalised away rather than followed."""
    upload(client, name="x.txt", path="/var/www/../../etc")
    assert client.uploaded["path"] == "/etc/x.txt"
