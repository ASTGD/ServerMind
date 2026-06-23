"""auth_service — JWT (with token_version) + password hashing."""
from app.services import auth_service as a


def test_password_hash_and_verify():
    h = a.hash_password("correct horse battery")
    assert h != "correct horse battery"
    assert a.verify_password("correct horse battery", h) is True
    assert a.verify_password("wrong", h) is False


def test_access_token_claims_include_tv():
    payload = a.decode_token(a.create_access_token("user-1", 7))
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"
    assert payload["tv"] == 7


def test_refresh_token_type():
    payload = a.decode_token(a.create_refresh_token("user-1", 3))
    assert payload["type"] == "refresh"
    assert payload["tv"] == 3


def test_default_token_version_is_zero():
    payload = a.decode_token(a.create_access_token("user-1"))
    assert payload["tv"] == 0


def test_decode_garbage_returns_none():
    assert a.decode_token("not.a.jwt") is None
    assert a.decode_token("") is None
