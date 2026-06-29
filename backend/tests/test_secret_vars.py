"""Secret-aware install inputs — encrypt at rest, mask in UI (Update 23.1)."""
from app.services import secret_vars


def test_encrypts_only_secret_named():
    v = {"DOMAIN": "ex.com", "DB_PASS": "p@ss", "ADMIN_PASSWORD": "x", "PORT": "80"}
    enc = secret_vars.encrypt_variables(v)
    assert enc["DOMAIN"] == "ex.com" and enc["PORT"] == "80"          # non-secret untouched
    assert enc["DB_PASS"].startswith("enc:v1:")                        # secret encrypted
    assert enc["ADMIN_PASSWORD"].startswith("enc:v1:")


def test_roundtrip():
    enc = secret_vars.encrypt_variables({"DB_PASS": "s3cr3t!"})
    assert secret_vars.decrypt_variable(enc["DB_PASS"]) == "s3cr3t!"


def test_idempotent_safe_for_backfill():
    enc = secret_vars.encrypt_variables({"DB_PASS": "a"})
    assert secret_vars.encrypt_variables(enc) == enc                   # re-encrypt is a no-op


def test_mask_never_shows_value_or_ciphertext():
    enc = secret_vars.encrypt_variables({"DOMAIN": "ex.com", "DB_PASS": "a"})
    masked = secret_vars.mask_variables(enc)
    assert masked["DB_PASS"] == "••••••" and masked["DOMAIN"] == "ex.com"


def test_is_secret():
    assert secret_vars.is_secret("DB_PASS") and secret_vars.is_secret("api_key")
    assert not secret_vars.is_secret("DOMAIN") and not secret_vars.is_secret("PORT")
