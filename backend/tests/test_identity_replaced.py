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
