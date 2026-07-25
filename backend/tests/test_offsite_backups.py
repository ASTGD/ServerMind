"""Offsite backup guarantees (docs/MARKET-RESEARCH-2026-07.md §8.2, Wave 1).

The properties that matter are security properties, and they are all about one thing:
**a presigned URL is a bearer credential.** Anyone holding it can write (or read) that
object, so it must never reach the process list, the database, or the UI — and the bucket's
real secret key must never reach the managed server or an API response at all.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.backup_destination import BackupDestination
from app.schemas.backup import DestinationOut
from app.services import offsite_service

_URL = (
    "https://bucket.r2.cloudflarestorage.com/backups/site-20260725.tar.gz"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=AKIAEXAMPLE%2F20260725"
    "&X-Amz-Signature=deadbeefcafe1234&X-Amz-Expires=3600"
)


def _dest(**kw) -> BackupDestination:
    return BackupDestination(
        id=uuid.uuid4(), user_id=uuid.uuid4(), name="R2 main", provider="r2",
        bucket="backups", region="auto",
        endpoint_url="https://acct.r2.cloudflarestorage.com",
        access_key_id="AKIAEXAMPLE",
        encrypted_secret_key="AES256GCM::do-not-leak-this-secret",
        created_at=datetime.now(tz=timezone.utc), **kw
    )


# ── The presigned URL must never leak ────────────────────────────────────────

def test_scrub_removes_presigned_urls():
    """Command output is stored in backup_runs.output and shown in the UI — a signed URL
    in there would be a live credential in the database."""
    out = offsite_service.scrub_urls(f"curl: uploading to {_URL}\ndone __SMUP__=200")
    assert "deadbeefcafe1234" not in out, "signature leaked"
    assert "X-Amz-Signature" not in out
    assert "AKIAEXAMPLE" not in out
    assert "[storage URL hidden]" in out
    assert "__SMUP__" not in out  # internal marker stripped too


def test_scrub_handles_non_aws_signature_style():
    """Some S3-compatible providers sign with a bare `Signature=` parameter."""
    url = "https://s3.example.com/b/k?AWSAccessKeyId=AK&Signature=abc123XYZ&Expires=1"
    assert "abc123XYZ" not in offsite_service.scrub_urls(f"failed for {url}")


def test_scrub_is_safe_on_empty_and_plain_text():
    assert offsite_service.scrub_urls("") == ""
    assert offsite_service.scrub_urls("tar: some warning") == "tar: some warning"


# ── The URL must not be visible in `ps` on the managed server ────────────────

def test_upload_command_keeps_url_out_of_argv():
    cmd = offsite_service.build_upload_command("/var/backups/a.tar.gz", _URL)
    # The URL is written into a curl config file (-K), not passed as an argument.
    assert "-K" in cmd and "mktemp" in cmd
    assert cmd.count(_URL) == 1, "URL should appear exactly once — in the config write"
    before = cmd.split(_URL)[0]
    assert "printf" in before[-100:], "URL must be written via printf into the config file"
    # And the config file is destroyed afterwards.
    assert "shred -u" in cmd or "rm -f" in cmd
    # It must never be handed to curl as a positional URL argument.
    assert f"curl -sS {_URL}" not in cmd


def test_download_command_keeps_url_out_of_argv():
    cmd = offsite_service.build_download_command(_URL, "/tmp/restore.tar.gz")
    assert "-K" in cmd and cmd.count(_URL) == 1
    assert "shred -u" in cmd or "rm -f" in cmd


def test_upload_command_reports_http_status():
    cmd = offsite_service.build_upload_command("/a.gz", _URL)
    assert "__SMUP__" in cmd
    assert offsite_service.parse_upload_code("noise __SMUP__=200 more") == 200
    assert offsite_service.parse_upload_code("__SMUP__=403") == 403
    assert offsite_service.parse_upload_code("no marker") is None


# ── The bucket secret must never leave the backend ───────────────────────────

def test_destination_out_never_exposes_the_secret():
    """The API view is the one place a secret could escape to a browser."""
    payload = DestinationOut.model_validate(_dest()).model_dump_json()
    assert "do-not-leak-this-secret" not in payload
    assert "encrypted_secret_key" not in payload
    assert "secret_key" not in payload
    # The access key id is NOT secret and is shown so users can identify the key.
    assert "AKIAEXAMPLE" in payload


# ── Object layout + limits ───────────────────────────────────────────────────

def test_object_key_layout():
    d = _dest()
    assert offsite_service.object_key(d, "nightly", "a.tar.gz") == "nightly/a.tar.gz"
    d.prefix = "servers/web1/"
    assert offsite_service.object_key(d, "nightly", "a.tar.gz") == "servers/web1/nightly/a.tar.gz"
    # A prefix-only key (used for retention listing) has no trailing junk.
    assert offsite_service.object_key(d, "nightly", "") == "servers/web1/nightly"


def test_single_put_limit_is_the_s3_maximum():
    """We upload in one PUT; S3 caps that at 5 GiB. Larger archives are refused with an
    honest message rather than failing deep inside curl."""
    assert offsite_service.MAX_SINGLE_PUT_BYTES == 5 * 1024 * 1024 * 1024


def test_presign_ttl_is_short():
    """A leaked URL should expire quickly."""
    assert 0 < offsite_service.PRESIGN_TTL_SECONDS <= 3600


# ── Error messages must tell the owner what to fix ───────────────────────────

def test_friendly_errors_name_the_actual_fix():
    """Live testing produced "Storage error: SSLError" for a typo'd endpoint, which tells
    the owner nothing. Each class of failure must name its own fix."""
    import ssl

    f = offsite_service._friendly
    assert "bucket" in f(Exception("NoSuchBucket: the bucket does not exist")).lower()
    assert "secret key" in f(Exception("SignatureDoesNotMatch")).lower()
    assert "keys" in f(Exception("InvalidAccessKeyId")).lower()
    # A bad endpoint is the most common setup mistake — it must point at the URL.
    assert "endpoint" in f(ssl.SSLError("bad handshake")).lower()
    assert "endpoint" in f(Exception("Could not connect to the endpoint URL")).lower()
    assert "secure connection" in f(ssl.SSLCertVerificationError("cert")).lower()
    # Unknown errors still degrade gracefully rather than leaking a stack trace.
    assert f(ValueError("weird")) == "Storage error: ValueError"


def test_auth_failure_is_not_mistaken_for_a_missing_bucket():
    """A 403 mentions neither word, but must not fall through to the 404 branch."""
    msg = offsite_service._friendly(Exception("An error occurred (403) when calling PutObject"))
    assert "reject" in msg.lower() or "cannot write" in msg.lower()
