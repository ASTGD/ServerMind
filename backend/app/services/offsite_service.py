"""Offsite backup storage — S3-compatible buckets, reached by presigned URL.

**The design decision that matters: the managed server never receives the bucket
credentials.** We generate a short-lived presigned URL here (boto3, already a dependency
for `cloud_service`) and the server uploads to it with plain `curl` — so:

- No AWS CLI / rclone to install on the customer's box.
- A compromised server cannot read the bucket, list other backups, or delete history;
  it holds only a one-hour, single-object URL.
- The archive goes **server → storage directly**; backup data never passes through us.

The URL is handed to `curl` through a `-K` config file (mode 600, shredded after) rather
than argv, so it never appears in `ps` output or shell history on the server.

Every provider below speaks the S3 API: AWS S3, Cloudflare R2, Backblaze B2, DigitalOcean
Spaces, Wasabi and MinIO.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from app.models.backup_destination import BackupDestination
from app.services import crypto_service

logger = logging.getLogger(__name__)

# Presigned URLs are deliberately short-lived: long enough for a big upload over a slow
# link, short enough that a leaked URL is near-worthless.
PRESIGN_TTL_SECONDS = 3600

# S3 caps a single (non-multipart) PUT at 5 GiB. We upload in one PUT, so a larger archive
# is refused with an honest message rather than failing deep inside curl.
MAX_SINGLE_PUT_BYTES = 5 * 1024 * 1024 * 1024


class OffsiteError(Exception):
    """A destination could not be reached or used. Message is safe to show a user."""


def _secret(dest: BackupDestination) -> str:
    try:
        return crypto_service.decrypt(dest.encrypted_secret_key)
    except Exception as exc:  # noqa: BLE001
        raise OffsiteError("Could not read this destination's stored secret key.") from exc


def _client(dest: BackupDestination):
    """A boto3 S3 client for this destination. boto3 is imported lazily so the module
    still imports when it isn't installed."""
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover — boto3 is in requirements
        raise OffsiteError("Object-storage support is not available on this server.") from exc

    return boto3.session.Session(
        aws_access_key_id=dest.access_key_id,
        aws_secret_access_key=_secret(dest),
        region_name=dest.region or "us-east-1",
    ).client(
        "s3",
        endpoint_url=dest.endpoint_url or None,
        # SigV4 + path-style keeps R2/B2/MinIO happy; AWS accepts both.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def object_key(dest: BackupDestination, backup_name_slug: str, filename: str) -> str:
    """Where an archive lives in the bucket: <prefix>/<job-slug>/<filename>."""
    parts = [(dest.prefix or "").strip("/"), backup_name_slug, filename]
    return "/".join(p for p in parts if p)


def _friendly(exc: Exception) -> str:
    """Turn a botocore error into something a non-technical owner can act on."""
    text = str(exc)
    if "NoSuchBucket" in text or "404" in text:
        return "That bucket does not exist (check the bucket name and region)."
    if "InvalidAccessKeyId" in text or "AccessDenied" in text or "403" in text:
        return "The storage provider rejected these keys, or they lack permission on this bucket."
    if "SignatureDoesNotMatch" in text:
        return "The secret key looks wrong — the provider rejected the signature."
    if "EndpointConnectionError" in text or "Could not connect" in text:
        return "Could not reach that endpoint URL. Check it and try again."
    return f"Storage error: {type(exc).__name__}"


async def verify(dest: BackupDestination) -> None:
    """Prove we can actually write to this bucket before a customer relies on it.

    Writes then deletes a tiny probe object — a list-only check would pass on a
    read-only key and fail at 2am during a real backup. Raises OffsiteError on failure.
    """
    import asyncio

    def _run() -> None:
        client = _client(dest)
        probe = object_key(dest, "_serverally", "connection-test.txt")
        try:
            client.put_object(Bucket=dest.bucket, Key=probe, Body=b"serverally connection test\n")
            client.delete_object(Bucket=dest.bucket, Key=probe)
        except Exception as exc:  # noqa: BLE001
            raise OffsiteError(_friendly(exc)) from exc

    await asyncio.to_thread(_run)


async def presign_put(dest: BackupDestination, key: str) -> str:
    """A short-lived URL the server can PUT one object to."""
    import asyncio

    def _run() -> str:
        try:
            return _client(dest).generate_presigned_url(
                "put_object",
                Params={"Bucket": dest.bucket, "Key": key},
                ExpiresIn=PRESIGN_TTL_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            raise OffsiteError(_friendly(exc)) from exc

    return await asyncio.to_thread(_run)


async def presign_get(dest: BackupDestination, key: str) -> str:
    """A short-lived URL the server can GET one object from (used by restore)."""
    import asyncio

    def _run() -> str:
        try:
            return _client(dest).generate_presigned_url(
                "get_object",
                Params={"Bucket": dest.bucket, "Key": key},
                ExpiresIn=PRESIGN_TTL_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            raise OffsiteError(_friendly(exc)) from exc

    return await asyncio.to_thread(_run)


async def prune_remote(dest: BackupDestination, prefix: str, keep: int) -> int:
    """Keep only the newest ``keep`` objects under ``prefix``. Returns how many were
    deleted. Retention has to apply offsite too, or the bucket grows forever."""
    import asyncio

    def _run() -> int:
        client = _client(dest)
        try:
            objs: list[dict] = []
            token = None
            while True:
                kwargs = {"Bucket": dest.bucket, "Prefix": prefix}
                if token:
                    kwargs["ContinuationToken"] = token
                page = client.list_objects_v2(**kwargs)
                objs.extend(page.get("Contents") or [])
                token = page.get("NextContinuationToken")
                if not page.get("IsTruncated"):
                    break
            if len(objs) <= keep:
                return 0
            objs.sort(key=lambda o: o.get("LastModified") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            stale = objs[keep:]
            # delete_objects caps at 1000 keys per call.
            deleted = 0
            for i in range(0, len(stale), 1000):
                batch = [{"Key": o["Key"]} for o in stale[i:i + 1000]]
                client.delete_objects(Bucket=dest.bucket, Delete={"Objects": batch})
                deleted += len(batch)
            return deleted
        except Exception as exc:  # noqa: BLE001
            raise OffsiteError(_friendly(exc)) from exc

    return await asyncio.to_thread(_run)


# ── Shell commands run on the managed server ─────────────────────────────────
# The presigned URL is written to a mode-600 curl config file and shredded afterwards, so
# it never lands in argv (visible via `ps`) or shell history.

def build_upload_command(archive: str, url: str) -> str:
    """Upload ``archive`` to the presigned ``url``. Emits __SMUP__=<http_code>."""
    return (
        "umask 077; CFG=$(mktemp); "
        f"printf 'url = \"%s\"\\n' {_shq(url)} > \"$CFG\"; "
        f"CODE=$(curl -sS -K \"$CFG\" -X PUT --upload-file {_shq(archive)} "
        "-w '%{http_code}' -o /tmp/.sm_up_err 2>/tmp/.sm_up_err2); rc=$?; "
        "shred -u \"$CFG\" 2>/dev/null || rm -f \"$CFG\"; "
        "echo __SMUP__=$CODE; "
        "[ \"$CODE\" != \"200\" ] && head -c 400 /tmp/.sm_up_err /tmp/.sm_up_err2 2>/dev/null; "
        "rm -f /tmp/.sm_up_err /tmp/.sm_up_err2; "
        "[ \"$CODE\" = \"200\" ] || exit 1; exit $rc"
    )


def build_download_command(url: str, dest_path: str) -> str:
    """Download the presigned ``url`` to ``dest_path`` (used before a restore)."""
    return (
        "umask 077; CFG=$(mktemp); "
        f"printf 'url = \"%s\"\\n' {_shq(url)} > \"$CFG\"; "
        f"CODE=$(curl -sS -K \"$CFG\" -o {_shq(dest_path)} -w '%{{http_code}}'); rc=$?; "
        "shred -u \"$CFG\" 2>/dev/null || rm -f \"$CFG\"; "
        "echo __SMDL__=$CODE; "
        f"[ \"$CODE\" = \"200\" ] || {{ rm -f {_shq(dest_path)}; exit 1; }}; exit $rc"
    )


def _shq(value: str) -> str:
    """Single-quote for the shell (mirrors backup_service._q)."""
    return "'" + str(value).replace("'", "'\\''") + "'"


_UP_RE = re.compile(r"__SMUP__=(\d+)")
_DL_RE = re.compile(r"__SMDL__=(\d+)")


def parse_upload_code(stdout: str) -> int | None:
    m = _UP_RE.search(stdout or "")
    return int(m.group(1)) if m else None


def scrub_urls(text: str) -> str:
    """Remove any presigned URL that leaked into command output before it is stored or
    shown. A presigned URL is a bearer credential — it must never reach the DB or the UI."""
    if not text:
        return text
    text = re.sub(r"https?://[^\s\"']*[?&]X-Amz-Signature=[^\s\"']*", "[storage URL hidden]", text)
    text = re.sub(r"https?://[^\s\"']*[?&]Signature=[^\s\"']*", "[storage URL hidden]", text)
    return _UP_RE.sub("", _DL_RE.sub("", text)).strip()
