"""totp_service — 2FA secret/verify + recovery codes (Update 14.3 / 14.3b)."""
import pyotp

from app.services import totp_service as t


def test_generate_verify_current_code():
    secret = t.generate_secret()
    enc = t.encrypt_secret(secret)
    assert t.verify(enc, pyotp.TOTP(secret).now()) is True


def test_verify_rejects_empty_and_none():
    enc = t.encrypt_secret(t.generate_secret())
    assert t.verify(enc, "") is False
    assert t.verify(enc, None) is False
    assert t.verify(None, "123456") is False


def test_verify_bad_secret_returns_false_not_raise():
    # An undecryptable secret must not 500 the caller — verify() swallows it.
    assert t.verify("not-a-real-encrypted-blob", "123456") is False


def test_secret_stored_encrypted_and_fits_column():
    secret = t.generate_secret()
    enc = t.encrypt_secret(secret)
    assert enc != secret           # encrypted, not plaintext
    assert len(enc) <= 255         # fits VARCHAR(255)


def test_provisioning_uri_format():
    uri = t.provisioning_uri(t.generate_secret(), "alice@example.com")
    assert uri.startswith("otpauth://totp/")
    assert "ServerMind" in uri


def test_recovery_codes_generation():
    codes = t.generate_recovery_codes()
    assert len(codes) == t.RECOVERY_CODE_COUNT
    assert len(set(codes)) == len(codes)   # unique


def test_recovery_code_hash_is_normalized():
    codes = t.generate_recovery_codes()
    hashes = [t.hash_code(c) for c in codes]
    c = codes[0]
    # case + dash insensitive
    assert t.hash_code(c.upper().replace("-", "")) == t.hash_code(c)
    assert t.hash_code(c) in hashes
    assert t.hash_code("zzzz-zzzz") not in hashes
