"""Entitlements — the one place that decides what a plan includes.

Three tiers, from [PRICING-TIERS-AND-GATES.md](../../../docs/PRICING-TIERS-AND-GATES.md)
(approved 2026-07-26): **Free $0 · Pro $9 · Pro+ $19**. Plans differ on three axes:
**counts** (servers, Ally requests, runbooks, status pages, team logins), **features** (what a
tier switches on at all), and **history** (owned separately by ``retention_service``).

Four rules shape everything here.

**1. Gate by scale and audience, never by capability, never by safety.** A Free user gets the
*same Ally* — same model, same expert procedures, same missions, same verification gate — and
every safety feature: backups, security scans, malware detection, incident response,
certificate warnings. That list is a competitive weapon (Ploi hides backups on its cheap tier
and it is their loudest complaint), so it lives in ``NEVER_GATED`` and is pinned by a test
rather than left to memory.

**2. An unrecognised plan gets the MOST generous limits, and says so loudly.** The previous
version fell back to Free, which meant that the moment a third tier existed, any code path not
updated would silently downgrade a paying customer — they would hit a wall they paid not to
hit, and nothing would log it. Failing generous is not exploitable either: ``users.plan`` is
set only by the billing integration or by hand, never by the customer.

**3. Gate CREATING, not USING.** Someone who downgrades keeps what already exists — their
running autopilot task, their webhook, their runbooks. We refuse the *next* one. Breaking
something already working would be a support incident, and for an autopilot task watching a
production server, a real risk.

**4. Nothing blocks while ``ENFORCE_PLAN_LIMITS`` is off** — the default. The numbers are
always measured and always shown; they only stop anyone once the wall is armed.
"""
from __future__ import annotations

import logging

from app.models.user import User

logger = logging.getLogger(__name__)

FREE = "free"
PRO = "pro"
PRO_PLUS = "pro_plus"

# ── Feature names ────────────────────────────────────────────────────────────
# Constants, not bare strings at the call sites: a typo'd string reads as "not allowed" and
# would silently lock a paying customer out of something they bought.

AUTOPILOT = "autopilot"                # Ally works on a schedule, within your policy
SMS_ALERTS = "sms_alerts"              # on-call by text / Telegram (costs real money)
API_ACCESS = "api_access"              # API keys + webhooks for the customer's own tools
CUSTOM_RUNBOOKS = "custom_runbooks"    # teach Ally your own procedures
CLIENT_REPORTS = "client_reports"      # the monthly report an agency sends its client
WHITE_LABEL = "white_label"            # remove our name from what clients see
TEAM = "team"                          # invite colleagues

FEATURES = (
    AUTOPILOT, SMS_ALERTS, API_ACCESS, CUSTOM_RUNBOOKS,
    CLIENT_REPORTS, WHITE_LABEL, TEAM,
)

# Available on EVERY plan, including free. Not a list of things we happen not to gate — a
# promise we make out loud on the pricing page. See rule 1.
NEVER_GATED = (
    "backups",                 # including sending them off the server
    "offsite_backups",
    "security_scans",
    "threat_detection",        # malware / intrusion
    "incident_response",
    "uptime_monitoring",
    "certificate_expiry",
    "ally_chat",               # the full experience, never a degraded model
    "missions",
    "verification_gate",
    "status_pages",            # the COUNT is limited; having one is not
    "file_manager",
    "terminal",
    "playbooks",
)

# Plain language, so an error or a lock reads like a sentence.
FEATURE_LABELS = {
    AUTOPILOT: "Ally working on a schedule",
    SMS_ALERTS: "text and Telegram alerts",
    API_ACCESS: "API keys and webhooks",
    CUSTOM_RUNBOOKS: "your own runbooks",
    CLIENT_REPORTS: "client reports",
    WHITE_LABEL: "your own branding",
    TEAM: "team logins",
}

PLANS: dict[str, dict] = {
    FREE: {
        "label": "Free",
        "actions_per_month": 20,
        "max_servers": 2,
        "max_runbooks": 0,
        "max_status_pages": 1,
        "max_team_members": 0,
        "features": (),
    },
    PRO: {
        "label": "Pro",
        "actions_per_month": 50,
        "max_servers": 10,
        "max_runbooks": 5,
        "max_status_pages": 3,
        "max_team_members": 2,
        "features": (AUTOPILOT, SMS_ALERTS, API_ACCESS, CUSTOM_RUNBOOKS, TEAM),
    },
    PRO_PLUS: {
        "label": "Pro+",
        "actions_per_month": 100,
        # Level with RunCloud's 50-for-$19, so a buyer compares features rather than counts.
        "max_servers": 50,
        "max_runbooks": 1000,          # "unlimited" in the UI; a number keeps the code honest
        "max_status_pages": 1000,
        "max_team_members": 10,
        "features": FEATURES,          # everything
    },
}

# The tier an unrecognised plan receives (rule 2).
_MOST_GENEROUS = PRO_PLUS


def normalise(plan: str | None) -> str:
    """Map a stored plan string to a known tier, or "" if unrecognised.

    Accepts the spellings billing might plausibly send for the top tier. A mismatch here
    downgrades a paying customer, which is the exact failure this module exists to prevent.
    """
    raw = (plan or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in PLANS:
        return raw
    if raw in ("proplus", "pro+", "plus", "agency"):
        return PRO_PLUS
    return ""


def limits_for_plan(plan: str | None, who: str = "?") -> dict:
    """The limits map for a plan STRING.

    The single implementation — ``limits_for`` and the admin console both come through here,
    so an operator is never shown different limits from the ones actually enforced. (The
    console previously reimplemented this lookup and inherited the fall-back-to-Free bug.)
    """
    resolved = normalise(plan)
    if resolved:
        return PLANS[resolved]

    logger.error(
        "UNKNOWN PLAN %r for user %s — granting %s limits so a paying customer is never "
        "silently downgraded. Add the plan to entitlements.PLANS.",
        plan, who, _MOST_GENEROUS,
    )
    return PLANS[_MOST_GENEROUS]


def limits_for(user: User) -> dict:
    """The limits map for a user's plan.

    An unrecognised plan gets the most generous tier and a loud log line — never a silent
    downgrade of somebody who is paying.
    """
    return limits_for_plan(getattr(user, "plan", None), str(getattr(user, "id", "?")))


def plan_label(user: User) -> str:
    return limits_for(user)["label"]


def allows(user: User, feature: str) -> bool:
    """Is ``feature`` included in this user's plan?

    True for anything in ``NEVER_GATED``, and true for everything while the wall is dormant.
    An unknown feature name returns **False** and logs — the opposite direction from an
    unknown *plan*, because an unrecognised feature means the caller has a typo, and silently
    allowing it would make every gate meaningless.
    """
    from app.config import settings

    if feature in NEVER_GATED:
        return True
    if feature not in FEATURES:
        logger.error("Unknown feature %r checked against a plan — refusing. "
                     "Use a constant from entitlements.", feature)
        return False
    if not settings.ENFORCE_PLAN_LIMITS:
        return True
    return feature in limits_for(user)["features"]


def required_plan(feature: str) -> str:
    """The cheapest tier that includes ``feature``."""
    for name in (FREE, PRO, PRO_PLUS):
        if feature in PLANS[name]["features"]:
            return name
    return PRO_PLUS


def upgrade_message(user: User, feature: str) -> str:
    """The wall text. Names the feature and the tier that includes it — "upgrade to continue"
    tells someone nothing about what they would be buying."""
    label = FEATURE_LABELS.get(feature, feature.replace("_", " "))
    tier = PLANS[required_plan(feature)]["label"]
    return (f"{label[0].upper()}{label[1:]} is included in {tier}. "
            f"You're on {plan_label(user)} — upgrade to switch it on.")


def require(user: User, feature: str) -> None:
    """Raise a clean 402 unless the plan includes ``feature``.

    402 Payment Required matches the existing server-cap wall, so the frontend has one status
    code meaning "this needs a bigger plan".
    """
    if allows(user, feature):
        return
    from fastapi import HTTPException
    raise HTTPException(status_code=402, detail=upgrade_message(user, feature))


def count_limit(user: User, key: str) -> int:
    """A numeric limit by name, e.g. ``max_runbooks``."""
    return int(limits_for(user).get(key, 0))


def count_gate(user: User, key: str, used: int) -> tuple[bool, int]:
    """``(allowed, limit)`` for adding one more of something.

    Never blocks while the wall is dormant, and only ever refuses the NEXT one — what already
    exists is untouched (rule 3).
    """
    from app.config import settings

    limit = count_limit(user, key)
    if not settings.ENFORCE_PLAN_LIMITS:
        return True, limit
    return used < limit, limit


def count_message(user: User, thing: str, limit: int) -> str:
    if limit <= 0:
        return (f"{thing[0].upper()}{thing[1:]} aren't included in {plan_label(user)}. "
                "Upgrade to add them.")
    return (f"Your plan includes {limit} {thing} and you're already using all of them. "
            "Upgrade for more.")


def describe(user: User) -> dict:
    """The whole entitlement picture, for ``/api/usage/me`` and the UI locks.

    The frontend renders locks from this rather than re-implementing the rules, so changing a
    plan never needs a matching frontend edit.
    """
    from app.config import settings

    limits = limits_for(user)
    return {
        "plan": normalise(getattr(user, "plan", None)) or _MOST_GENEROUS,
        "plan_label": limits["label"],
        "enforced": bool(settings.ENFORCE_PLAN_LIMITS),
        "limits": {
            "servers": limits["max_servers"],
            "actions": limits["actions_per_month"],
            "runbooks": limits["max_runbooks"],
            "status_pages": limits["max_status_pages"],
            "team_members": limits["max_team_members"],
        },
        # feature -> {allowed, label, required_plan} so a lock can explain itself.
        "features": {
            name: {
                "allowed": allows(user, name),
                "label": FEATURE_LABELS.get(name, name),
                "required_plan": PLANS[required_plan(name)]["label"],
            }
            for name in FEATURES
        },
        "never_gated": list(NEVER_GATED),
    }
