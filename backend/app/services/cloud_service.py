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
import time
from dataclasses import dataclass, asdict

import requests

from app.models.cloud_account import CloudAccount
from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("aws", "digitalocean", "hetzner", "gcp", "azure")


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
    #: Registered with AWS Systems Manager and answering. Best-effort: a key without
    #: `ssm:DescribeInstanceInformation` leaves this False for everything, which costs the
    #: SSM option rather than the whole import.
    ssm_managed: bool = False

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
        # Both kinds of connection — an access key, or a role we assume in the client's
        # account — resolve in ONE place, so neither caller can end up not knowing about
        # roles. Lazy import: the module loads fine without boto3.
        from app.services import aws_identity
        return aws_identity.session_for(self.cred)

    def verify(self) -> dict:
        from app.services.aws_identity import AwsRoleError

        try:
            ident = self._session().client("sts").get_caller_identity()
        except AwsRoleError as exc:
            # Already a sentence about roles; wrapping it in "AWS rejected these credentials"
            # would replace the accurate diagnosis with a wrong one.
            raise CloudError(str(exc))
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
                found: list[Instance] = []
                for page in ec2.get_paginator("describe_instances").paginate():
                    for res in page.get("Reservations", []):
                        for inst in res.get("Instances", []):
                            found.append(self._map(inst, region))
            except Exception as exc:  # noqa: BLE001 — one bad region shouldn't kill discovery
                logger.warning("AWS describe_instances failed in %s: %s", region, exc)
                continue

            managed = self._ssm_managed(sess, region)
            for inst in found:
                inst.ssm_managed = inst.instance_id in managed
            out.extend(found)
        return out

    @staticmethod
    def _ssm_managed(sess, region: str) -> set[str]:
        """Which instances in this region answer through Systems Manager.

        **Best-effort on purpose.** Most keys have no `ssm:DescribeInstanceInformation`, and
        an import that refused to list anything because of a permission the customer does not
        need yet would be worse than one that simply does not offer the SSM option. So a
        failure here costs the option, never the discovery.
        """
        try:
            ssm = sess.client("ssm", region_name=region)
            ids: set[str] = set()
            for page in ssm.get_paginator("describe_instance_information").paginate():
                for item in page.get("InstanceInformationList", []) or []:
                    if item.get("PingStatus") == "Online" and item.get("InstanceId"):
                        ids.add(item["InstanceId"])
            return ids
        except Exception as exc:  # noqa: BLE001
            logger.info("SSM instance check unavailable in %s: %s", region, exc)
            return set()


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


class GCPAdapter(_CloudAdapter):
    """Google Compute Engine via a service-account key. Mints an OAuth token with the
    JWT-bearer flow (sign a short assertion with the SA private key → exchange for a token —
    no google SDK needed), then lists instances across all zones with aggregatedList."""

    SCOPE = "https://www.googleapis.com/auth/compute.readonly"

    def _sa(self) -> dict:
        raw = self.cred.get("service_account_json", "")
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            raise CloudError("The Google service-account key isn't valid JSON.")

    def _token(self) -> str:
        from jose import jwt as jose_jwt  # already a dependency (RS256 via cryptography)
        sa = self._sa()
        token_uri = sa.get("token_uri") or "https://oauth2.googleapis.com/token"
        if not sa.get("client_email") or not sa.get("private_key"):
            raise CloudError("The Google key is missing client_email or private_key.")
        now = int(time.time())
        try:
            assertion = jose_jwt.encode(
                {"iss": sa["client_email"], "scope": self.SCOPE, "aud": token_uri,
                 "iat": now, "exp": now + 3600},
                sa["private_key"], algorithm="RS256", headers={"kid": sa.get("private_key_id")},
            )
        except Exception as exc:  # noqa: BLE001 — bad/garbled private key
            raise CloudError(f"Could not sign the Google token (check the service-account key): {exc}")
        try:
            r = requests.post(token_uri, data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion}, timeout=20)
        except requests.RequestException as exc:
            raise CloudError(f"Could not reach Google: {exc}")
        if r.status_code >= 400:
            raise CloudError("Google rejected the service-account key — check it's valid and active.")
        return r.json().get("access_token", "")

    def _project(self) -> str:
        return self._sa().get("project_id", "")

    def _get(self, url: str, token: str, params: dict, timeout: int = 30) -> dict:
        try:
            r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=timeout)
        except requests.RequestException as exc:
            raise CloudError(f"Could not reach Google: {exc}")
        if r.status_code in (401, 403):
            raise CloudError("This Google key lacks permission — it needs compute.instances.list "
                             "(the Compute Viewer role) and the Compute Engine API enabled.")
        if r.status_code >= 400:
            raise CloudError(f"Google API error {r.status_code}: {r.text[:200]}")
        return r.json()

    def verify(self) -> dict:
        token, project = self._token(), self._project()
        if not project:
            raise CloudError("The Google service-account key has no project_id.")
        self._get(f"https://compute.googleapis.com/compute/v1/projects/{project}/aggregated/instances",
                  token, {"maxResults": 1})
        return {"project": project}

    @staticmethod
    def _map(inst: dict, zone: str) -> Instance:
        nics = inst.get("networkInterfaces") or []
        private = nics[0].get("networkIP") if nics else None
        public = None
        if nics:
            for ac in nics[0].get("accessConfigs") or []:
                if ac.get("natIP"):
                    public = ac["natIP"]
                    break
        is_win = any("windows" in (lic or "").lower()
                     for d in (inst.get("disks") or []) for lic in (d.get("licenses") or []))
        mt = inst.get("machineType", "") or ""
        return Instance(
            instance_id=str(inst.get("id", "")),
            name=inst.get("name") or str(inst.get("id", "")),
            public_ip=public,
            private_ip=private,
            os="windows" if is_win else "linux",
            state=(inst.get("status") or "unknown").lower(),   # RUNNING → running
            region=zone,
            instance_type=mt.split("/")[-1] if mt else None,
        )

    def list_instances(self) -> list[Instance]:
        token, project = self._token(), self._project()
        url = f"https://compute.googleapis.com/compute/v1/projects/{project}/aggregated/instances"
        out: list[Instance] = []
        page = None
        while True:
            params = {"maxResults": 500}
            if page:
                params["pageToken"] = page
            data = self._get(url, token, params)
            for zone_key, block in (data.get("items") or {}).items():
                zone = zone_key.split("/")[-1]                 # "zones/us-central1-a" → "us-central1-a"
                for inst in block.get("instances") or []:
                    out.append(self._map(inst, zone))
            page = data.get("nextPageToken")
            if not page:
                return out


class AzureAdapter(_CloudAdapter):
    """Azure VMs via a service principal (client-credentials OAuth), listed in one Resource
    Graph query that joins VMs to their network interfaces + public IPs."""

    _GRAPH = (
        "Resources | where type =~ 'microsoft.compute/virtualmachines' "
        "| extend nicId = tostring(properties.networkProfile.networkInterfaces[0].id) "
        "| join kind=leftouter (Resources | where type =~ 'microsoft.network/networkinterfaces' "
        "| extend ipc = properties.ipConfigurations[0] "
        "| project nicId = id, privateIp = tostring(ipc.properties.privateIPAddress), "
        "pipId = tostring(ipc.properties.publicIPAddress.id)) on nicId "
        "| join kind=leftouter (Resources | where type =~ 'microsoft.network/publicipaddresses' "
        "| project pipId = id, publicIp = tostring(properties.ipAddress)) on pipId "
        "| project name, location, vmId = id, "
        "os = tostring(properties.storageProfile.osDisk.osType), "
        "state = tostring(properties.extended.instanceView.powerState.code), privateIp, publicIp"
    )

    def _token(self) -> str:
        tenant = self.cred.get("tenant_id", "")
        try:
            r = requests.post(
                f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
                data={"grant_type": "client_credentials",
                      "client_id": self.cred.get("client_id", ""),
                      "client_secret": self.cred.get("client_secret", ""),
                      "scope": "https://management.azure.com/.default"}, timeout=20)
        except requests.RequestException as exc:
            raise CloudError(f"Could not reach Azure: {exc}")
        if r.status_code >= 400:
            raise CloudError("Azure rejected these credentials — check the tenant ID, client ID and secret.")
        return r.json().get("access_token", "")

    def verify(self) -> dict:
        token = self._token()
        sub = self.cred.get("subscription_id", "")
        try:
            r = requests.get(f"https://management.azure.com/subscriptions/{sub}",
                             headers={"Authorization": f"Bearer {token}"},
                             params={"api-version": "2020-01-01"}, timeout=20)
        except requests.RequestException as exc:
            raise CloudError(f"Could not reach Azure: {exc}")
        if r.status_code in (401, 403):
            raise CloudError("This Azure service principal can't access the subscription — "
                             "grant it the Reader role on the subscription.")
        if r.status_code >= 400:
            raise CloudError(f"Azure API error {r.status_code}: {r.text[:200]}")
        return {"subscription": sub}

    @staticmethod
    def _map(row: dict) -> Instance:
        state = (row.get("state") or "").split("/")[-1] or "unknown"   # PowerState/running → running
        os = (row.get("os") or "").lower()
        return Instance(
            instance_id=row.get("vmId") or row.get("name") or "",
            name=row.get("name") or "",
            public_ip=row.get("publicIp") or None,
            private_ip=row.get("privateIp") or None,
            os="windows" if os == "windows" else "linux",
            state=state.lower(),
            region=row.get("location"),
            instance_type=None,
        )

    def list_instances(self) -> list[Instance]:
        token = self._token()
        sub = self.cred.get("subscription_id", "")
        out: list[Instance] = []
        skip = None
        while True:
            body: dict = {"subscriptions": [sub], "query": self._GRAPH,
                          "options": {"resultFormat": "objectArray"}}
            if skip:
                body["options"]["$skipToken"] = skip
            try:
                r = requests.post(
                    "https://management.azure.com/providers/Microsoft.ResourceGraph/resources",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"api-version": "2022-10-01"}, json=body, timeout=30)
            except requests.RequestException as exc:
                raise CloudError(f"Could not reach Azure: {exc}")
            if r.status_code >= 400:
                raise CloudError(f"Azure API error {r.status_code}: {r.text[:200]}")
            data = r.json()
            for row in (data.get("data") or []):
                out.append(self._map(row))
            skip = data.get("$skipToken")
            if not skip:
                return out


_ADAPTERS = {
    "aws": AWSAdapter,
    "digitalocean": DigitalOceanAdapter,
    "hetzner": HetznerAdapter,
    "gcp": GCPAdapter,
    "azure": AzureAdapter,
}


# ── Import mapping ────────────────────────────────────────────────────────────

def transport_defaults(os: str) -> dict:
    """How a discovered instance connects, by OS — used to prefill the imported asset."""
    if os == "windows":
        return {"connection_type": "winrm", "port": 5985, "shell": "powershell"}
    return {"connection_type": "ssh", "port": 22, "shell": "bash"}


def transport_for(inst: Instance, *, host: str | None, prefer_ssm: bool = False) -> dict | None:
    """How this particular instance should be reached, or None if it cannot be.

    **Systems Manager is the fallback, not the default**, and that is a deliberate call rather
    than caution. SSM has no file transfer and no interactive terminal yet, so choosing it for
    a machine that has a perfectly good address would quietly hand the customer a server with
    no File Manager, no `.env` editor, no certificate install and no terminal — a downgrade
    they never asked for and would have no way to explain. So: an address wins, unless the
    customer says otherwise.

    What it DOES unlock is the case SSH cannot do at all. An instance with no public and no
    private address we can reach used to be skipped outright ("no reachable IP"); if it is
    registered with Systems Manager it is now importable, because the agent dials out.
    """
    if not host:
        return dict(SSM_TRANSPORT) if inst.ssm_managed else None
    if prefer_ssm and inst.ssm_managed:
        return dict(SSM_TRANSPORT)
    return transport_defaults(inst.os)


#: An SSM asset has no address, no port and no login of its own — the shape says so rather
#: than filling those in with numbers that mean nothing.
SSM_TRANSPORT = {"connection_type": "ssm", "port": 0, "shell": "bash"}


def credential_needed(transports: list[dict]) -> bool:
    """Whether this import has to ask for a username and key at all.

    A batch that is entirely Systems Manager needs no credential, and asking for one anyway
    would be asking for the exact artefact SSM exists to remove.
    """
    return any(t.get("connection_type") != "ssm" for t in transports)


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
