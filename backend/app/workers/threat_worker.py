"""Proactive threat-monitoring worker.

Periodically runs the read-only threat (IOC) scan on every SSH server, stores the
result, and — when a server NEWLY looks compromised (its verdict worsened into
at_risk/compromised since the last scan) — raises an in-app notification and a
best-effort email so the owner finds out before Google does. Detection only; any
fix is still the user's decision (offered as an approved mission).
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.notification import Notification
from app.models.server import Server
from app.models.threat_scan import ThreatScan
from app.models.user import User
from app.services import threat_service
from app.services import incident_service
from app.services.notification_service import send_email

logger = logging.getLogger(__name__)

# Verdicts that warrant proactively alerting the user.
_ALERTING = {"at_risk", "compromised"}


async def scan_all_servers() -> None:
    """APScheduler entry point — scan every SSH server for compromise."""
    async with AsyncSessionLocal() as db:
        servers = (
            await db.execute(select(Server).where(Server.connection_type == "ssh"))
        ).scalars().all()

    logger.info("Threat scan run: %d SSH servers", len(servers))
    for server in servers:
        try:
            await _scan_and_alert(server)
        except Exception as exc:  # noqa: BLE001 — one server must not stop the sweep
            logger.debug("Threat scan skipped for %s (%s): %s", server.name, server.id, exc)


async def _scan_and_alert(server: Server) -> None:
    # The verdict of the most recent PRIOR scan — so we only alert on a NEW problem.
    async with AsyncSessionLocal() as db:
        prev = (
            await db.execute(
                select(ThreatScan.verdict)
                .where(ThreatScan.server_id == server.id)
                .order_by(ThreatScan.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    result = await threat_service.run_scan(server)
    if result["status"] != "completed":
        return  # unreachable / unsupported — don't alert or store a noisy failure

    counts = result["counts"]
    async with AsyncSessionLocal() as db:
        scan = ThreatScan(
            server_id=server.id, user_id=server.user_id, verdict=result["verdict"],
            status=result["status"], error=result.get("error"),
            duration_ms=result.get("duration_ms"),
            critical_count=counts.get("critical", 0), high_count=counts.get("high", 0),
            medium_count=counts.get("medium", 0), low_count=counts.get("low", 0),
            pass_count=counts.get("pass", 0), info_count=counts.get("info", 0),
            findings=json.dumps(result["findings"]),
        )
        db.add(scan)
        await db.commit()

    # Alert only when the verdict is bad AND it wasn't already bad last time — so the
    # user gets one clear heads-up per new incident, not a nag every cycle.
    if result["verdict"] in _ALERTING and prev not in _ALERTING:
        await _notify(server, result)
    elif result["verdict"] not in _ALERTING and prev in _ALERTING:
        # The server came back clean — close the incident rather than leaving a solved
        # problem paging (or sitting) in the owner's list.
        try:
            async with AsyncSessionLocal() as db:
                await incident_service.resolve_key(db, server.user_id, f"threat:{server.id}")
        except Exception:  # noqa: BLE001
            logger.warning("Threat incident close failed for %s", server.id, exc_info=True)


async def _notify(server: Server, result: dict) -> None:
    top = [f for f in result["findings"] if f["severity"] in ("critical", "high")]
    headline = top[0]["title"] if top else "Suspicious activity"
    verdict_word = "may be compromised" if result["verdict"] == "compromised" else "may be at risk"

    async with AsyncSessionLocal() as db:
        db.add(Notification(
            user_id=server.user_id, type="threat", status=result["verdict"],
            title=f"Security alert: {server.name} {verdict_word}",
            body=f"{headline} — open the server's Security tab to review.",
            server_id=server.id,
        ))
        await db.commit()

    # A compromised server is the strongest case for waking somebody. If an on-call policy
    # covers it, the ladder replaces the single email — otherwise the email below still goes,
    # so nothing gets quieter than before.
    try:
        async with AsyncSessionLocal() as db:
            fresh = await db.get(Server, server.id)
            raised = await incident_service.raise_for(
                db, user_id=server.user_id, server=fresh, source="threat",
                dedup_key=f"threat:{server.id}",
                title=f"{server.name} {verdict_word}",
                message=(f"{headline}\n\n" + "\n".join(
                    f"- [{f['severity']}] {f['title']}: {f['detail'] or ''}" for f in top[:6]
                ) + "\n\nServerAlly did NOT change anything — detection only. Open the "
                    "server's Security tab to respond."),
                severity="critical" if result["verdict"] == "compromised" else "high",
            )
            if raised is not None:
                return
    except Exception:  # noqa: BLE001 — escalation must not swallow the email fallback
        logger.warning("Threat escalation failed for %s", server.id, exc_info=True)

    try:
        async with AsyncSessionLocal() as db:
            owner = await db.get(User, server.user_id)
        if owner and owner.email:
            lines = "\n".join(f"  - [{f['severity']}] {f['title']}: {f['detail'] or ''}" for f in top[:6])
            await send_email(
                owner.email,
                f"[ServerAlly] Security alert: {server.name} {verdict_word}",
                f"ServerAlly's automatic threat scan found signs that {server.name} "
                f"{verdict_word}.\n\nWhat we found:\n{lines}\n\n"
                "Open ServerAlly → the server → Security to review the details and let "
                "Ally help you respond. (We did NOT change anything — detection only.)\n",
            )
    except Exception:  # noqa: BLE001 — email is best-effort
        logger.warning("Threat alert email failed for %s", server.id, exc_info=True)
