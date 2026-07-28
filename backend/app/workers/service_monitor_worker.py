"""Service sweep — notice a stopped service, tell someone, optionally restart it.

Same announce-on-transition rule as the uptime and threat workers: one message when a
service stops, one when it comes back. A service down all afternoon does not send an
email every ninety seconds.

One probe per SERVER, not per monitor. A box with eight watched services is one SSH
round trip, not eight — the probe is built to report them all at once, and doing it any
other way would make the sweep's cost scale with how carefully someone watches.

Restarting is the only thing here that changes a server, and it is bounded by
``service_monitor_service.restart_decision``. When that bound is hit the monitor is
marked ``gave_up`` and the owner is told plainly, because a crash-loop that quietly
keeps restarting looks healthier than it is.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.server import Server
from app.models.service_monitor import ServiceMonitor
from app.services import (connection_manager, incident_service, notification_service,
                          service_monitor_service as svc, webhook_service)

logger = logging.getLogger(__name__)

_CONCURRENCY = 6          # servers probed at once
_SSH_TIMEOUT = 25


async def _announce(db, monitor: ServiceMonitor, server: Server, *,
                    went_down: bool, restarted: bool = False,
                    gave_up: bool = False) -> None:
    """Tell the owner. Best-effort — a failed email must never break the sweep."""
    name = f"{monitor.label} on {server.name}"
    if gave_up:
        subject = f"🔴 {name} keeps stopping"
        body = (f"{monitor.label} on {server.name} has stopped repeatedly and ServerAlly "
                f"has stopped trying to restart it.\n\n{monitor.last_error or ''}\n\n"
                "Restarting it again would just hide the problem — something is making it "
                "crash. Ask Ally to investigate.")
    elif went_down and restarted:
        subject = f"🟡 {name} stopped — restarted automatically"
        body = (f"{monitor.label} on {server.name} had stopped. ServerAlly restarted it "
                "and confirmed it is running again.\n\nNothing to do — this is a heads-up.")
    elif went_down:
        subject = f"🔴 {name} has stopped"
        body = (f"{monitor.label} on {server.name} is not running.\n\n"
                f"{monitor.last_error or ''}\n\nAsk Ally to look at it, or start it yourself.")
    else:
        subject = f"✅ {name} is running again"
        body = f"{monitor.label} on {server.name} is back up."

    try:
        owner_email = await _owner_email(db, monitor.user_id)
        if owner_email:
            await notification_service.send_email(owner_email, subject, body)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Service alert email for %s failed: %s", monitor.id, exc)

    try:
        await webhook_service.emit(
            db, monitor.user_id,
            "service.down" if went_down else "service.up",
            {"server": server.name, "service": monitor.label, "unit": monitor.unit,
             "status": monitor.current_status, "restarted": restarted,
             "gave_up": gave_up, "detail": monitor.last_error},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Service webhook for %s failed: %s", monitor.id, exc)


async def _owner_email(db, user_id) -> str | None:
    from app.models.user import User
    row = await db.execute(select(User.email).where(User.id == user_id))
    return row.scalar_one_or_none()


async def _sweep_server(server_id) -> None:
    """Probe every active monitor on one server in a single round trip."""
    async with AsyncSessionLocal() as db:
        server = await db.get(Server, server_id)
        if not server or server.connection_type != "ssh":
            return
        monitors = (await db.execute(
            select(ServiceMonitor).where(ServiceMonitor.server_id == server_id,
                                         ServiceMonitor.is_active.is_(True))
        )).scalars().all()
        if not monitors:
            return

        units = [m.unit for m in monitors]
        try:
            out, _err, _code = await asyncio.wait_for(
                connection_manager.execute(server, svc.build_probe(units)),
                timeout=_SSH_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            # An unreachable server is the metrics worker's job to report. Leaving the
            # states untouched is deliberate: we learned nothing, so we claim nothing.
            logger.info("Service probe on %s failed: %s", server.name, exc)
            return

        states = svc.parse_probe(out or "", units)
        now = datetime.now(timezone.utc)

        for m in monitors:
            st = states.get(m.unit)
            if st is None:
                continue
            status, failures, changed = svc.next_state(
                current_status=m.current_status,
                consecutive_failures=m.consecutive_failures,
                ok=st.ok, failure_threshold=m.failure_threshold)

            m.last_checked, m.last_state = now, st.state
            m.consecutive_failures = failures
            m.last_error = None if st.ok else (st.detail or "The service is not running.")
            went_down = changed and status == "down"
            came_back = changed and status == "up"
            if changed:
                m.current_status, m.last_status_change = status, now
            else:
                m.current_status = status

            restarted = gave_up = False
            if status == "down":
                decision = svc.restart_decision(
                    auto_restart=m.auto_restart, status=status,
                    restart_count=m.restart_count,
                    window_started=m.restart_window_started,
                    max_restarts=m.max_restarts,
                    restart_window_seconds=m.restart_window_seconds, now=now)

                if decision.should_restart:
                    if (m.restart_window_started is None
                            or (now - m.restart_window_started).total_seconds()
                            > max(60, m.restart_window_seconds)):
                        m.restart_window_started, m.restart_count = now, 0
                    m.restart_count += 1
                    m.last_restart_at = now
                    try:
                        rout, _e, _c = await asyncio.wait_for(
                            connection_manager.execute(server, svc.build_restart(m.unit)),
                            timeout=_SSH_TIMEOUT)
                        restarted = svc.restart_worked(rout or "")
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Restart of %s on %s failed: %s",
                                       m.unit, server.name, exc)
                        restarted = False
                    if restarted:
                        m.current_status, m.consecutive_failures = "up", 0
                        m.last_error = None
                elif decision.give_up and not m.gave_up:
                    m.gave_up, gave_up = True, True
                    m.last_error = decision.reason

            if came_back:
                # A clean recovery closes the book: the next failure starts a fresh window
                # rather than inheriting a count from an incident that is over.
                m.restart_count, m.restart_window_started, m.gave_up = 0, None, False

            await db.commit()

            if gave_up or went_down or came_back:
                await _announce(db, m, server, went_down=went_down or gave_up,
                                restarted=restarted, gave_up=gave_up)
            if went_down and not restarted and not gave_up:
                try:
                    await incident_service.raise_for(
                        db, user_id=m.user_id, server=server, source="service",
                        dedup_key=f"service:{m.id}",
                        title=f"{m.label} stopped on {server.name}",
                        message=(m.last_error or "The service is not running.")
                                + f"\n\nService: {m.unit} on {server.name}",
                        severity="critical")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Service escalation for %s failed: %s", m.id, exc)


async def sweep() -> None:
    """Check every server that has active service monitors."""
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(ServiceMonitor.server_id)
            .where(ServiceMonitor.is_active.is_(True)).distinct())
        server_ids = [r[0] for r in rows.all()]

    if not server_ids:
        return
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def one(sid):
        async with sem:
            try:
                await _sweep_server(sid)
            except Exception as exc:  # noqa: BLE001 — one server must not stop the sweep
                logger.warning("Service sweep for %s failed: %s", sid, exc)

    await asyncio.gather(*(one(s) for s in server_ids))
    logger.info("Service sweep finished across %d server(s)", len(server_ids))
