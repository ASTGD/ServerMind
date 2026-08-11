"""Connecting a client's AWS account without holding a credential in it.

This is the piece that makes ServerAlly sellable to an agency: an AWS partner is not given an
IAM user in a client's account, they are given a role with an external ID. The security of the
whole arrangement rests on that external ID, and on it being ours.
"""
import inspect
import json
import time

import pytest

from app.services import aws_identity as ai


# ── the confused-deputy guard ────────────────────────────────────────────────

def test_the_external_id_is_never_taken_from_the_request():
    """The hole this closes: a role that trusts our AWS account is assumable by ANYONE who
    can name its ARN, because AWS only checks that the caller is us. If the connecting
    customer could choose the external ID too, they could choose another customer's — and
    reach a client account that is not theirs.

    So whatever arrives in the request is thrown away rather than merged.
    """
    from app.routers import cloud_accounts

    source = inspect.getsource(cloud_accounts.connect_account)
    assert 'cred.pop("external_id", None)' in source, "a supplied value must be discarded"
    assert 'cred["external_id"] = aws_identity.external_id_for' in source
    # Merging would be the subtle version of the same bug: `{**body, **ours}` looks safe and
    # leaves the customer's value in place for any key we do not overwrite.
    assert "**body.credential" not in source


def test_one_customer_cannot_satisfy_another_customers_trust_policy():
    """The property the whole thing rests on."""
    assert ai.external_id_for("user-a") != ai.external_id_for("user-b")


def test_it_is_stable_for_one_customer():
    """It is handed over BEFORE the role exists and used after. A value that changed in
    between would leave the customer with a trust policy that can never match — after they
    have already been through their client's IAM approval."""
    assert ai.external_id_for("user-a") == ai.external_id_for("user-a")


def test_it_is_not_guessable_from_the_account_id():
    """It is an HMAC under the deployment secret, so knowing who somebody is tells you
    nothing about their value."""
    value = ai.external_id_for("user-a")
    assert "user-a" not in value
    assert len(value) > 24


def test_it_changes_with_the_deployment_secret(monkeypatch):
    """Proves the secret is actually in the derivation rather than decorative."""
    before = ai.external_id_for("user-a")
    monkeypatch.setattr(ai.settings, "SECRET_KEY", "a-different-secret")
    assert ai.external_id_for("user-a") != before


def test_a_role_is_never_assumed_without_one(monkeypatch):
    """Sending an empty ExternalId is exactly the hole, so it is refused before the call.

    Has to get past the "have we an identity at all" check to reach it — that one comes
    first, correctly, because it is the more fundamental problem.
    """
    monkeypatch.setattr(ai, "base_configured", lambda: True)
    monkeypatch.setattr(ai, "_base_session", lambda _r: pytest.fail(
        "STS must not be called at all without an external ID"))
    with pytest.raises(ai.AwsRoleError) as exc:
        ai.assume("arn:aws:iam::111122223333:role/ServerAlly", "")
    assert "external ID" in str(exc.value)


# ── what we keep, and what we never keep ─────────────────────────────────────

def test_only_the_arn_and_the_external_id_are_stored():
    """Assumed credentials are short-lived and belong in memory. A row containing them would
    be a secret with no expiry, in a database, for an account that is not even ours."""
    from app.routers import cloud_accounts

    source = inspect.getsource(cloud_accounts.connect_account)
    assert "encrypt(json.dumps(cred))" in source
    for never in ("AccessKeyId", "SessionToken", "assume("):
        assert never not in source, f"{never} must not be anywhere near what gets stored"


def test_assumed_credentials_are_cached_in_memory_only():
    """Twenty commands in a mission should not mean twenty extra STS calls — but the cache
    must be a module dict, not anything that outlives the process."""
    source = inspect.getsource(ai)
    assert "_assumed: dict" in source
    for persisted in ("session.add", "open(", "encrypt(", "redis"):
        assert persisted not in source, f"credentials must not reach {persisted}"


def test_a_cached_credential_is_dropped_before_it_expires(monkeypatch):
    """Using one that expires mid-command turns a working deploy into an AccessDenied
    halfway through."""
    calls = {"n": 0}

    class _STS:
        def assume_role(self, **_):
            calls["n"] += 1
            return {"Credentials": {"AccessKeyId": "A", "SecretAccessKey": "S",
                                    "SessionToken": "T"}}

    class _Sess:
        def client(self, *_a, **_k):
            return _STS()

    monkeypatch.setattr(ai, "_base_session", lambda _r: _Sess())
    monkeypatch.setattr(ai, "base_configured", lambda: True)
    ai._assumed.clear()                                          # noqa: SLF001

    ai.assume("arn:role/x", "ext-1")
    ai.assume("arn:role/x", "ext-1")
    assert calls["n"] == 1, "the second call should have come from the cache"

    # Expiring inside the margin must NOT be reused.
    ai._assumed["arn:role/x|ext-1"] = ({"AccessKeyId": "old"},    # noqa: SLF001
                                       time.time() + ai._EXPIRY_MARGIN - 1)
    ai.assume("arn:role/x", "ext-1")
    assert calls["n"] == 2
    ai._assumed.clear()                                          # noqa: SLF001


def test_a_removed_connection_can_have_its_credentials_forgotten():
    ai._assumed["arn:role/y|ext"] = ({"AccessKeyId": "A"}, time.time() + 9999)  # noqa: SLF001
    ai.forget("arn:role/y", "ext")
    assert "arn:role/y|ext" not in ai._assumed                   # noqa: SLF001


# ── what the customer is handed ──────────────────────────────────────────────

def test_the_trust_policy_is_produced_rather_than_described():
    """One typed from a description is one with a typo in it, and a typo'd external ID fails
    as an AccessDenied that reads like a permissions problem."""
    policy = ai.trust_policy("serverally-abc", "123456789012")
    statement = policy["Statement"][0]
    assert statement["Action"] == "sts:AssumeRole"
    assert statement["Principal"]["AWS"] == "arn:aws:iam::123456789012:root"
    assert statement["Condition"]["StringEquals"]["sts:ExternalId"] == "serverally-abc"
    json.dumps(policy)          # must be pasteable as-is


def test_the_role_option_is_absent_when_we_have_no_identity_to_trust(monkeypatch):
    """Absent, not broken — the rule the asset and site menus already follow. Collecting an
    ARN we could never assume wastes their time and teaches them the feature does not work."""
    monkeypatch.setattr(ai.settings, "AWS_BASE_ACCESS_KEY_ID", "")
    monkeypatch.setattr(ai.settings, "AWS_BASE_SECRET_ACCESS_KEY", "")
    assert ai.base_configured() is False

    with pytest.raises(ai.AwsRoleError) as exc:
        ai.assume("arn:aws:iam::111122223333:role/X", "ext")
    assert "no AWS identity of its own" in str(exc.value)


def test_a_refused_assume_names_the_three_things_it_could_be():
    """AWS says AccessDenied for a wrong account, a wrong external ID and a missing role. A
    message that repeats "AccessDenied" sends somebody to check permissions, which is the one
    thing it usually is not."""
    msg = ai._role_message(Exception("AccessDenied"))            # noqa: SLF001
    assert "trust policy" in msg
    assert "external ID" in msg
    assert "does not exist" in msg


def test_our_own_broken_credentials_are_owned_rather_than_blamed_on_them():
    msg = ai._role_message(Exception("InvalidClientTokenId"))    # noqa: SLF001
    assert "our side to fix" in msg


# ── one session builder, both callers ────────────────────────────────────────

def test_both_aws_callers_go_through_the_same_session_builder():
    """`cloud_service` discovers instances and `ssm_service` runs commands. A second copy of
    "how do I become this account" is how one of them ends up not knowing roles exist — the
    seam that cost ten steps on a live deploy this morning."""
    from app.services import cloud_service, ssm_service

    for module, fn in ((cloud_service.AWSAdapter, "_session"), (ssm_service, "_client")):
        source = inspect.getsource(getattr(module, fn))
        assert "aws_identity.session_for" in source or "session_for(" in source, (
            f"{fn} builds its own session and would not know about roles")
        assert "boto3.session.Session(" not in source, f"{fn} still builds boto3 directly"


def test_a_key_connection_still_works_without_any_of_this(monkeypatch):
    """Roles are additive. An account connected with an access key must not start needing an
    identity we may not have."""
    monkeypatch.setattr(ai.settings, "AWS_BASE_ACCESS_KEY_ID", "")
    monkeypatch.setattr(ai, "is_role", lambda c: False)

    made = {}

    class _Sess:
        def __init__(self, **kw):
            made.update(kw)

    import boto3
    monkeypatch.setattr(boto3.session, "Session", _Sess)
    ai.session_for({"access_key_id": "AKIA", "secret_access_key": "s", "region": "eu-west-1"})
    assert made["aws_access_key_id"] == "AKIA"
    assert "aws_session_token" not in made
