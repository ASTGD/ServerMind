"""The escalation worker — climbs the ladder until somebody answers.

Runs every minute. For each open incident whose next action is due, it asks the pure
``escalation_service.decide`` what to do, sends that one page, and writes back where it got
to. All the judgement lives in ``decide``; this module only does the parts that need a
database and a network.

The query is the safety mechanism: an incident is only picked up while its status is
``open`` **and** it has a due ``next_action_at``. Acknowledging or resolving changes both,
so those actions stop the paging within the same instant they happen — there is no tick in
which an acknowledged incident can page again.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.escalation import STATUS_OPEN, EscalationPolicy, Incident
from app.models.server import Server
from app.services import escalation_service as esc
from app.services import incident_service, paging_service

logger = logging.getLogger(__name__)

# How many incidents one tick will work through. A cap so a pathological backlog degrades
# into "a bit late" rather than a tick that never finishes.
_BATCH = 50


def app_url() -> str:
    """The public frontend origin for the acknowledge link. Same source as the digest."""
    return (settings.APP_BASE_URL
            or (settings.ALLOWED_ORIGINS[0] if settings.ALLOWED_ORIGINS else "")).rstrip("/")


def build_page(incident: Incident, server_name: str | None, ack_token: str | None,
               attempt: int, total: int) -> tuple[str, str]:
    """The message a human actually receives, as ``(subject, body)``.

    Written to be read on a phone screen at 3am: what broke, where, and the one link that
    makes it stop. The "N of M" tells the reader whether more people are about to be woken,
    which is the thing they most need to know before deciding to act or hand off.
    """
    # Name the server, but never twice. Detectors build their own titles, and a monitor is
    # usually named after the server it watches — so "Shop is down" on a server called
    # "Shop" would read "Shop is down on Shop". Every character also costs money in an SMS.
    where = ""
    if server_name and server_name.lower() not in incident.title.lower():
        where = f" on {server_name}"
    subject = f"[{incident.severity.upper()}] {incident.title}{where}"

    lines = [incident.title + where]
    if incident.message:
        lines += ["", incident.message.strip()]
    lines += ["", f"Alert {attempt} of at most {total}."]
    if ack_token:
        lines += ["", f"Stop these alerts: {app_url()}/ack/{ack_token}"]
    lines += [f"Open in ServerAlly: {app_url()}/incidents"]
    return subject, "\n".join(lines)


async def _due_incidents(db: AsyncSession, now: datetime) -> list[Incident]:
    return list((await db.execute(
        select(Incident).where(
            Incident.status == STATUS_OPEN,
            Incident.next_action_at.isnot(None),
            Incident.next_action_at <= now,
        ).order_by(Incident.next_action_at).limit(_BATCH)
    )).scalars().all())


async def process_incident(db: AsyncSession, incident: Incident, now: datetime) -> bool:
    """Advance one incident by at most one page. Returns True if a page was sent."""
    policy = await db.get(EscalationPolicy, incident.policy_id) if incident.policy_id else None
    if policy is None or not policy.is_active:
        # The policy was deleted or switched off while this was escalating. Stop paging —
        # turning a policy off has to mean the paging stops, not that in-flight incidents
        # keep going on the old rules.
        logger.info("Incident %s has no active policy — stopping escalation", incident.id)
        incident.next_action_at = None
        await db.commit()
        return False

    steps = await incident_service.steps_for(db, policy)
    decision = esc.decide(
        steps, incident.created_at, now,
        step_index=incident.step_index, repeats_done=incident.repeats_done,
        repeat_minutes=policy.repeat_minutes, max_repeats=policy.max_repeats,
        last_notified_at=incident.last_notified_at,
    )

    sent = False
    if decision.fire is not None:
        server_name = None
        if incident.server_id:
            server = await db.get(Server, incident.server_id)
            server_name = server.name if server else None

        attempt = incident.notifications_sent + 1
        subject, body = build_page(
            incident, server_name, incident_service.read_ack_token(incident),
            attempt, esc.total_notifications(steps, policy.max_repeats),
        )
        ok, detail = await paging_service.deliver(
            db, incident.user_id, decision.fire.channel, decision.fire.target, subject, body,
        )
        # Advance regardless of the result. A dead channel must not park the ladder on its
        # own rung forever — the next step exists precisely so a failure still reaches
        # someone. The failure is logged, and the count only rises on a real delivery.
        if ok:
            incident.notifications_sent = attempt
            incident.last_notified_at = now
            sent = True
        else:
            logger.warning("Incident %s: %s step failed (%s)", incident.id,
                           decision.fire.channel, detail)
            incident.last_notified_at = now

    incident.step_index = decision.step_index
    incident.repeats_done = decision.repeats_done
    incident.next_action_at = decision.next_at
    await db.commit()
    return sent


async def run_escalations(now: datetime | None = None) -> int:
    """One tick. Returns how many pages were delivered."""
    now = now or datetime.now(tz=timezone.utc)
    async with AsyncSessionLocal() as db:
        due = await _due_incidents(db, now)
        if not due:
            return 0
        logger.info("Escalation tick: %d incident(s) due", len(due))

        delivered = 0
        for incident in due:
            try:
                if await process_incident(db, incident, now):
                    delivered += 1
            except Exception as exc:  # noqa: BLE001 — one incident must not stop the rest
                logger.warning("Escalation failed for incident %s: %s", incident.id, exc)
                await db.rollback()
        return delivered
