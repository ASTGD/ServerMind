"""Importing an instance that is managed through Systems Manager.

Phase 4 built the transport and left it unreachable — nothing created an `ssm` asset. This is
the door, and the interesting decisions are all about NOT taking something away from the
customer while adding it.
"""
import inspect

import pytest

from app.services import cloud_service as cs


def inst(**over) -> cs.Instance:
    base = dict(instance_id="i-1", name="web", public_ip="203.0.113.9", private_ip="10.0.0.9",
                os="linux", state="running", region="eu-west-2")
    base.update(over)
    return cs.Instance(**base)


# ── which way in ─────────────────────────────────────────────────────────────

def test_an_address_beats_systems_manager():
    """SSM is the fallback, not the default, and this is the whole reason.

    SSM has no file transfer and no terminal yet, so choosing it for a machine that has a
    perfectly good address would hand the customer a server with no File Manager, no `.env`
    editor, no certificate install and no terminal — a downgrade they never asked for and
    could not explain.
    """
    t = cs.transport_for(inst(ssm_managed=True), host="203.0.113.9")
    assert t["connection_type"] == "ssh"
    assert t["port"] == 22


def test_the_customer_can_ask_for_systems_manager_anyway():
    """Key custody is the thing an agency actually wants rid of, so the choice is theirs."""
    t = cs.transport_for(inst(ssm_managed=True), host="203.0.113.9", prefer_ssm=True)
    assert t["connection_type"] == "ssm"


def test_preferring_ssm_cannot_conjure_it_for_an_unmanaged_instance():
    """An instance without the agent is not reachable that way, however the box is ticked —
    and silently filing it as `ssm` would produce an asset that can never answer."""
    t = cs.transport_for(inst(ssm_managed=False), host="203.0.113.9", prefer_ssm=True)
    assert t["connection_type"] == "ssh"


def test_an_instance_with_no_address_becomes_importable_when_it_is_managed():
    """The headline: this is the case SSH cannot do at all.

    An instance with no public and no reachable private address used to be counted as "no
    reachable IP" and dropped. If the agent dials out, there is nothing to reach.
    """
    assert cs.transport_for(inst(public_ip=None, private_ip=None), host=None) is None
    t = cs.transport_for(inst(public_ip=None, private_ip=None, ssm_managed=True), host=None)
    assert t["connection_type"] == "ssm"


def test_an_ssm_asset_has_no_port():
    """There is no port. Writing 22 there would be a number that means nothing and would
    read, on the asset page, as something a firewall could be blocking."""
    assert cs.SSM_TRANSPORT["port"] == 0


def test_windows_still_gets_winrm():
    t = cs.transport_for(inst(os="windows"), host="203.0.113.9")
    assert t["connection_type"] == "winrm"


# ── what the customer is asked for ───────────────────────────────────────────

def test_an_all_ssm_batch_asks_for_no_credential():
    """Asking anyway would be asking for the exact artefact SSM exists to remove."""
    assert cs.credential_needed([cs.SSM_TRANSPORT, cs.SSM_TRANSPORT]) is False


def test_one_ssh_instance_makes_the_credential_required_again():
    """A mixed batch still needs the key for the half that uses it — and a batch that
    silently imported those without one would produce assets that can never connect."""
    assert cs.credential_needed([cs.SSM_TRANSPORT, cs.transport_defaults("linux")]) is True
    assert cs.credential_needed([cs.transport_defaults("windows")]) is True


def test_the_endpoint_refuses_a_batch_that_needs_a_key_and_has_none():
    """Checked against what the instances RESOLVE to, not against a checkbox — the schema
    cannot know that this particular selection happens to be all-SSM."""
    from app.routers import cloud_accounts

    source = inspect.getsource(cloud_accounts.import_instances)
    assert "credential_needed" in source
    assert "422" in source or "UNPROCESSABLE" in source


# ── what gets written ────────────────────────────────────────────────────────

def test_the_import_records_the_region_on_the_asset():
    """`ssm_service` reads `region:<x>` off the asset's tags, and an account left on "all
    regions" imports from several — without this AWS answers `InvalidInstanceId` for an
    instance that exists perfectly well somewhere else. The two halves have to agree."""
    from app.routers import cloud_accounts
    from app.services import ssm_service

    written = inspect.getsource(cloud_accounts.import_instances)
    assert 'f"region:{inst.region}"' in written, "the import never records the region"

    read = inspect.getsource(ssm_service._region_for)                 # noqa: SLF001
    assert '"region:"' in read, "ssm_service stopped reading it"


def test_an_ssm_asset_stores_no_secret_of_its_own():
    """It borrows the account's AWS key. Storing the batch SSH password on a row that can
    never use it would be a secret kept for no reason — and a secret kept for no reason is
    one more thing that can leak."""
    from app.routers import cloud_accounts

    source = inspect.getsource(cloud_accounts.import_instances)
    assert 'encrypt("") if is_ssm else encrypted' in source


def test_an_ssm_asset_still_shows_something_recognisable_as_a_host():
    """There is no address to connect to, but a row reading as blank is a row nobody can
    identify. The private IP when there is one, else what AWS itself calls it."""
    from app.routers import cloud_accounts

    source = inspect.getsource(cloud_accounts.import_instances)
    assert "inst.private_ip or inst.instance_id" in source


# ── discovery ────────────────────────────────────────────────────────────────

def test_the_ssm_check_is_best_effort():
    """Most keys have no `ssm:DescribeInstanceInformation`. An import that listed nothing
    because of a permission the customer does not need yet would be worse than one that
    simply does not offer the option."""
    class _Sess:
        def client(self, *_a, **_k):
            raise RuntimeError("AccessDeniedException")

    assert cs.AWSAdapter._ssm_managed(_Sess(), "eu-west-2") == set()   # noqa: SLF001


def test_only_an_instance_that_is_actually_answering_counts_as_managed():
    """A registered agent that has stopped replying is not a way in. Counting it would file
    the asset as reachable and let every later probe return nothing."""
    class _Paginator:
        def paginate(self):
            return [{"InstanceInformationList": [
                {"InstanceId": "i-online", "PingStatus": "Online"},
                {"InstanceId": "i-lost", "PingStatus": "ConnectionLost"},
                {"PingStatus": "Online"},                       # no id at all
            ]}]

    class _Client:
        def get_paginator(self, _name):
            return _Paginator()

    class _Sess:
        def client(self, *_a, **_k):
            return _Client()

    assert cs.AWSAdapter._ssm_managed(_Sess(), "eu-west-2") == {"i-online"}   # noqa: SLF001


def test_a_provider_without_ssm_never_claims_it():
    """DigitalOcean and Hetzner have no Systems Manager. The field defaults False so their
    instances can never be filed as reachable a way that does not exist for them."""
    assert cs.Instance(instance_id="i", name="n", public_ip=None, private_ip=None,
                       os="linux", state="running").ssm_managed is False


@pytest.mark.parametrize("adapter", ["DigitalOceanAdapter", "HetznerAdapter"])
def test_no_other_adapter_sets_the_managed_flag(adapter):
    cls = getattr(cs, adapter, None)
    if cls is None:
        pytest.skip(f"{adapter} is not in this build")
    assert "ssm_managed" not in inspect.getsource(cls)
