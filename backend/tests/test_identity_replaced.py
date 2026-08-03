"""What happens to our records when a server is replaced.

The owner rebuilt a test server, trusted the new host key, and the app went on showing the
three websites the OLD machine had — and, after a rescan cleared them, still refused to
offer the setup choice, because a completed setup record from the previous machine made it
look like ServerAlly already ran this one.

Both are the same fault: **records of the old machine outliving the machine**. Trusting a
new key is the customer telling us, explicitly, that this is different hardware, and until
now nothing acted on that.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import server_role as sr


def role(**kw):
    base = {"connection_type": "ssh", "panel_type": None,
            "setup_done": False, "site_count": 0}
    return sr.decide(**{**base, **kw})


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


# The REAL rule, not a copy of it. Written out here first, this test passed happily while
# the endpoint was mutated to ignore staleness — the exact "test the artefact, not the
# behaviour" trap, caught by mutation testing.
def _stale(finished_at, changed_at):
    return not sr.setup_applies(finished_at, changed_at)


def test_a_setup_that_finished_before_the_rebuild_no_longer_counts():
    """The exact bug. Without this the rebuilt server keeps claiming ServerAlly is its
    control panel, so Start here never comes back and Sites stays in the menu."""
    finished, changed = NOW - timedelta(days=2), NOW
    assert _stale(finished, changed) is True
    assert role(setup_done=not _stale(finished, changed))["role"] == "undecided"


def test_a_setup_run_after_the_rebuild_counts_normally():
    """The other direction matters just as much: someone rebuilds, sets the machine up
    again, and must not be asked to choose a second time."""
    finished, changed = NOW, NOW - timedelta(days=2)
    assert _stale(finished, changed) is False
    assert role(setup_done=not _stale(finished, changed))["role"] == "serverally"


def test_a_server_that_was_never_replaced_is_unaffected():
    """Almost every server. If this rule leaked into them it would re-ask the question on
    machines that answered it long ago."""
    assert _stale(NOW - timedelta(days=30), None) is False


def test_a_setup_still_running_is_not_judged_stale_by_a_missing_finish():
    """An unfinished setup has no finished_at, and treating that as "before the rebuild"
    would discard a setup that is happening right now."""
    assert _stale(None, NOW) is False


# ── What the trust action itself has to do ───────────────────────────────────

def test_trusting_a_new_key_forgets_the_previous_machine():
    """Read from the source because the effect spans three tables and one commit; what is
    being pinned is that all four things happen together, not how.

    Sites are marked ABSENT rather than deleted, which is the same rule the discovery scan
    follows — during an incident "when did this disappear?" is exactly the question.
    """
    import inspect

    from app.routers import servers as servers_router

    src = inspect.getsource(servers_router._forget_the_previous_machine)
    assert "identity_changed_at" in src, "nothing would mark the setup record stale"
    assert "is_present=False" in src, "the old machine's websites would keep showing"
    assert "panel_type = None" in src, "a panel from the old machine would keep the menu"
    assert "delete" not in src.lower(), (
        "sites must be marked absent, never deleted — the scan's rule, so the question "
        "'when did this disappear' stays answerable")


def test_the_trust_endpoint_actually_calls_it():
    """The guard above is worth nothing if the endpoint stops calling it."""
    import inspect

    from app.routers import servers as servers_router

    src = inspect.getsource(servers_router.trust_server_key)
    assert "_forget_the_previous_machine" in src


@pytest.mark.parametrize("kind", ["winrm", "rdp"])
def test_an_asset_that_never_answers_the_question_is_untouched(kind):
    assert role(connection_type=kind)["applies"] is False


# ── The rule has to live at the READ, not at one caller ──────────────────────

class _FakeResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _FakeDb:
    def __init__(self, row):
        self._row = row

    async def execute(self, _stmt):
        return _FakeResult(self._row)


class _Setup:
    def __init__(self, finished_at, status="done"):
        self.finished_at, self.status = finished_at, status


class _Server:
    id = "s"

    def __init__(self, changed_at):
        self.identity_changed_at = changed_at


@pytest.mark.asyncio
async def test_a_setup_from_the_previous_machine_is_not_returned_at_all():
    """The second half of the same bug, found by the owner pressing the button.

    The Start-here page correctly offered the choice, they picked ServerAlly — and the
    setup screen said "This server is set up", listing fourteen steps that ran on hardware
    that no longer exists, with nothing to press. Stuck.

    Fixed at the read rather than at the caller: the first version of this rule lived at
    one call site, and the setup panel simply never got it.
    """
    from app.routers import server_setup

    row = _Setup(finished_at=NOW - timedelta(days=2))
    assert await server_setup._latest(_Server(NOW), _FakeDb(row)) is None


@pytest.mark.asyncio
async def test_a_setup_that_ran_on_this_machine_is_returned():
    from app.routers import server_setup

    row = _Setup(finished_at=NOW)
    assert await server_setup._latest(_Server(NOW - timedelta(days=2)), _FakeDb(row)) is row


@pytest.mark.asyncio
async def test_a_setup_running_right_now_is_never_discarded():
    """It has no finish time. Treating that as "before the rebuild" would hide a setup
    that is happening while the customer watches it."""
    from app.routers import server_setup

    row = _Setup(finished_at=None, status="running")
    assert await server_setup._latest(_Server(NOW), _FakeDb(row)) is row


def test_no_caller_re_implements_the_rule():
    """What actually went wrong: the rule was applied at one of four call sites. If it
    reappears beside a caller, that caller is the only one protected again."""
    import inspect

    from app.routers import server_setup

    src = inspect.getsource(server_setup)
    assert src.count("setup_applies") == 1, (
        "the staleness rule belongs at the read, so every caller gets it")
    assert "_latest(server.id" not in src, (
        "_latest takes the server so it can see identity_changed_at")


# ── "we set this up" is not the same as "we are its panel" ───────────────────

def test_only_a_server_we_actually_set_up_says_so():
    """Both of these answer role=serverally, and the difference decides whether the Sites
    page tells the owner their server is ready.

    A server we merely FOUND websites on was never set up by us — claiming it was would
    announce a setup that never ran, on a machine somebody else built.
    """
    ours = role(setup_done=True)
    found = role(site_count=3)
    assert ours["role"] == found["role"] == "serverally"
    assert ours["set_up_by_us"] is True
    assert found["set_up_by_us"] is False


def test_a_setup_from_the_previous_machine_does_not_claim_this_one_is_ready():
    """The staleness rule reaches this too, or a rebuilt server greets its owner with a
    'ready' banner for software the rebuild removed."""
    stale = _stale(NOW - timedelta(days=2), NOW)
    assert role(setup_done=not stale)["set_up_by_us"] is False


@pytest.mark.parametrize("kind", ["winrm", "rdp"])
def test_an_asset_we_never_set_up_never_claims_we_did(kind):
    assert role(connection_type=kind)["set_up_by_us"] is False
