"""Telling someone that a site deployed — Ploi's per-site Notifications.

**This is a subscription, not a second notification system.** The destination is a channel
the customer already made and verified, and the sending is `channel_service.deliver`, so
there is still exactly one implementation of "talk to Slack". Ploi's other half — a pair of
raw webhook URLs POSTed per site — is deliberately NOT copied: we already have signed,
retried, delivery-logged webhooks with an event catalogue, so deploy became two more events
in that catalogue rather than an unsigned second path that nobody could audit.

Two rules shape everything here.

**A failure to notify must never fail the deploy.** The deploy is the important thing; being
told about it is a side effect. So every send is best-effort, the outcome is recorded on the
row, and the screen reads it back — the same honesty as a notification channel that says
"Not tested yet" until a message has actually arrived.

**The message says what happened, to which site, and where to look.** A notification that
only says "deploy failed" makes somebody open the app to find out which of their sites it
was, which is the work it was supposed to save.
"""
from __future__ import annotations

from app.models.deployment import DEPLOY_EVENTS


class DeployNotifyError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def clean_events(values) -> list[str]:
    """The events to be told about, or a refusal naming the real ones.

    An empty set is refused rather than saved: a rule that fires on nothing is a rule that
    looks configured and does nothing, which is worse than not having made one — the
    customer believes they are covered.
    """
    if isinstance(values, str):
        values = [values]
    seen = [str(v).strip().lower() for v in (values or [])]
    unknown = [v for v in seen if v and v not in DEPLOY_EVENTS]
    if unknown:
        raise DeployNotifyError(
            f"'{unknown[0]}' is not a deploy event. Choose from: "
            + ", ".join(DEPLOY_EVENTS) + "."
        )
    kept = [e for e in DEPLOY_EVENTS if e in seen]     # a stable, meaningful order
    if not kept:
        raise DeployNotifyError(
            "Choose at least one thing to be told about, or this rule would never send "
            "anything while looking like it was set up."
        )
    return kept


def wants(rule, event: str) -> bool:
    """Whether this rule should fire for this event.

    Fails closed at every ambiguity: switched off, no channel to send to, or an events list
    that is missing or malformed all mean "do not send". Being silent is recoverable; sending
    to the wrong place, or crashing a deploy, is not.
    """
    if rule is None or not getattr(rule, "is_active", False):
        return False
    if getattr(rule, "channel_id", None) is None:
        return False
    events = getattr(rule, "events", None)
    if not isinstance(events, (list, tuple)):
        return False
    return event in events


#: What a customer sees, per event. Written as the sentence they will read on their phone.
_HEADLINE = {
    "started": "Deploy started",
    "completed": "Deploy finished",
    "failed": "Deploy FAILED",
}


def build_message(*, event: str, site: str, repo: str, branch: str,
                  release: str | None = None, failed_step: str | None = None,
                  trigger: str = "manual") -> tuple[str, str]:
    """The subject and body for one deploy event.

    Names the SITE first, because a message that only says "deploy failed" makes somebody
    open the app to find out which of their sites it was — the work it was meant to save.
    """
    head = _HEADLINE.get(event, "Deploy")
    subject = f"{head} — {site}"

    lines = [f"{repo} ({branch})"]
    if release:
        lines.append(f"Release {release}")
    if event == "failed" and failed_step:
        # The question actually asked is "which step", so it leads.
        lines.append(f"Stopped at: {failed_step}")
    lines.append("Started by a push to the repository." if trigger == "push"
                 else "Started by hand.")
    return subject, "\n".join(lines)


def summarise(rule) -> str:
    """One line for the screen: what this rule does, in words rather than field names."""
    events = [e for e in DEPLOY_EVENTS if e in (getattr(rule, "events", None) or [])]
    if not events:
        return "Nothing selected, so this sends nothing."
    if len(events) == len(DEPLOY_EVENTS):
        return "Every deploy — started, finished and failed."
    names = {"started": "when one starts", "completed": "when one finishes",
             "failed": "when one fails"}
    parts = [names[e] for e in events]
    if len(parts) == 1:
        return f"Only {parts[0]}."
    return f"{parts[0].capitalize()}, and {parts[-1]}." if len(parts) == 2 else (
        ", ".join(parts[:-1]) + f", and {parts[-1]}.")


# ── Sending ──────────────────────────────────────────────────────────────────

async def notify(target_id, event: str, *, user_id, site: str, repo: str, branch: str,
                 release: str | None = None, failed_step: str | None = None,
                 trigger: str = "manual") -> int:
    """Tell everyone who asked about this event. Returns how many were told.

    **Never raises.** A deploy that succeeded must not be reported as failed because Slack
    was down, and a deploy that failed must not lose its own error behind a second one. Every
    outcome is written onto the rule instead, so the screen can say what really happened.
    """
    import logging

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.deployment import DeployNotification
    from app.models.notification_channel import NotificationChannel
    from app.services import channel_service, webhook_service

    log = logging.getLogger(__name__)
    sent = 0
    try:
        subject, body = build_message(event=event, site=site, repo=repo, branch=branch,
                                      release=release, failed_step=failed_step,
                                      trigger=trigger)
        async with AsyncSessionLocal() as db:
            rules = (await db.execute(
                select(DeployNotification).where(DeployNotification.target_id == target_id)
            )).scalars().all()
            for rule in rules:
                if not wants(rule, event):
                    continue
                channel = await db.get(NotificationChannel, rule.channel_id)
                if channel is None or not channel.is_active:
                    continue
                try:
                    await channel_service.deliver(db, channel, subject=subject, body=body)
                    rule.last_sent_at = _now()
                    rule.last_error = None
                    sent += 1
                except Exception as exc:  # noqa: BLE001 — the outcome belongs on the row
                    rule.last_error = str(exc)[:500]
                    log.info("deploy notification failed for target %s: %s", target_id, exc)
            await db.commit()

            # The other half of Ploi's tab, done through the webhook system we already have
            # — signed, retried and logged, rather than a raw POST nobody can verify.
            #
            # Emitted for the deploy's OWNER, independently of whether any channel rule
            # exists: a customer with a webhook endpoint and no Slack rule still asked to be
            # told. Deriving the owner from the rules made the webhook silently depend on an
            # unrelated setting.
            if user_id is not None:
                await webhook_service.emit(
                    db, user_id,
                    "deploy.started" if event == "started" else "deploy.finished",
                    {"site": site, "repo": repo, "branch": branch, "event": event,
                     "release": release, "failed_step": failed_step, "trigger": trigger})
    except Exception:  # noqa: BLE001 — see the docstring: this can never break a deploy
        log.exception("could not send deploy notifications for target %s", target_id)
    return sent


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
