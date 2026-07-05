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
