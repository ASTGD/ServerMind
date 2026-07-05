"""Cloud service — connect a provider account, discover + import its instances (Phase C).

Mirrors ``hosting_service``'s adapter pattern: a ``_CloudAdapter`` base + one subclass per
provider behind a uniform async dispatch. AWS ships first; DigitalOcean / Hetzner / GCP /
Azure are Phase D (each is just another adapter).

Important by design: a cloud API only LISTS instances (id, IP, OS, state) — it never hands
over a login to them. So "import" prefills a ``servers`` row and the user supplies the SSH
key / password separately. The account credential is a provider-shaped JSON blob, stored
AES-256-GCM encrypted (same pattern as ``servers.encrypted_cred``):

    aws → {"access_key_id", "secret_access_key", "region"}   (region blank = all regions)
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, asdict

from app.models.cloud_account import CloudAccount
from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("aws",)  # Phase D adds: digitalocean, hetzner, gcp, azure


class CloudError(Exception):
    """A provider API call failed (bad key, missing permission, unreachable)."""


@dataclass
class Instance:
    instance_id: str
    name: str
    public_ip: str | None
    private_ip: str | None
    os: str            # 'windows' | 'linux'
    state: str         # 'running' | 'stopped' | ...
    region: str | None = None
    instance_type: str | None = None

    def dict(self) -> dict:
        return asdict(self)


# ── Adapters ──────────────────────────────────────────────────────────────────

class _CloudAdapter:
    def __init__(self, cred: dict):
        self.cred = cred

    def verify(self) -> dict:
        raise CloudError("verify not supported")

    def list_instances(self) -> list[Instance]:
        raise CloudError("listing instances is not supported for this provider")


def _aws_msg(exc: Exception) -> str:
    code = ""
    resp = getattr(exc, "response", None)
    if isinstance(resp, dict):
        code = resp.get("Error", {}).get("Code", "")
    if code in ("InvalidClientTokenId", "SignatureDoesNotMatch", "AuthFailure", "UnrecognizedClientException"):
        return "AWS rejected these credentials — check the access key ID and secret."
    if code in ("AccessDenied", "UnauthorizedOperation"):
        return ("This AWS key lacks permission. It needs sts:GetCallerIdentity and "
                "ec2:DescribeInstances — a read-only policy is enough.")
    return f"AWS error: {exc}"


class AWSAdapter(_CloudAdapter):
    """AWS EC2 via boto3. Verify with STS get-caller-identity; list instances in the
    configured region, or across ALL enabled regions when no region is set."""

    def _session(self):
        import boto3  # lazy — the module imports fine even without boto3 installed
        return boto3.session.Session(
            aws_access_key_id=self.cred.get("access_key_id"),
            aws_secret_access_key=self.cred.get("secret_access_key"),
            region_name=self.cred.get("region") or "us-east-1",
        )

    def verify(self) -> dict:
        try:
            ident = self._session().client("sts").get_caller_identity()
        except Exception as exc:  # noqa: BLE001 — surface a friendly message, never a stack
            raise CloudError(_aws_msg(exc))
        return {"account": ident.get("Account"), "arn": ident.get("Arn")}

    def _regions(self, sess) -> list[str]:
        configured = (self.cred.get("region") or "").strip()
        if configured:
            return [configured]
        try:
            data = sess.client("ec2", region_name="us-east-1").describe_regions()
            return [r["RegionName"] for r in data.get("Regions", [])]
        except Exception as exc:  # noqa: BLE001
            raise CloudError(_aws_msg(exc))

    @staticmethod
    def _map(inst: dict, region: str) -> Instance:
        name = ""
        for tag in inst.get("Tags", []) or []:
            if tag.get("Key") == "Name":
                name = tag.get("Value", "")
                break
        is_win = (inst.get("Platform") == "windows") or (inst.get("PlatformDetails", "").lower().startswith("windows"))
        return Instance(
            instance_id=inst.get("InstanceId", ""),
            name=name or inst.get("InstanceId", ""),
            public_ip=inst.get("PublicIpAddress"),
            private_ip=inst.get("PrivateIpAddress"),
            os="windows" if is_win else "linux",
            state=(inst.get("State") or {}).get("Name", "unknown"),
            region=region,
            instance_type=inst.get("InstanceType"),
        )

    def list_instances(self) -> list[Instance]:
        sess = self._session()
        out: list[Instance] = []
        for region in self._regions(sess):
            try:
                ec2 = sess.client("ec2", region_name=region)
                for page in ec2.get_paginator("describe_instances").paginate():
                    for res in page.get("Reservations", []):
                        for inst in res.get("Instances", []):
                            out.append(self._map(inst, region))
            except Exception as exc:  # noqa: BLE001 — one bad region shouldn't kill discovery
                logger.warning("AWS describe_instances failed in %s: %s", region, exc)
        return out


_ADAPTERS = {"aws": AWSAdapter}


# ── Import mapping ────────────────────────────────────────────────────────────

def transport_defaults(os: str) -> dict:
    """How a discovered instance connects, by OS — used to prefill the imported asset."""
    if os == "windows":
        return {"connection_type": "winrm", "port": 5985, "shell": "powershell"}
    return {"connection_type": "ssh", "port": 22, "shell": "bash"}


# ── Dispatch ──────────────────────────────────────────────────────────────────

def _cred_for(account: CloudAccount) -> dict:
    return json.loads(decrypt(account.encrypted_credential))


def _adapter(account: CloudAccount) -> _CloudAdapter:
    cls = _ADAPTERS.get((account.provider or "").lower())
    if cls is None:
        raise CloudError(f"Unsupported cloud provider: {account.provider or '(none)'}")
    return cls(_cred_for(account))


def _adapter_for(provider: str, cred: dict) -> _CloudAdapter:
    cls = _ADAPTERS.get((provider or "").lower())
    if cls is None:
        raise CloudError(f"Unsupported cloud provider: {provider or '(none)'}")
    return cls(cred)


async def _run(fn, *args):
    return await asyncio.to_thread(fn, *args)


async def verify_credential(provider: str, cred: dict) -> dict:
    """Verify a credential at connect time, BEFORE saving the account."""
    return await _run(_adapter_for(provider, cred).verify)


async def list_instances(account: CloudAccount) -> list[Instance]:
    return await _run(_adapter(account).list_instances)
