"""Plan gates for the three tiers (docs/PRICING-TIERS-AND-GATES.md, approved 2026-07-26).

Four properties, each of which would be a real incident if it broke:

1. **Safety is never gated.** A free user whose site is hacked and who cannot run a scan will
   blame us, not their plan. This list is also a public promise on the pricing page.
2. **An unrecognised plan fails GENEROUS.** The previous code fell back to Free, so the moment
   a third tier existed any missed code path would silently downgrade a paying customer.
3. **A downgrade never breaks what is running.** Gates sit on *create*, never on *use* — an
   autopilot task watching production must not stop because an invoice lapsed.
4. **A lock in the UI always agrees with the gate that refuses the request**, because both read
   the same function.
"""
from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services import entitlements as ent


class U:
    """Minimal stand-in for a User row."""

    def __init__(self, plan):
        self.plan = plan
        self.id = "u1"


@pytest.fixture
def armed(monkeypatch):
    """With the plan wall on — the only state in which anything is refused."""
    monkeypatch.setattr(settings, "ENFORCE_PLAN_LIMITS", True)


@pytest.fixture
def dormant(monkeypatch):
    monkeypatch.setattr(settings, "ENFORCE_PLAN_LIMITS", False)


# ── 1. Safety is never gated ─────────────────────────────────────────────────

@pytest.mark.parametrize("feature", [
    "backups", "offsite_backups", "security_scans", "threat_detection",
    "incident_response", "uptime_monitoring", "certificate_expiry",
    "ally_chat", "missions", "verification_gate",
])
def test_a_free_user_keeps_every_safety_feature(armed, feature):
    """The competitive weapon. Ploi hides backups on its cheap tier and it is their loudest
    complaint; we say out loud that we never do that, so it has to stay true."""
    assert ent.allows(U("free"), feature) is True


def test_the_never_gated_list_cannot_quietly_shrink():
    """Removing an entry here changes a public promise, so it should require deleting a line
    from this test too."""
    for feature in ("backups", "security_scans", "threat_detection", "incident_response",
                    "ally_chat", "missions", "verification_gate", "uptime_monitoring"):
        assert feature in ent.NEVER_GATED


def test_a_safety_feature_is_never_also_a_paid_feature():
    """If a name appeared in both, the gate's answer would depend on check order."""
    assert not set(ent.NEVER_GATED) & set(ent.FEATURES)


def test_the_free_plan_grants_the_same_ally(armed):
    """Rule 1: gate scale and audience, never capability. A degraded free Ally would break the
    moment that makes people pay."""
    free = U("free")
    assert ent.allows(free, "ally_chat")
    assert ent.allows(free, "missions")
    assert ent.allows(free, "verification_gate")


# ── 2. An unrecognised plan fails generous ───────────────────────────────────

@pytest.mark.parametrize("plan", [None, "", "enterprise", "trial", "startup", "lifetime"])
def test_an_unknown_plan_gets_the_most_generous_limits(armed, plan, caplog):
    """The bug this replaced: falling back to Free meant one missed code path would throttle a
    paying customer with nothing logged."""
    limits = ent.limits_for(U(plan))
    assert limits is ent.PLANS[ent.PRO_PLUS]
    assert limits["max_servers"] == 50


def test_an_unknown_plan_logs_loudly(armed, caplog):
    """Failing generous silently would hide a billing bug for months."""
    with caplog.at_level("ERROR"):
        ent.limits_for(U("mystery-tier"))
    assert any("UNKNOWN PLAN" in r.message for r in caplog.records)


@pytest.mark.parametrize("plan,expected", [
    ("pro_plus", ent.PRO_PLUS), ("pro-plus", ent.PRO_PLUS), ("Pro Plus", ent.PRO_PLUS),
    ("proplus", ent.PRO_PLUS), ("pro+", ent.PRO_PLUS), ("agency", ent.PRO_PLUS),
    ("PRO", ent.PRO), (" free ", ent.FREE),
])
def test_the_spellings_billing_might_send_all_resolve(plan, expected):
    """A mismatch here downgrades a paying customer, so accept the plausible variants rather
    than only the canonical one."""
    assert ent.normalise(plan) == expected


def test_an_unknown_FEATURE_fails_closed_not_open(armed, caplog):
    """Opposite direction from an unknown plan, deliberately: an unrecognised feature name
    means the caller has a typo, and allowing it would make every gate meaningless."""
    with caplog.at_level("ERROR"):
        assert ent.allows(U("pro_plus"), "teleportation") is False
    assert any("Unknown feature" in r.message for r in caplog.records)


# ── 3. Nothing blocks while the wall is dormant ──────────────────────────────

def test_with_limits_dormant_a_free_user_can_do_everything(dormant):
    """Production state today. Shipping the gates must change nothing for current users."""
    free = U("free")
    for feature in ent.FEATURES:
        assert ent.allows(free, feature) is True
    assert ent.count_gate(free, "max_runbooks", 999) == (True, 0)


def test_require_raises_402_when_armed(armed):
    with pytest.raises(HTTPException) as exc:
        ent.require(U("free"), ent.AUTOPILOT)
    # 402 matches the existing server-cap wall, so the frontend has one code to recognise.
    assert exc.value.status_code == 402


def test_require_is_silent_when_allowed(armed):
    assert ent.require(U("pro"), ent.AUTOPILOT) is None


# ── The tier ladder ──────────────────────────────────────────────────────────

def test_each_tier_includes_everything_the_one_below_it_does(armed):
    """A customer who upgrades must never lose something. This is what makes "only ever add
    tiers above" safe."""
    free, pro, plus = (set(ent.PLANS[p]["features"]) for p in (ent.FREE, ent.PRO, ent.PRO_PLUS))
    assert free <= pro <= plus


def test_counts_never_decrease_as_the_tier_rises():
    keys = ("actions_per_month", "max_servers", "max_runbooks",
            "max_status_pages", "max_team_members")
    for key in keys:
        values = [ent.PLANS[p][key] for p in (ent.FREE, ent.PRO, ent.PRO_PLUS)]
        assert values == sorted(values), f"{key} is not monotonic: {values}"


@pytest.mark.parametrize("feature,tier", [
    (ent.AUTOPILOT, "Pro"), (ent.SMS_ALERTS, "Pro"), (ent.API_ACCESS, "Pro"),
    (ent.CUSTOM_RUNBOOKS, "Pro"), (ent.TEAM, "Pro"),
    (ent.CLIENT_REPORTS, "Pro+"), (ent.WHITE_LABEL, "Pro+"),
])
def test_each_feature_sits_on_the_tier_the_plan_doc_says(feature, tier):
    """Pro+ is defined by OTHER PEOPLE — clients who receive reports, and your own branding.
    That is the whole reason an agency pays the higher price."""
    assert ent.PLANS[ent.required_plan(feature)]["label"] == tier


def test_the_agency_features_are_exactly_the_pro_plus_ones(armed):
    pro = U("pro")
    assert not ent.allows(pro, ent.CLIENT_REPORTS)
    assert not ent.allows(pro, ent.WHITE_LABEL)
    # …and a Pro customer keeps everything else.
    for feature in (ent.AUTOPILOT, ent.SMS_ALERTS, ent.API_ACCESS, ent.CUSTOM_RUNBOOKS, ent.TEAM):
        assert ent.allows(pro, feature)


# ── Count gates ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("plan,used,expected", [
    ("free", 0, False),      # free includes no runbooks at all
    ("pro", 4, True),
    ("pro", 5, False),       # at the limit
    ("pro_plus", 5, True),
])
def test_the_runbook_count_gate(armed, plan, used, expected):
    allowed, _limit = ent.count_gate(U(plan), "max_runbooks", used)
    assert allowed is expected


def test_a_zero_limit_reads_as_not_included_rather_than_full(armed):
    """"You're using all 0 of your runbooks" would be nonsense."""
    message = ent.count_message(U("free"), "runbooks", 0)
    assert "aren't included" in message
    assert "using all" not in message


def test_a_reached_limit_says_how_many_you_have(armed):
    message = ent.count_message(U("pro"), "runbooks", 5)
    assert "5 runbooks" in message


# ── 4. The wall text is useful ───────────────────────────────────────────────

def test_the_wall_names_the_feature_and_the_tier(armed):
    """"Upgrade to continue" tells someone nothing about what they would be buying."""
    message = ent.upgrade_message(U("free"), ent.AUTOPILOT)
    assert "Ally working on a schedule" in message
    assert "included in Pro" in message
    assert "You're on Free" in message


def test_every_paid_feature_has_a_plain_language_label():
    for feature in ent.FEATURES:
        label = ent.FEATURE_LABELS[feature]
        assert label and "_" not in label, feature


# ── The UI reads the same source as the gate ─────────────────────────────────

def test_describe_agrees_with_allows_for_every_feature(armed):
    """A lock that disagreed with the gate would let someone fill in a form and then be
    refused — the exact experience the locks exist to prevent."""
    for plan in (ent.FREE, ent.PRO, ent.PRO_PLUS):
        user = U(plan)
        described = ent.describe(user)
        for feature in ent.FEATURES:
            assert described["features"][feature]["allowed"] == ent.allows(user, feature)


def test_describe_is_honest_while_the_wall_is_dormant(dormant):
    described = ent.describe(U("free"))
    assert described["enforced"] is False
    assert all(f["allowed"] for f in described["features"].values())
    # …but still reports the real plan and its real numbers.
    assert described["plan_label"] == "Free"
    assert described["limits"]["servers"] == 2


def test_describe_publishes_the_never_gated_promise(armed):
    """The UI shows this list so retention and gating never read as "we take things away"."""
    described = ent.describe(U("free"))
    assert "backups" in described["never_gated"]
    assert "security_scans" in described["never_gated"]


# ── 3 (continued). Gates sit on CREATE, never on USE ─────────────────────────

# Paid features that are GENERATED on demand rather than stored, so gating their read is
# correct: there is no previously-created thing for a downgraded customer to lose access to,
# and leaving them open would hand the whole feature away for free.
_ON_DEMAND_PAID_READS = {
    "/api/servers/{server_id}/client-report": "the report is built per request, not stored",
}

# Actions that operate on something the customer ALREADY created. Gating one of these is what
# turns a lapsed invoice into an outage.
_ACTS_ON_EXISTING = {"run", "test", "send", "acknowledge", "resolve", "restore", "stop"}


def test_gates_are_only_on_create_endpoints():
    """The load-bearing property for anyone who downgrades. A gate on running, testing or
    sending would stop a live autopilot task, break a webhook mid-delivery, or silence an
    on-call page — turning a billing event into an outage.
    """
    import main

    offenders = []
    for route in main.app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None or not path.startswith("/api"):
            continue
        try:
            source = inspect.getsource(endpoint)
        except (OSError, TypeError):
            continue
        if "entitlements.require" not in source and "entitlements.count_gate" not in source:
            continue

        # A gated route should be a write, unless it generates a paid artefact on demand.
        read_only = "GET" in methods and not (methods - {"GET", "HEAD", "OPTIONS"})
        if read_only and path not in _ON_DEMAND_PAID_READS:
            offenders.append(f"{path} (GET, and not a documented on-demand paid read)")

        # Compare PATH SEGMENTS, not substrings. A substring check reports "/api/runbooks" as
        # a "/run" action, which is the same class of false positive as a malware scan
        # flagging "judicious" for containing "judi".
        segments = {s for s in path.split("/") if s}
        if segments & _ACTS_ON_EXISTING:
            offenders.append(f"{path} (acts on something already created)")
    assert not offenders, f"gates found on non-create routes: {offenders}"


def test_the_segment_check_does_not_false_positive_on_runbooks():
    """Guards the fix above: "/api/runbooks" must not read as a "/run" action."""
    assert not {s for s in "/api/runbooks".split("/") if s} & _ACTS_ON_EXISTING
    assert {s for s in "/api/backups/{id}/run".split("/") if s} & _ACTS_ON_EXISTING


def test_every_on_demand_paid_read_states_why_it_is_allowed():
    """An exception list without reasons becomes a place to hide gates that should not exist."""
    for path, reason in _ON_DEMAND_PAID_READS.items():
        assert len(reason) > 20, path


def test_the_paid_feature_creates_are_actually_gated():
    """The other half — a gate nobody wired up is worth nothing. Named routes, so deleting a
    gate fails here rather than silently giving a feature away."""
    import main

    must_be_gated = {
        "/api/autopilot/tasks": ent.AUTOPILOT,
        "/api/api-keys": ent.API_ACCESS,
        "/api/webhooks": ent.API_ACCESS,
        "/api/client-reports": ent.CLIENT_REPORTS,
        "/api/runbooks": ent.CUSTOM_RUNBOOKS,
        "/api/team/invite": ent.TEAM,
    }
    found: dict[str, bool] = {p: False for p in must_be_gated}
    for route in main.app.routes:
        path = getattr(route, "path", "")
        if path not in found or "POST" not in (getattr(route, "methods", set()) or set()):
            continue
        try:
            source = inspect.getsource(route.endpoint)
        except (OSError, TypeError):
            continue
        found[path] = "entitlements.require" in source or "entitlements.count_gate" in source
    missing = [p for p, ok in found.items() if not ok]
    assert not missing, f"these paid creates have no gate: {missing}"
