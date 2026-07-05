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

import requests

from app.models.cloud_account import CloudAccount
from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("aws", "digitalocean", "hetzner")  # Phase D+; gcp/azure later


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


class _TokenAdapter(_CloudAdapter):
    """Shared base for the simple bearer-token REST clouds (DigitalOcean, Hetzner). Both
    are global APIs — one token, no region dance — so listing returns every instance."""

    BASE = ""
    PROVIDER = ""

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.cred.get('api_token', '')}",
                "Content-Type": "application/json"}

    def _get(self, url: str, timeout: int = 20) -> dict:
        try:
            r = requests.get(url, headers=self._headers(), timeout=timeout)
        except requests.RequestException as exc:  # network / DNS / TLS
            raise CloudError(f"Could not reach {self.PROVIDER}: {exc}")
        if r.status_code in (401, 403):
            raise CloudError(f"{self.PROVIDER} rejected this API token — check it has read access.")
        if r.status_code >= 400:
            raise CloudError(f"{self.PROVIDER} API error {r.status_code}: {r.text[:200]}")
        try:
            return r.json()
        except ValueError:
            raise CloudError(f"{self.PROVIDER} returned an unexpected (non-JSON) response.")


class DigitalOceanAdapter(_TokenAdapter):
    """DigitalOcean droplets. Verify with /v2/account; list /v2/droplets (paginated)."""

    BASE = "https://api.digitalocean.com"
    PROVIDER = "DigitalOcean"

    def verify(self) -> dict:
        acct = self._get(f"{self.BASE}/v2/account").get("account", {})
        return {"account": acct.get("email"), "uuid": acct.get("uuid")}

    @staticmethod
    def _map(d: dict) -> Instance:
        nets = (d.get("networks") or {}).get("v4") or []
        public = next((n.get("ip_address") for n in nets if n.get("type") == "public"), None)
        private = next((n.get("ip_address") for n in nets if n.get("type") == "private"), None)
        distro = ((d.get("image") or {}).get("distribution") or "")
        return Instance(
            instance_id=str(d.get("id", "")),
            name=d.get("name") or str(d.get("id", "")),
            public_ip=public,
            private_ip=private,
            os="windows" if "windows" in distro.lower() else "linux",
            state=d.get("status", "unknown"),          # active | off | new
            region=(d.get("region") or {}).get("slug"),
            instance_type=d.get("size_slug"),
        )

    def list_instances(self) -> list[Instance]:
        out: list[Instance] = []
        url = f"{self.BASE}/v2/droplets?per_page=200"
        while url:
            data = self._get(url, timeout=30)
            for d in data.get("droplets", []):
                out.append(self._map(d))
            url = ((data.get("links") or {}).get("pages") or {}).get("next")  # cursor
        return out


class HetznerAdapter(_TokenAdapter):
    """Hetzner Cloud servers. Verify + list via /v1/servers (paginated)."""

    BASE = "https://api.hetzner.cloud"
    PROVIDER = "Hetzner"

    def verify(self) -> dict:
        # Any authenticated call proves the token; keep it tiny.
        self._get(f"{self.BASE}/v1/servers?per_page=1")
        return {"account": "hetzner-project"}

    @staticmethod
    def _map(s: dict) -> Instance:
        public = ((s.get("public_net") or {}).get("ipv4") or {}).get("ip")
        privs = s.get("private_net") or []
        private = privs[0].get("ip") if privs else None
        flavor = ((s.get("image") or {}).get("os_flavor") or "")
        return Instance(
            instance_id=str(s.get("id", "")),
            name=s.get("name") or str(s.get("id", "")),
            public_ip=public,
            private_ip=private,
            os="windows" if "windows" in flavor.lower() else "linux",
            state=s.get("status", "unknown"),          # running | off | ...
            region=((s.get("datacenter") or {}).get("location") or {}).get("name"),
            instance_type=(s.get("server_type") or {}).get("name"),
        )

    def list_instances(self) -> list[Instance]:
        out: list[Instance] = []
        page = 1
        while page:
            data = self._get(f"{self.BASE}/v1/servers?per_page=50&page={page}", timeout=30)
            for s in data.get("servers", []):
                out.append(self._map(s))
            page = (((data.get("meta") or {}).get("pagination") or {}).get("next_page"))
        return out


_ADAPTERS = {
    "aws": AWSAdapter,
    "digitalocean": DigitalOceanAdapter,
    "hetzner": HetznerAdapter,
}


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
