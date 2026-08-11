"""AWS Systems Manager as a transport.

The point of SSM is reaching a machine we cannot dial: no public address, port 22 shut, and no
key for anybody to lose. What makes it worth testing carefully is that it fails DIFFERENTLY
from SSH — quietly. An instance that is not registered answers nothing rather than refusing a
connection, and output over 24,000 characters is cut with no flag saying so. Both look exactly
like a healthy server that had nothing to report, which is the same false all-clear the
privilege work was written to stop.
"""
import asyncio

import pytest

from app.services import ssm_service as ssm


class _Server:
    def __init__(self, **over):
        self.id = "srv-1"
        self.connection_type = "ssm"
        self.cloud_account_id = "acc-1"
        self.cloud_instance_id = "i-0abc123"
        self.os_type = "ubuntu"
        self.tags = None
        self.encrypted_cred = "SHOULD-NEVER-BE-READ"
        self.__dict__.update(over)


# ── the honesty rules ────────────────────────────────────────────────────────

def test_an_unregistered_instance_is_not_reachable():
    """The normal case, not a fault: most instances have never been given a role.

    Fails closed on anything it cannot read, because "reachable" here means every later probe
    returns nothing — and nothing reads as a server with no sites and no findings.
    """
    assert ssm.is_managed({"InstanceInformationList": [
        {"InstanceId": "i-0abc123", "PingStatus": "Online"}]}, "i-0abc123") is True

    for answer in (
        {},                                                        # nothing came back
        {"InstanceInformationList": []},                           # registered nowhere
        {"InstanceInformationList": None},                         # malformed
        {"InstanceInformationList": [{"InstanceId": "i-other", "PingStatus": "Online"}]},
        {"InstanceInformationList": [                              # agent stopped answering
            {"InstanceId": "i-0abc123", "PingStatus": "ConnectionLost"}]},
    ):
        assert ssm.is_managed(answer, "i-0abc123") is False, answer


def test_the_not_managed_message_says_how_to_fix_it(monkeypatch):
    """An error naming an AWS API tells a customer nothing about what to switch on."""
    server = _Server()

    async def go():
        return await ssm.test_connection(server, _Account())

    monkeypatch.setattr(ssm, "_describe", lambda *_: {"InstanceInformationList": []})
    result = asyncio.run(go())

    assert result["ok"] is False
    for needed in ("SSM agent", "AmazonSSMManagedInstanceCore", "endpoints"):
        assert needed in result["error"], f"the fix does not mention {needed}"
    assert "INWARD" in result["error"], "must say nothing needs opening inward — that is the point"


def test_output_cut_at_the_limit_says_so():
    """AWS returns the first 24,000 characters and no flag saying it truncated.

    Length is the only signal there is, and a malware scan cut short looks precisely like a
    malware scan that found less — which is how a compromised server gets reported as clean.
    """
    out, err, code = ssm.read_output({
        "StandardOutputContent": "x" * ssm.INLINE_OUTPUT_LIMIT,
        "StandardErrorContent": "", "ResponseCode": 0, "Status": "Success",
    })
    assert len(out) == ssm.INLINE_OUTPUT_LIMIT
    assert "INCOMPLETE" in err
    assert code == 0


def test_the_notice_goes_to_stderr_not_into_the_output():
    """Appending it to stdout would corrupt the sentinel-delimited bundles our probes parse —
    turning a reporting problem into a parsing one."""
    out, err, _ = ssm.read_output({
        "StandardOutputContent": "y" * ssm.INLINE_OUTPUT_LIMIT,
        "StandardErrorContent": "", "ResponseCode": 0, "Status": "Success",
    })
    assert set(out) == {"y"}, "the output must come back exactly as AWS gave it"
    assert "ServerAlly" in err


def test_ordinary_output_gets_no_notice():
    """A warning on every command is a warning nobody reads."""
    out, err, code = ssm.read_output({
        "StandardOutputContent": "all fine\n", "StandardErrorContent": "",
        "ResponseCode": 0, "Status": "Success",
    })
    assert (out, err, code) == ("all fine\n", "", 0)


def test_a_command_that_never_ran_is_not_reported_as_success():
    """`ResponseCode` is absent when the command never executed. Defaulting that to 0 would
    turn "the agent never picked this up" into "it worked"."""
    _, _, code = ssm.read_output({"Status": "Failed", "StandardOutputContent": ""})
    assert code == 1
    _, _, ok = ssm.read_output({"Status": "Success", "StandardOutputContent": ""})
    assert ok == 0


# ── the security guarantee ───────────────────────────────────────────────────

class _Account:
    id = "acc-1"
    provider = "aws"
    encrypted_credential = "unused-in-these-tests"


def test_the_server_row_credential_is_never_read():
    """An SSM asset has no login of its own — it borrows the account's key, and that key is
    used HERE, in our process. Reading `encrypted_cred` would mean somebody had started
    storing a per-server secret for a transport that does not have one."""
    import inspect

    source = inspect.getsource(ssm)
    assert "encrypted_cred" not in source.replace("encrypted_credential", ""), (
        "ssm_service must never touch the server row's own credential")


def test_no_aws_key_ever_reaches_the_managed_instance(monkeypatch):
    """The whole reason this is safe to point at somebody else's account.

    The command sent to the instance is the caller's command and nothing else — no key
    material appended, no environment smuggled in.
    """
    sent = {}

    class _Client:
        def send_command(self, **kw):
            sent.update(kw)
            return {"Command": {"CommandId": "cmd-1"}}

        def get_command_invocation(self, **_):
            return {"Status": "Success", "ResponseCode": 0,
                    "StandardOutputContent": "ok", "StandardErrorContent": ""}

    monkeypatch.setattr(ssm, "_client", lambda *_: _Client())
    out, _, code = ssm._send_and_wait(_Server(), _Account(), "df -h", 30)   # noqa: SLF001

    assert (out, code) == ("ok", 0)
    assert sent["Parameters"] == {"commands": ["df -h"]}, "the command must go through as-is"
    blob = repr(sent)
    for secret in ("access_key_id", "secret_access_key", "aws_secret", "AKIA"):
        assert secret not in blob, f"{secret} reached the instance payload"


def test_a_disconnected_account_says_what_actually_happened():
    """Unlike every other transport, an SSM asset stops being reachable when its account is
    disconnected — the FK is SET NULL and the key goes with it. That deserves its own
    sentence, not a generic failure to connect."""
    with pytest.raises(ssm.SsmError) as exc:
        asyncio.run(ssm.account_for(_Server(cloud_account_id=None)))
    assert "no longer connected" in str(exc.value)
    assert "SSH" in str(exc.value), "must offer the way out, not just the diagnosis"


# ── the details that decide whether it works at all ──────────────────────────

def test_the_region_comes_from_the_asset_before_the_account():
    """An account left on "all regions" imports instances from several. Guessing one gives
    `InvalidInstanceId` for an instance that exists perfectly well somewhere else."""
    assert ssm._region_for(_Server(tags=["aws", "region:eu-west-2"]),          # noqa: SLF001
                           {"region": "us-east-1"}) == "eu-west-2"
    assert ssm._region_for(_Server(tags=["aws"]), {"region": "ap-south-1"}) == "ap-south-1"
    assert ssm._region_for(_Server(tags=None), {}) == "us-east-1"


def test_windows_and_linux_get_different_documents():
    """Sending the wrong one runs nothing at all."""
    assert ssm._document(_Server(os_type="ubuntu")) == "AWS-RunShellScript"    # noqa: SLF001
    assert ssm._document(_Server(os_type="Windows Server 2022")) == "AWS-RunPowerShellScript"
    assert ssm._document(_Server(os_type=None)) == "AWS-RunShellScript"


def test_a_command_that_never_finishes_stops_at_the_budget(monkeypatch):
    """SSM says nothing until the command ends, so there is no "no output for N seconds" to
    measure. Treating the timeout as idle time would mean never timing out at all."""
    class _Client:
        def send_command(self, **_):
            return {"Command": {"CommandId": "cmd-1"}}

        def get_command_invocation(self, **_):
            return {"Status": "InProgress"}

    monkeypatch.setattr(ssm, "_client", lambda *_: _Client())
    monkeypatch.setattr(ssm, "_POLL_START", 0.01)
    monkeypatch.setattr(ssm, "_POLL_MAX", 0.01)
    with pytest.raises(ssm.SsmError) as exc:
        ssm._send_and_wait(_Server(), _Account(), "sleep 999", 0)   # noqa: SLF001
    assert "still running" in str(exc.value)
    assert "cmd-1" in str(exc.value), "name the command id so the result can still be found"


def test_the_stream_says_there_is_no_stream(monkeypatch):
    """A progress box that sits empty for four minutes is read as a hang — the same lesson
    the apt-lock wait learned when it was silent."""
    async def go():
        server, account = _Server(), _Account()

        async def fake_execute(*_a, **_k):
            return ("done\n", "", 0)

        monkeypatch.setattr(ssm, "execute", fake_execute)
        return [chunk async for chunk in ssm.execute_stream(server, account, "ls")]

    chunks = asyncio.run(go())
    assert "does not stream" in chunks[0]
    assert "done\n" in chunks


def test_every_aws_error_becomes_something_a_customer_can_act_on():
    """"AccessDeniedException" names an API, not the permission to add."""
    cases = {
        "InvalidInstanceId": "terminated",
        "AccessDeniedException": "ssm:SendCommand",
        "ExpiredTokenException": "rotated",
        "ThrottlingException": "rate-limiting",
        "EndpointConnectionError": "endpoint",
    }
    for raw, expected in cases.items():
        assert expected in ssm._friendly(Exception(raw)), raw    # noqa: SLF001


def test_connection_manager_routes_ssm_everywhere_it_routes_ssh():
    """A transport wired into three of the four entry points is a transport that works until
    somebody opens a terminal."""
    import inspect

    from app.services import connection_manager

    source = inspect.getsource(connection_manager)
    for fn in ("test_connection", "execute", "execute_stream"):
        body = source.split(f"async def {fn}(", 1)[1].split("\nasync def ", 1)[0]
        assert 'connection_type == "ssm"' in body, f"{fn} does not route ssm"


def test_these_tests_left_the_module_as_they_found_it():
    """Patching a module global without restoring it hands the next test a stub and calls it
    a pass. `monkeypatch` undoes it; this asserts nobody stopped using it."""
    import inspect

    assert inspect.isfunction(ssm._client), "_client was replaced and not restored"
    assert inspect.iscoroutinefunction(ssm.execute), "execute was replaced and not restored"
    assert (ssm._POLL_START, ssm._POLL_MAX) == (0.4, 2.0)
