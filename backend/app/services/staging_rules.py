"""What a staging site must not inherit.

A staging copy is an ordinary site row — that is the design, and it is why Files, Logs,
Database, PHP and Deployments all work on it the day it exists. But four of the things an
ordinary site can do are, on a copy of a live site, incidents rather than features:

| If staging inherits it | What actually happens |
|---|---|
| **Cron jobs** | A copied WordPress fires its scheduled work: real customer emails, sent twice. A copied Laravel scheduler hits a payment API on a schedule nobody remembers setting up. |
| **Queue workers** | The same bug in different clothes — a staging worker connected to the live queue *consumes* jobs, so the live site's work silently disappears into a machine nobody is watching. |
| **Push-to-deploy** | The next push to the branch deploys to staging AND live, which is the opposite of what a staging site is for. |
| **On-call escalation** | Staging breaks constantly — that is its job — and a copy that pages somebody at 3am is how a team learns to ignore the pager for the live site too. |

Everything here is a rule about the SITE, in one place, because the cron page, the daemons
page, the deploy screen and the uptime worker all have to agree. Four copies of "is this
staging?" is four chances for one of them to say no.

**Nothing here is a lock the customer cannot open.** These are the defaults a staging site
starts with, and each refusal says what it is protecting and how to proceed anyway where
proceeding is reasonable. A staging site that genuinely needs a cron job is a real case; a
staging site that gets one *by inheritance*, without anyone deciding, is the incident.
"""
from __future__ import annotations

#: The value `sites.environment` carries for a copy.
STAGING = "staging"


def is_staging(site) -> bool:
    """Whether this site is a staging copy.

    Reads `environment`, never the domain. Somebody who called a site `staging.shop.com` by
    hand is not a copy of anything — the same distinction `site_service.is_staging` makes for
    promote, and for the same reason: a name is not a fact.
    """
    return getattr(site, "environment", "") == STAGING


# ── The four things it must not inherit ──────────────────────────────────────

def may_have_cron(site) -> tuple[bool, str]:
    """Scheduled jobs. Refused with the reason, not silently hidden."""
    if not is_staging(site):
        return True, ""
    return False, (
        "This is a staging copy, so it starts with no scheduled jobs. A copied site running "
        "the live site's schedule sends real emails to real customers and calls real APIs — "
        "twice, because the live site is doing it too. Add a job here only if this copy "
        "genuinely needs one of its own."
    )


def may_have_daemons(site) -> tuple[bool, str]:
    """Always-running processes — queue workers above all."""
    if not is_staging(site):
        return True, ""
    return False, (
        "This is a staging copy, so it starts with nothing running in the background. A "
        "queue worker here would take jobs off the live queue and do them where nobody is "
        "looking — the live site's work would simply stop happening, with no error anywhere."
    )


def may_auto_deploy(site) -> tuple[bool, str]:
    """Push-to-deploy. Off on a copy, and the webhook secret is never carried over."""
    if not is_staging(site):
        return True, ""
    return False, (
        "Push-to-deploy is off on a staging copy. With it on, one push would deploy to both "
        "this copy and the live site, which is the opposite of what a staging site is for. "
        "Deploy here by hand, then promote when you are happy."
    )


def may_escalate(site) -> bool:
    """Whether a failure here should open an on-call incident.

    **Staging still gets a monitor** — it is deliberately not "no monitor at all", because the
    Sites list would then read *"Not checked"* for it, and a row that says nothing is worse
    than a row that says down. The customer should be able to see their staging copy is
    broken. They should not be woken up about it.
    """
    return not is_staging(site)
