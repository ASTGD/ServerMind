"""How long history is kept, per plan.

This is the only feature in the product whose implementation **deletes customer data**, so
almost all of the design here is about making a scheduled destructive job safe rather than
about tiers.

**Nobody loses anything.** The three high-volume series already had a fixed retention window
before this existed — metrics 7 days, uptime checks 30 days, webhook deliveries 14 days. Those
windows become the FREE tier unchanged, and Pro simply gets a longer one. So the change only
ever moves a cutoff *further into the past*; it never starts deleting something that used to
be kept. (The plan doc describes this as "7 days free vs 12 months Pro", which reads as though
Free is being cut — it is not, and it should not be.)

**Over-deleting Pro data is structurally impossible**, not merely unlikely:

1. A global sweep runs at the most generous window. It catches everything, including rows
   whose server or owner has since been deleted, so nothing grows forever.
2. A second sweep applies the shorter Free window, filtered on ``plan = 'free'`` explicitly.

Because the only query carrying a short cutoff selects Free accounts *by name*, a Pro account —
or an account whose plan is NULL, misspelled, or a tier we have not invented yet — is never
matched by it, and keeps the long window. Every failure mode therefore keeps more data.

**What is never tier-pruned:** missions, security and threat scans, command logs, audit logs
and the AI usage ledger. Those are not history, they are *evidence* — they back the client
reports an agency has already sent, the forensic record of a compromise, Ally's memory of its
own work, and billing. A test pins that list.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.config import settings

logger = logging.getLogger(__name__)

FREE = "free"
PRO = "pro"

# The three series that carry a retention window. Free values are exactly what the product
# already did before retention became a tier, so switching this on takes nothing away.
WINDOWS: dict[str, dict[str, int]] = {
    # 5-minute samples: a year is ~105k rows per server, which is the honest storage cost
    # behind this being a paid tier.
    "metrics": {FREE: 7, PRO: 365},
    # One row per check per monitor — the densest table in the product.
    "uptime": {FREE: 30, PRO: 365},
    # Debugging trail for an integration, not a record anyone reports on.
    "webhooks": {FREE: 14, PRO: 90},
}

KINDS = tuple(WINDOWS)

# Never tier-pruned. Listed here so the reason lives with the rule, and pinned by a test.
PROTECTED = {
    "missions": "back the incident and client reports an agency may already have sent",
    "security_scans": "the forensic record of a server's posture over time",
    "threat_scans": "the evidence of a compromise, which is worth most long after the fact",
    "command_logs": "the audit trail of what Ally did, and Ally's memory of its own work",
    "audit_logs": "the administrative record, including entitlement changes",
    "ai_usage": "billing and metering evidence",
    "playbook_runs": "what was installed and when — re-derived into the Installed view",
    "backup_runs": "proof that a backup ran, which is the point of having backups",
}


def days_for(kind: str, plan: str | None) -> int:
    """How many days of ``kind`` this plan keeps.

    Unknown or missing plans get the LONGEST window. A plan we cannot identify is a bug on our
    side, and the safe response to our own bug is to keep the customer's data, not delete it.
    """
    windows = WINDOWS.get(kind)
    if windows is None:
        # An unknown kind means a caller is out of step with this module; refuse to guess a
        # deletion window for it.
        raise ValueError(f"Unknown retention kind '{kind}'")

    longest = max(windows.values())
    if not settings.ENFORCE_PLAN_LIMITS:
        # The plan wall is dormant, so everyone gets the generous window — same posture as the
        # server and action limits. This is why shipping retention changes no deletions today.
        return longest
    if plan == FREE:
        return windows[FREE]
    if plan == PRO:
        return windows[PRO]
    return longest


def longest_days(kind: str) -> int:
    """The most generous window — used by the global sweep that catches orphaned rows."""
    return max(WINDOWS[kind].values())


def free_days(kind: str) -> int:
    """The Free window, and the floor on how aggressive any sweep may be."""
    return WINDOWS[kind][FREE]


def cutoff(kind: str, plan: str | None, now: datetime | None = None) -> datetime:
    """The timestamp before which ``plan``'s rows of ``kind`` may be deleted."""
    now = now or datetime.now(tz=timezone.utc)
    return now - timedelta(days=days_for(kind, plan))


def free_cutoff(kind: str, now: datetime | None = None) -> datetime | None:
    """The Free-tier cutoff, or None when the Free sweep must not run.

    Returns None when the plan wall is dormant, or when Free and Pro happen to share a window —
    in both cases the extra sweep would delete nothing and only risk a mistake.
    """
    if not settings.ENFORCE_PLAN_LIMITS:
        return None
    if WINDOWS[kind][FREE] >= WINDOWS[kind][PRO]:
        return None
    now = now or datetime.now(tz=timezone.utc)
    return now - timedelta(days=WINDOWS[kind][FREE])


def global_cutoff(kind: str, now: datetime | None = None) -> datetime:
    """The cutoff for the sweep that applies to every row regardless of owner."""
    now = now or datetime.now(tz=timezone.utc)
    return now - timedelta(days=longest_days(kind))


def describe(plan: str | None) -> dict:
    """What this account keeps, for the Settings card.

    Includes the Pro figures so the comparison is honest — a customer should be able to see
    what upgrading actually buys without reading a pricing page.
    """
    return {
        "enforced": bool(settings.ENFORCE_PLAN_LIMITS),
        "plan": plan or "free",
        "kinds": [
            {
                "kind": kind,
                "label": _LABELS[kind],
                "days": days_for(kind, plan),
                "free_days": WINDOWS[kind][FREE],
                "pro_days": WINDOWS[kind][PRO],
            }
            for kind in KINDS
        ],
        "kept_forever": sorted(PROTECTED),
    }


_LABELS = {
    "metrics": "CPU, memory and disk history",
    "uptime": "Uptime check history",
    "webhooks": "Webhook delivery history",
}


def log_prune(kind: str, scope: str, deleted: int, cut: datetime) -> None:
    """Record what a sweep removed.

    A destructive job that deletes silently is a job nobody can audit after the fact, so every
    sweep says what it did even when the answer is nothing.
    """
    if deleted:
        logger.info("Retention: pruned %d %s row(s) [%s] older than %s",
                    deleted, kind, scope, cut.date().isoformat())
    else:
        logger.debug("Retention: nothing to prune for %s [%s]", kind, scope)
