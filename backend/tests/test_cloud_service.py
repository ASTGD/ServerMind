"""Phase C — the AWS cloud adapter. No live AWS account at build time, so lock the verify /
region-discovery / instance-mapping / error / dispatch paths against a fake boto3 session
(same discipline as the hosting adapters). boto3 itself is never called."""
import json
from unittest.mock import patch

import pytest

from app.models.cloud_account import CloudAccount
from app.services import cloud_service as cs
from app.services.cloud_service import AWSAdapter, CloudError, Instance
from app.services.crypto_service import encrypt


# ── Fakes standing in for a boto3 session ──────────────────────────────────────

class FakeClientError(Exception):
    """Mimics botocore.exceptions.ClientError enough for _aws_msg (has .response)."""
    def __init__(self, code: str):
        self.response = {"Error": {"Code": code}}
        super().__init__(code)


class FakeEc2:
    def __init__(self, pages=None, regions=None, raise_exc=None):
        self._pages = pages or []
        self._regions = regions or []
        self._raise = raise_exc

    def describe_regions(self):
        return {"Regions": [{"RegionName": r} for r in self._regions]}

    def get_paginator(self, name):
        assert name == "describe_instances"
        return self

    def paginate(self):
        if self._raise:
            raise self._raise
        return iter(self._pages)


class FakeSts:
    def __init__(self, ident=None, raise_exc=None):
        self._ident = ident or {}
        self._raise = raise_exc

    def get_caller_identity(self):
        if self._raise:
            raise self._raise
        return self._ident


class FakeSession:
    def __init__(self, sts=None, ec2_by_region=None):
        self._sts = sts
        self._ec2 = ec2_by_region or {}

    def client(self, service, region_name=None):
        if service == "sts":
            return self._sts
        if service == "ec2":
            return self._ec2.get(region_name, FakeEc2())
        raise AssertionError(f"unexpected client {service}")


def _reservation(*instances):
    return {"Reservations": [{"Instances": list(instances)}]}


LINUX = {
    "InstanceId": "i-linux1",
    "Tags": [{"Key": "Name", "Value": "web-prod"}],
    "PublicIpAddress": "1.2.3.4",
    "PrivateIpAddress": "10.0.0.5",
    "State": {"Name": "running"},
    "InstanceType": "t3.micro",
}
WINDOWS = {
    "InstanceId": "i-win1",
    "Platform": "windows",
    "PrivateIpAddress": "10.0.0.9",
    "State": {"Name": "stopped"},
    "InstanceType": "t3.small",
}


# ── verify ─────────────────────────────────────────────────────────────────────

def test_verify_success():
    sess = FakeSession(sts=FakeSts(ident={"Account": "123456789012", "Arn": "arn:aws:iam::x:user/bot"}))
    with patch.object(AWSAdapter, "_session", return_value=sess):
        out = AWSAdapter({"access_key_id": "AKIA", "secret_access_key": "s"}).verify()
    assert out == {"account": "123456789012", "arn": "arn:aws:iam::x:user/bot"}


def test_verify_bad_credentials_maps_to_friendly_error():
    sess = FakeSession(sts=FakeSts(raise_exc=FakeClientError("InvalidClientTokenId")))
    with patch.object(AWSAdapter, "_session", return_value=sess):
        with pytest.raises(CloudError, match="rejected these credentials"):
            AWSAdapter({}).verify()


def test_verify_permission_denied_names_the_policy():
    sess = FakeSession(sts=FakeSts(raise_exc=FakeClientError("AccessDenied")))
    with patch.object(AWSAdapter, "_session", return_value=sess):
        with pytest.raises(CloudError, match="ec2:DescribeInstances"):
            AWSAdapter({}).verify()


# ── list_instances ─────────────────────────────────────────────────────────────

def test_list_instances_single_region_maps_fields():
    ec2 = FakeEc2(pages=[_reservation(LINUX, WINDOWS)])
    sess = FakeSession(ec2_by_region={"us-east-1": ec2})
    with patch.object(AWSAdapter, "_session", return_value=sess):
        out = AWSAdapter({"region": "us-east-1"}).list_instances()

    assert [i.instance_id for i in out] == ["i-linux1", "i-win1"]
    lin, win = out
    assert lin.name == "web-prod" and lin.os == "linux"
    assert lin.public_ip == "1.2.3.4" and lin.private_ip == "10.0.0.5"
    assert lin.state == "running" and lin.region == "us-east-1" and lin.instance_type == "t3.micro"
    # windows: no Name tag → falls back to the instance id; no public IP
    assert win.name == "i-win1" and win.os == "windows"
    assert win.public_ip is None and win.state == "stopped"


def test_list_instances_all_regions_when_none_configured():
    # region blank → describe_regions (on us-east-1), then per-region describe_instances
    east = FakeEc2(pages=[_reservation(LINUX)], regions=["us-east-1", "eu-west-1"])
    west = FakeEc2(pages=[_reservation(WINDOWS)])
    sess = FakeSession(ec2_by_region={"us-east-1": east, "eu-west-1": west})
    with patch.object(AWSAdapter, "_session", return_value=sess):
        out = AWSAdapter({}).list_instances()

    by_id = {i.instance_id: i for i in out}
    assert set(by_id) == {"i-linux1", "i-win1"}
    assert by_id["i-linux1"].region == "us-east-1"
    assert by_id["i-win1"].region == "eu-west-1"


def test_one_bad_region_does_not_kill_discovery():
    east = FakeEc2(pages=[_reservation(LINUX)], regions=["us-east-1", "eu-west-1"])
    west = FakeEc2(raise_exc=RuntimeError("throttled"))
    sess = FakeSession(ec2_by_region={"us-east-1": east, "eu-west-1": west})
    with patch.object(AWSAdapter, "_session", return_value=sess):
        out = AWSAdapter({}).list_instances()
    assert [i.instance_id for i in out] == ["i-linux1"]  # west failed, east survived


def test_platform_details_windows_detection():
    inst = {"InstanceId": "i-x", "PlatformDetails": "Windows BYOL", "State": {"Name": "running"}}
    assert AWSAdapter._map(inst, "us-east-1").os == "windows"


# ── dispatch / mapping helpers ─────────────────────────────────────────────────

def test_transport_defaults():
    assert cs.transport_defaults("windows") == {"connection_type": "winrm", "port": 5985, "shell": "powershell"}
    assert cs.transport_defaults("linux") == {"connection_type": "ssh", "port": 22, "shell": "bash"}


def test_unsupported_provider_rejected():
    with pytest.raises(CloudError, match="Unsupported cloud provider"):
        cs._adapter_for("gcp", {})


def test_instance_dict_roundtrip():
    inst = Instance("i-1", "n", "1.1.1.1", None, "linux", "running", region="us-east-1")
    d = inst.dict()
    assert d["instance_id"] == "i-1" and d["public_ip"] == "1.1.1.1" and d["private_ip"] is None


async def test_verify_credential_async_dispatch():
    sess = FakeSession(sts=FakeSts(ident={"Account": "1", "Arn": "a"}))
    with patch.object(AWSAdapter, "_session", return_value=sess):
        out = await cs.verify_credential("aws", {"access_key_id": "AKIA"})
    assert out["account"] == "1"


async def test_list_instances_async_reads_account_credential():
    cred = {"access_key_id": "AKIA", "secret_access_key": "s", "region": "us-east-1"}
    account = CloudAccount(provider="aws", label="prod", encrypted_credential=encrypt(json.dumps(cred)))
    ec2 = FakeEc2(pages=[_reservation(LINUX)])
    sess = FakeSession(ec2_by_region={"us-east-1": ec2})
    with patch.object(AWSAdapter, "_session", return_value=sess):
        out = await cs.list_instances(account)
    assert [i.instance_id for i in out] == ["i-linux1"]


# ── Phase D: DigitalOcean + Hetzner (bearer-token REST, mock requests.get) ──────

from app.services.cloud_service import DigitalOceanAdapter, HetznerAdapter  # noqa: E402


class FakeResp:
    def __init__(self, payload=None, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_providers_registered():
    assert set(cs.SUPPORTED_PROVIDERS) == {"aws", "digitalocean", "hetzner"}
    assert cs._ADAPTERS["digitalocean"] is DigitalOceanAdapter
    assert cs._ADAPTERS["hetzner"] is HetznerAdapter


def test_do_verify_and_bad_token():
    with patch("app.services.cloud_service.requests.get",
               return_value=FakeResp({"account": {"email": "me@x.com", "uuid": "u1"}})):
        assert DigitalOceanAdapter({"api_token": "t"}).verify()["account"] == "me@x.com"
    with patch("app.services.cloud_service.requests.get", return_value=FakeResp(status=401, text="unauth")):
        with pytest.raises(CloudError, match="rejected this API token"):
            DigitalOceanAdapter({"api_token": "bad"}).verify()


def test_do_list_maps_and_paginates():
    page1 = {
        "droplets": [{
            "id": 111, "name": "web1", "status": "active", "size_slug": "s-1vcpu-1gb",
            "region": {"slug": "nyc3"},
            "image": {"distribution": "Ubuntu"},
            "networks": {"v4": [
                {"ip_address": "1.2.3.4", "type": "public"},
                {"ip_address": "10.0.0.2", "type": "private"},
            ]},
        }],
        "links": {"pages": {"next": "https://api.digitalocean.com/v2/droplets?page=2"}},
    }
    page2 = {"droplets": [{"id": 222, "name": "win1", "status": "off",
                           "image": {"distribution": "Windows"}, "networks": {"v4": []}}],
             "links": {}}
    with patch("app.services.cloud_service.requests.get", side_effect=[FakeResp(page1), FakeResp(page2)]):
        out = DigitalOceanAdapter({"api_token": "t"}).list_instances()
    assert [i.instance_id for i in out] == ["111", "222"]
    web, win = out
    assert web.name == "web1" and web.os == "linux" and web.public_ip == "1.2.3.4"
    assert web.private_ip == "10.0.0.2" and web.region == "nyc3" and web.state == "active"
    assert win.os == "windows" and win.public_ip is None and win.state == "off"


def test_hetzner_verify_and_list_maps():
    with patch("app.services.cloud_service.requests.get", return_value=FakeResp({"servers": []})):
        assert HetznerAdapter({"api_token": "t"}).verify()["account"] == "hetzner-project"
    page = {
        "servers": [{
            "id": 99, "name": "hz1", "status": "running",
            "public_net": {"ipv4": {"ip": "5.6.7.8"}},
            "private_net": [{"ip": "10.1.0.3"}],
            "image": {"os_flavor": "ubuntu"},
            "datacenter": {"location": {"name": "fsn1"}},
            "server_type": {"name": "cx22"},
        }],
        "meta": {"pagination": {"next_page": None}},
    }
    with patch("app.services.cloud_service.requests.get", return_value=FakeResp(page)):
        out = HetznerAdapter({"api_token": "t"}).list_instances()
    assert len(out) == 1
    hz = out[0]
    assert hz.instance_id == "99" and hz.public_ip == "5.6.7.8" and hz.private_ip == "10.1.0.3"
    assert hz.os == "linux" and hz.region == "fsn1" and hz.instance_type == "cx22" and hz.state == "running"


def test_token_adapter_network_error_is_cloud_error():
    import requests as _rq
    with patch("app.services.cloud_service.requests.get", side_effect=_rq.ConnectionError("boom")):
        with pytest.raises(CloudError, match="Could not reach"):
            HetznerAdapter({"api_token": "t"}).verify()


async def test_do_async_dispatch_reads_account():
    cred = {"api_token": "tok"}
    account = CloudAccount(provider="digitalocean", label="do", encrypted_credential=encrypt(json.dumps(cred)))
    payload = {"droplets": [{"id": 7, "name": "d7", "status": "active",
                             "image": {"distribution": "Debian"},
                             "networks": {"v4": [{"ip_address": "9.9.9.9", "type": "public"}]}}],
               "links": {}}
    with patch("app.services.cloud_service.requests.get", return_value=FakeResp(payload)):
        out = await cs.list_instances(account)
    assert out[0].instance_id == "7" and out[0].public_ip == "9.9.9.9"
