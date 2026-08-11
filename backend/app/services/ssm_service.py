"""Reaching inside an EC2 instance through AWS Systems Manager, with no key and no open port.

**Why this exists.** Everything else here dials IN — SSH to 22, WinRM to 5985 — which needs a
reachable address, an inbound rule, and a credential somebody has to hold. That last one is
the worst part of the job for an agency: fifty clients means fifty `.pem` files, and the
question of who has them and what happens when that person leaves. SSM removes all three. The
agent on the instance dials OUT, so an instance with **no public IP at all** and **port 22
closed entirely** is still reachable, and access is IAM — granted and revoked centrally, with
no artefact to lose. For a customer under PCI or HIPAA, where inbound SSH is simply forbidden,
this is the only sanctioned path, which today means we cannot serve them at all.

**Why it fits without touching anything else.** Every transport in this codebase meets one
contract — ``execute(server, command) -> (stdout, stderr, exit_code)`` — and SSM's
``SendCommand`` + ``GetCommandInvocation`` produce exactly that shape. No session protocol, no
plugin binary. So OS detection, metrics, site discovery, the security and malware scans, log
discovery, databases, cron, daemons, PHP versions, firewall, playbooks, Ally and missions all
work over it unchanged.

**Where the credential lives, and where it does not.** An SSM server has no login of its own.
It carries a ``cloud_account_id``, and the AWS key on THAT row is what we call AWS with — from
here, in our process. The managed server receives a command and nothing else. That is the same
rule `offsite_service` follows with presigned URLs, and it is the reason this is safe to point
at somebody else's account.

**What it cannot do, said rather than hidden.**

- **Output is capped at 24,000 characters** unless SSM is configured to spill to S3, and
  several of our probes are bigger than that. A malware scan that is quietly cut short reads
  as *fewer findings*, which is the same false all-clear the privilege work was written to
  stop — so a truncated result says so, loudly, every time.
- **There is no live stream.** ``execute_stream`` runs the command and yields the result at
  the end, after saying it will, because a progress box that sits empty for four minutes reads
  as a hang.
- **An instance without the agent or without an instance role is not managed**, and that is
  the normal case rather than an error. It is reported as *not reachable this way, and here is
  the fix* — never as a server that answered with nothing.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

from app.models.server import Server
from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)

#: How much output `GetCommandInvocation` will return inline. AWS's own documented limit;
#: beyond it the content is cut and the rest is only available if the command was sent with an
#: S3 output location. Phase 6 adds that; until then this number is a fact we must report.
INLINE_OUTPUT_LIMIT = 24_000

#: The banner a caller — and a customer — sees when output was cut. Deliberately unmistakable:
#: the failure this guards against is a scan that looks complete and is not.
TRUNCATED_NOTICE = (
    "[ServerAlly] AWS Systems Manager returned only the first {n} characters of this "
    "command's output and discarded the rest. What you see above is INCOMPLETE — do not "
    "read it as the whole answer."
)

#: How long to wait between polls, and for how long in total. SSM is poll-based, so every
#: command carries latency SSH does not; the first poll is quick because most of our probes
#: finish in well under a second.
_POLL_START = 0.4
_POLL_MAX = 2.0


class SsmError(Exception):
    """Something the customer can read and act on."""


class NotManaged(SsmError):
    """The instance is not registered with Systems Manager.

    Its own class because this is the ordinary case, not a fault: most instances have never
    been given an instance role, and the answer is a short list of things to switch on rather
    than a stack trace.
    """


_FIX = (
    "To manage it this way the instance needs three things: the SSM agent running (it is "
    "preinstalled on Amazon Linux and on Canonical's Ubuntu images), an instance role "
    "carrying the AmazonSSMManagedInstanceCore policy (most instances have no role at all), "
    "and a route out to the Systems Manager endpoints — either internet egress or VPC "
    "endpoints. Nothing needs to be opened INWARD."
)


# ── Talking to AWS ───────────────────────────────────────────────────────────

def _client(server: Server, account) -> object:
    """An SSM client for the account this server was imported from.

    The credential is decrypted HERE, in our process, and used HERE. It is never passed to the
    managed instance, never written to a file on it, and never appears in a command — the same
    guarantee the offsite-backup work makes about bucket keys.
    """
    import boto3  # lazy — this module must import cleanly without boto3 installed

    cred = json.loads(decrypt(account.encrypted_credential))
    region = _region_for(server, cred)
    return boto3.session.Session(
        aws_access_key_id=cred.get("access_key_id"),
        aws_secret_access_key=cred.get("secret_access_key"),
        region_name=region,
    ).client("ssm", region_name=region)


def _region_for(server: Server, cred: dict) -> str:
    """Which region this instance is in.

    The account's configured region when it has one. An account left on "all regions" imported
    instances from many, so the region is carried on the asset itself — as the second tag,
    written at import — rather than guessed. Guessing gives `InvalidInstanceId` for an
    instance that exists perfectly well somewhere else.
    """
    for tag in (server.tags or []):
        if tag.startswith("region:"):
            return tag.split(":", 1)[1]
    return (cred.get("region") or "").strip() or "us-east-1"


def _document(server: Server) -> str:
    """Windows and Linux take different SSM documents; sending the wrong one runs nothing."""
    return ("AWS-RunPowerShellScript" if (server.os_type or "").lower().startswith("windows")
            else "AWS-RunShellScript")


# ── The transport ────────────────────────────────────────────────────────────

def is_managed(info: dict, instance_id: str) -> bool:
    """Whether `DescribeInstanceInformation` actually found this instance.

    Fails closed: a malformed or empty answer is "not managed". Reporting an unmanaged
    instance as reachable would let every later probe return nothing and be read as a server
    with no sites, no findings and nothing wrong.
    """
    for item in (info or {}).get("InstanceInformationList") or []:
        if item.get("InstanceId") == instance_id and item.get("PingStatus") == "Online":
            return True
    return False


def read_output(inv: dict) -> tuple[str, str, int]:
    """Turn one `GetCommandInvocation` answer into our (stdout, stderr, exit) contract.

    **Truncation is reported, never swallowed.** AWS gives back the first 24,000 characters
    with no flag saying it did so, so the length is the only signal there is — and a scan cut
    short looks exactly like a scan that found less.
    """
    out = inv.get("StandardOutputContent") or ""
    err = inv.get("StandardErrorContent") or ""
    code = inv.get("ResponseCode")
    if code is None:
        # A command that never ran has no response code. Calling that 0 would report a
        # failure as a success.
        code = 0 if inv.get("Status") == "Success" else 1

    notices = []
    if len(out) >= INLINE_OUTPUT_LIMIT:
        notices.append(TRUNCATED_NOTICE.format(n=INLINE_OUTPUT_LIMIT))
    if len(err) >= INLINE_OUTPUT_LIMIT:
        notices.append(TRUNCATED_NOTICE.format(n=INLINE_OUTPUT_LIMIT))
    if notices:
        # Into stderr, not stdout: appending to stdout would corrupt the sentinel-delimited
        # output our probe bundles parse, turning a reporting problem into a parsing one.
        err = (err + "\n" + "\n".join(notices)).strip()

    return out, err, int(code)


async def test_connection(server: Server, account) -> dict:
    """Is this instance reachable through Systems Manager?

    Shaped like `ssh_service.test_connection` so `connection_manager` can treat it the same.
    There is no host key here — identity is AWS's, not a fingerprint we pin — so that field
    stays empty rather than being invented.
    """
    started = time.monotonic()
    try:
        info = await asyncio.to_thread(
            _describe, server, account)
    except NotManaged as exc:
        return {"ok": False, "latency_ms": _ms(started), "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — a friendly message, never a stack
        return {"ok": False, "latency_ms": _ms(started), "error": _friendly(exc)}

    if not is_managed(info, server.cloud_instance_id or ""):
        return {"ok": False, "latency_ms": _ms(started),
                "error": f"This instance is not registered with AWS Systems Manager. {_FIX}"}
    return {"ok": True, "latency_ms": _ms(started), "error": None}


def _describe(server: Server, account) -> dict:
    client = _client(server, account)
    return client.describe_instance_information(
        Filters=[{"Key": "InstanceIds", "Values": [server.cloud_instance_id or ""]}])


async def execute(server: Server, account, command: str,
                  read_timeout: int = 60) -> tuple[str, str, int]:
    """Run a command on the instance and wait for it.

    `read_timeout` is honoured as a TOTAL budget rather than an idle one: SSM tells us nothing
    until the command finishes, so there is no such thing as "no output for N seconds" here.
    Treating it as idle time would mean never timing out at all.
    """
    return await asyncio.to_thread(_send_and_wait, server, account, command, read_timeout)


def _send_and_wait(server: Server, account, command: str,
                   budget: int) -> tuple[str, str, int]:
    client = _client(server, account)
    instance = server.cloud_instance_id or ""

    try:
        sent = client.send_command(
            InstanceIds=[instance],
            DocumentName=_document(server),
            Parameters={"commands": [command]},
            TimeoutSeconds=max(30, min(budget, 2592000)),
        )
    except Exception as exc:  # noqa: BLE001
        raise SsmError(_friendly(exc))

    command_id = (sent.get("Command") or {}).get("CommandId")
    if not command_id:
        raise SsmError("AWS accepted the command but did not return an id for it, so there "
                       "is nothing to collect the result from.")

    deadline = time.monotonic() + budget
    delay = _POLL_START
    while True:
        try:
            inv = client.get_command_invocation(CommandId=command_id, InstanceId=instance)
        except Exception as exc:  # noqa: BLE001
            # The invocation is not always readable the instant SendCommand returns.
            if "InvocationDoesNotExist" not in str(exc):
                raise SsmError(_friendly(exc))
            inv = {"Status": "Pending"}

        status = inv.get("Status")
        if status in ("Success", "Failed", "Cancelled", "TimedOut"):
            return read_output(inv)

        if time.monotonic() >= deadline:
            raise SsmError(
                f"The command was still running after {budget} seconds, so we stopped "
                f"waiting. It may still be running on the instance — Systems Manager keeps "
                f"the result under command id {command_id}.")
        time.sleep(delay)
        delay = min(delay * 1.6, _POLL_MAX)


async def execute_stream(server: Server, account, command: str) -> AsyncIterator[str]:
    """Run a command and yield its output.

    **There is no live stream over SSM**, so this says so first and then yields the whole
    result at the end. Saying it matters: a progress box that sits empty for four minutes is
    read as a hang, which is the same lesson the apt-lock wait learned when it was silent.
    """
    yield ("[ServerAlly] Running through AWS Systems Manager — output arrives when the "
           "command finishes, because Systems Manager does not stream.\n")
    out, err, code = await execute(server, account, command, read_timeout=600)
    if out:
        yield out if out.endswith("\n") else out + "\n"
    if err:
        yield err if err.endswith("\n") else err + "\n"
    if code != 0:
        yield f"[ServerAlly] The command finished with exit code {code}.\n"


# ── Where the AWS key comes from ─────────────────────────────────────────────

async def account_for(server: Server):
    """The connected cloud account whose key we call AWS with.

    **Unlike every other transport, an SSM server has no credential of its own** — it borrows
    the account's. So disconnecting that account does not merely lose a label, it removes the
    only way to reach the machine, and the FK is `SET NULL` so the link simply vanishes. That
    is worth saying in those words rather than surfacing as a generic failure to connect.
    """
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.cloud_account import CloudAccount

    if not server.cloud_account_id:
        raise SsmError(
            "This asset is managed through AWS Systems Manager, but the AWS account it came "
            "from is no longer connected — and that account's key is how we reach it. "
            "Reconnect the account, or add the machine again over SSH.")
    async with AsyncSessionLocal() as session:
        account = (await session.execute(select(CloudAccount).where(
            CloudAccount.id == server.cloud_account_id))).scalar_one_or_none()
    if account is None:
        raise SsmError(
            "The AWS account this asset was imported from could not be found, so there is no "
            "key to reach it with.")
    return account


# ── Messages worth reading ───────────────────────────────────────────────────

def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _friendly(exc: Exception) -> str:
    """AWS's errors name an API; a customer needs to know what to change.

    The same reasoning as `_aws_msg` in `cloud_service` and `_friendly` in `offsite_service`:
    "AccessDeniedException" tells somebody nothing about which permission to add.
    """
    text = str(exc)
    if "InvalidInstanceId" in text:
        return ("AWS does not recognise that instance in this region — either it has been "
                "terminated, or the account's region does not match where it lives.")
    if "AccessDenied" in text or "UnauthorizedOperation" in text:
        return ("This AWS key is not allowed to run commands through Systems Manager. It "
                "needs ssm:SendCommand, ssm:GetCommandInvocation and "
                "ssm:DescribeInstanceInformation for this instance.")
    if "ExpiredToken" in text or "InvalidClientTokenId" in text:
        return "AWS rejected these credentials. The access key may have been rotated or removed."
    if "ThrottlingException" in text or "TooManyUpdates" in text:
        return "AWS is rate-limiting Systems Manager requests right now. Try again shortly."
    if "EndpointConnectionError" in text or "could not connect" in text.lower():
        return "Could not reach the AWS Systems Manager endpoint for that region."
    return f"AWS Systems Manager error: {text}"
