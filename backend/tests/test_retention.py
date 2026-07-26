"""History retention tiers (docs/PRO-FEATURES-PLAN.md §4 #6).

This is the only feature whose implementation deletes customer data, so these tests are about
one question: can it ever delete more than it should?

The design answer is structural — the only query carrying a short cutoff filters
``plan = 'free'`` by name, so any account we cannot positively identify as Free keeps the long
window. These tests pin that, pin the list of tables that are never tier-pruned at all, and
pin that switching the feature on takes nothing away from anybody.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.services import retention_service as retention

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def enforced(monkeypatch):
    """With the plan wall armed — the only state in which anything is deleted by tier."""
    monkeypatch.setattr(settings, "ENFORCE_PLAN_LIMITS", True)


@pytest.fixture
def dormant(monkeypatch):
    monkeypatch.setattr(settings, "ENFORCE_PLAN_LIMITS", False)


# ── Nobody loses anything ────────────────────────────────────────────────────

def test_the_free_window_is_exactly_what_the_product_already_did():
    """The plan doc reads as though Free is being cut to 7 days. It is not: these were the
    fixed, tier-blind windows before retention became a tier, so switching this on only ever
    moves a cutoff further into the past for Pro.
    """
    assert retention.WINDOWS["metrics"][retention.FREE] == 7      # was RETENTION_HOURS 168
    assert retention.WINDOWS["uptime"][retention.FREE] == 30      # was CHECK_RETENTION_DAYS
    assert retention.WINDOWS["webhooks"][retention.FREE] == 14    # was DELIVERY_RETENTION_DAYS


def test_pro_never_keeps_less_than_free():
    """A tier that paid more must never be pruned harder. A typo here would be a silent,
    irreversible downgrade."""
    for kind, windows in retention.WINDOWS.items():
        assert windows[retention.PRO] >= windows[retention.FREE], kind


def test_while_the_plan_wall_is_dormant_everyone_keeps_the_long_window(dormant):
    """ENFORCE_PLAN_LIMITS is off in production today, so shipping this must not delete
    anything new for anyone."""
    for kind in retention.KINDS:
        assert retention.days_for(kind, "free") == retention.longest_days(kind)
        assert retention.free_cutoff(kind, NOW) is None, "the Free sweep must not run at all"


# ── Every failure mode keeps MORE data ───────────────────────────────────────

@pytest.mark.parametrize("plan", [None, "", "PRO", "Free", "agency", "enterprise", "trial", "unknown"])
def test_an_unidentifiable_plan_keeps_the_longest_window(enforced, plan):
    """A plan we cannot identify is a bug on our side, and the safe response to our own bug is
    to keep the customer's data.

    ``users.plan`` is ``NOT NULL DEFAULT 'free'``, so the None and "" cases cannot arrive from
    that column — verified live, where Postgres refused the insert. They are covered anyway
    because ``days_for`` is also reachable with a plan read from somewhere else: a cached value,
    an API payload, or a future column. The reachable case is the one in the middle: a tier we
    have not invented yet, such as an "agency" plan, must keep its data rather than be treated
    as Free.
    """
    for kind in retention.KINDS:
        assert retention.days_for(kind, plan) == retention.longest_days(kind), (kind, plan)


def test_free_gets_the_short_window_only_when_named_exactly(enforced):
    assert retention.days_for("metrics", "free") == 7
    assert retention.days_for("metrics", "pro") == 365
    # Anything else — including a near-miss — keeps the long one.
    assert retention.days_for("metrics", "freemium") == 365


def test_an_unknown_kind_refuses_rather_than_guessing(enforced):
    """Guessing a deletion window for a series this module does not know about is how a
    caller silently deletes the wrong table."""
    with pytest.raises(ValueError):
        retention.days_for("command_logs", "free")
    with pytest.raises(ValueError):
        retention.cutoff("missions", "free")


def test_the_global_cutoff_is_always_the_most_generous(enforced):
    for kind in retention.KINDS:
        assert retention.global_cutoff(kind, NOW) <= retention.cutoff(kind, "pro", NOW)
        free_cut = retention.free_cutoff(kind, NOW)
        if free_cut is not None:
            # The Free cutoff is NEWER (deletes more), which is why it is the one that has to
            # be filtered by plan.
            assert free_cut > retention.global_cutoff(kind, NOW)


def test_no_free_sweep_when_the_windows_are_equal(enforced, monkeypatch):
    """A sweep that would delete nothing is pure risk, so it does not run."""
    monkeypatch.setitem(retention.WINDOWS, "metrics", {retention.FREE: 30, retention.PRO: 30})
    assert retention.free_cutoff("metrics", NOW) is None


def test_cutoffs_are_in_the_past_and_the_right_distance(enforced):
    assert retention.cutoff("metrics", "free", NOW) == NOW - timedelta(days=7)
    assert retention.cutoff("metrics", "pro", NOW) == NOW - timedelta(days=365)


# ── Evidence is never tier-pruned ────────────────────────────────────────────

def test_the_evidence_tables_are_not_retention_kinds():
    """These are not history, they are records: they back client reports an agency may already
    have sent, the forensic trail of a compromise, Ally's memory of its own work, and billing.
    Adding one of them to WINDOWS would make it deletable, so this asserts the separation."""
    for table in retention.PROTECTED:
        assert table not in retention.WINDOWS, f"{table} must never be tier-pruned"


def test_the_protected_list_covers_what_reports_and_forensics_depend_on():
    """Named explicitly, so removing one is a deliberate act with a failing test attached."""
    for table in ("missions", "security_scans", "threat_scans", "command_logs",
                  "audit_logs", "ai_usage", "playbook_runs", "backup_runs"):
        assert table in retention.PROTECTED


def test_every_protected_table_says_why():
    """A list without reasons gets pruned by the next person who wants to save space."""
    for table, reason in retention.PROTECTED.items():
        assert len(reason) > 20, table


def test_only_the_three_high_volume_series_are_swept():
    """Scope discipline: retention applies to dense time-series, not to anything a customer
    would reasonably call a record."""
    assert set(retention.KINDS) == {"metrics", "uptime", "webhooks"}


# ── The sweep queries ────────────────────────────────────────────────────────

def test_the_short_cutoff_query_selects_free_accounts_by_name():
    """The load-bearing detail. `== 'free'` means an unknown plan is not matched and keeps its
    data; `!= 'pro'` would mean the opposite, and would delete a new tier's data by default."""
    import ast
    import inspect
    import textwrap

    from app.workers import retention_worker

    source = inspect.getsource(retention_worker._free_user_ids)
    assert "User.plan == retention.FREE" in source

    # Check the CODE, not the prose — the docstring legitimately mentions `!=` while
    # explaining why it is not used, and a naive substring search fails on its own comment.
    tree = ast.parse(textwrap.dedent(source))
    comparisons = [
        node for node in ast.walk(tree) if isinstance(node, ast.Compare)
    ]
    assert comparisons, "the plan filter is gone"
    for node in comparisons:
        assert all(isinstance(op, ast.Eq) for op in node.ops), (
            "the plan filter must be equality against 'free'; an inequality would make an "
            "unknown tier lose its data by default"
        )


def test_every_series_filter_scopes_the_free_clause_to_free_owners():
    """A filter that returned an unscoped clause for the Free sweep would delete every
    account's data at the Free cutoff — the single worst bug this feature could have."""
    import inspect

    from app.workers import retention_worker
    for name in ("_metric_filters", "_uptime_filters", "_webhook_filters"):
        source = inspect.getsource(getattr(retention_worker, name))
        assert "_free_user_ids()" in source, name
        # And the clause must be None when there is no Free cutoff, rather than falling back
        # to something unfiltered.
        assert "free_rows = None" in source, name


@pytest.mark.parametrize("kind", ["metrics", "uptime", "webhooks"])
def test_a_dormant_wall_produces_no_free_clause(dormant, kind):
    from app.workers import retention_worker

    _model, filters = retention_worker._SERIES[kind]
    _all_rows, free_rows = filters(
        retention.global_cutoff(kind, NOW), retention.free_cutoff(kind, NOW)
    )
    assert free_rows is None


@pytest.mark.parametrize("kind", ["metrics", "uptime", "webhooks"])
def test_an_armed_wall_produces_both_clauses(enforced, kind):
    from app.workers import retention_worker

    _model, filters = retention_worker._SERIES[kind]
    all_rows, free_rows = filters(
        retention.global_cutoff(kind, NOW), retention.free_cutoff(kind, NOW)
    )
    assert all_rows is not None and free_rows is not None


def test_an_unknown_series_cannot_be_swept():
    import asyncio

    from app.workers import retention_worker
    with pytest.raises(ValueError):
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            retention_worker.sweep("missions")
        )


# ── What the customer is told ────────────────────────────────────────────────

def test_the_settings_card_shows_the_honest_comparison(enforced):
    described = retention.describe("free")
    metrics = next(k for k in described["kinds"] if k["kind"] == "metrics")
    assert metrics["days"] == 7
    assert metrics["pro_days"] == 365
    assert metrics["label"] == "CPU, memory and disk history"
    # And it says what is kept regardless of plan, so retention never reads as "we delete
    # your records".
    assert "missions" in described["kept_forever"]
    assert "security_scans" in described["kept_forever"]


def test_the_card_is_truthful_while_the_wall_is_dormant(dormant):
    described = retention.describe("free")
    assert described["enforced"] is False
    metrics = next(k for k in described["kinds"] if k["kind"] == "metrics")
    assert metrics["days"] == 365, "a Free account really does keep the long window today"


def test_every_kind_has_a_plain_language_label():
    for kind in retention.KINDS:
        label = retention._LABELS[kind]
        assert label and label[0].isupper()
        assert "_" not in label  # a column name is not a label
