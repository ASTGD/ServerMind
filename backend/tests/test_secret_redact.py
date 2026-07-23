"""Server-side secret redaction (app/services/secret_redact.py).

The MCP read_file tool runs this before returning any file to a customer's AI, so a
password/key/token must be masked and ordinary config must NOT be (false positives make
the feature useless). Ported from the client filter; these lock the behaviour.
"""
from __future__ import annotations

from app.services.secret_redact import SECRET_MASK, redact_secrets


def _masked(text: str) -> bool:
    return SECRET_MASK in redact_secrets(text)[0]


def test_masks_env_style_secret_value_keeps_key():
    out, n = redact_secrets("DB_PASSWORD=hunter2")
    assert out == "DB_PASSWORD=[secret hidden]" and n == 1


def test_masks_wp_config_define():
    out, _ = redact_secrets("define('DB_PASSWORD', 's3cr3t');")
    assert "DB_PASSWORD" in out and "s3cr3t" not in out and SECRET_MASK in out


def test_masks_connection_string_password():
    out, _ = redact_secrets("url = mysql://user:p4ss@db:3306/app")
    assert "mysql://user:" in out and "p4ss" not in out


def test_masks_standalone_tokens():
    assert _masked("token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    assert _masked("aws AKIAIOSFODNN7EXAMPLE here")
    assert _masked("jwt eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF")


def test_masks_pem_private_key_body():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"
    out, _ = redact_secrets(pem)
    assert "MIIEowIBAAKCAQEA" not in out and out.startswith("-----BEGIN")


def test_masks_yaml_block_scalar_under_sensitive_key():
    out, _ = redact_secrets("password: |\n  supersecret\n  line2\nother: keepme")
    assert "supersecret" not in out and "keepme" in out


def test_no_false_positive_on_ordinary_config():
    text = "app_name: myapp\nport: 8080\nhost: localhost\npublic_key_url: https://x/k"
    out, n = redact_secrets(text)
    assert n == 0 and out == text


def test_empty_string_is_safe():
    assert redact_secrets("") == ("", 0)
