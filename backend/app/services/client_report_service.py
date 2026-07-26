"""Client reports — "here is what we did for you this month", for an agency to send on.

**Deliberately deterministic — no AI.** An agency may send this to a paying client every
month, so it must be reproducible, free to generate, and impossible to hallucinate. Every
number comes from a table we already fill: uptime checks, security scans, threat scans,
backup runs, missions, and the command log.

It answers the three questions a client actually has:

1. *Was my site up?* — uptime %, and how many outages.
2. *Is it safe?* — security grade, threat verdict, whether backups ran.
3. *What did you actually do for me?* — completed work, in plain language.

The AI narrative reports (``explain_incident`` / ``explain_server_report``) remain the
richer, per-incident story. This is the routine, zero-cost monthly one.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models.backup import Backup, BackupRun
from app.models.command_log import CommandLog
from app.models.mission import Mission
from app.models.security_scan import SecurityScan
from app.models.server import Server
from app.models.threat_scan import ThreatScan
from app.models.uptime import UptimeCheck, UptimeMonitor
from app.services import uptime_service

logger = logging.getLogger(__name__)

DEFAULT_PERIOD_DAYS = 30


def period_bounds(days: int = DEFAULT_PERIOD_DAYS, now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(tz=timezone.utc)
    return now - timedelta(days=days), now


def _verdict(uptime: float | None, security_grade: str | None, threat: str | None,
             backups_ok: bool | None) -> tuple[str, str]:
    """(tone, headline) — the one line a client reads first.

    Ordered by what actually harms them: a compromise first, then downtime, then posture.
    """
    if threat in ("compromised", "at_risk"):
        return "bad", "We found a security problem and acted on it"
    if uptime is not None and uptime < 99.0:
        return "warn", "Your site had some downtime this period"
    if backups_ok is False:
        return "warn", "Everything ran well, but backups need attention"
    if security_grade in ("D", "E", "F"):
        return "warn", "Your site stayed online; security hardening is recommended"
    return "good", "Everything ran smoothly this period"


async def build(db, server: Server, days: int = DEFAULT_PERIOD_DAYS) -> dict:
    """Assemble the report for one server over the last ``days``. Never raises."""
    since, until = period_bounds(days)

    # ── Uptime ───────────────────────────────────────────────────────────────
    monitors = (await db.execute(
        select(UptimeMonitor).where(UptimeMonitor.server_id == server.id)
    )).scalars().all()
    uptime_pct: float | None = None
    outages = 0
    monitor_lines: list[dict] = []
    if monitors:
        ids = [m.id for m in monitors]
        rows = (await db.execute(
            select(
                UptimeCheck.monitor_id,
                func.count().label("total"),
                func.count().filter(UptimeCheck.status == "up").label("up"),
                func.count().filter(UptimeCheck.status == "down").label("down"),
            )
            .where(UptimeCheck.monitor_id.in_(ids), UptimeCheck.checked_at >= since)
            .group_by(UptimeCheck.monitor_id)
        )).all()
        stats = {r[0]: (r[1], r[2], r[3]) for r in rows}
        total_checks = sum(s[0] for s in stats.values())
        total_up = sum(s[1] for s in stats.values())
        outages = sum(s[2] for s in stats.values())
        if total_checks:
            uptime_pct = uptime_service.uptime_percentage(total_up, total_checks)
        for m in monitors:
            t, u, _d = stats.get(m.id, (0, 0, 0))
            monitor_lines.append({
                "name": m.name,
                "uptime": uptime_service.uptime_percentage(u, t),
                "checked": t,
            })

    # ── Security & threats (latest in period) ────────────────────────────────
    scan = (await db.execute(
        select(SecurityScan).where(SecurityScan.server_id == server.id)
        .order_by(SecurityScan.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    threat = (await db.execute(
        select(ThreatScan).where(ThreatScan.server_id == server.id)
        .order_by(ThreatScan.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    # ── Backups ──────────────────────────────────────────────────────────────
    backup_rows = (await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(BackupRun.status == "success").label("ok"),
        )
        .select_from(BackupRun)
        .where(BackupRun.server_id == server.id, BackupRun.action == "backup",
               BackupRun.started_at >= since)
    )).one()
    backups_total, backups_ok_count = int(backup_rows[0] or 0), int(backup_rows[1] or 0)
    has_jobs = bool((await db.execute(
        select(func.count()).select_from(Backup).where(Backup.server_id == server.id)
    )).scalar())
    backups_ok = None if not has_jobs else (backups_total > 0 and backups_ok_count == backups_total)

    # ── Work done ────────────────────────────────────────────────────────────
    missions = (await db.execute(
        select(Mission).where(Mission.server_id == server.id, Mission.created_at >= since)
        .order_by(Mission.created_at.desc()).limit(50)
    )).scalars().all()
    done = [
        {"goal": (m.goal or "").strip()[:180], "verified": bool(m.verified)}
        for m in missions if m.status == "completed"
    ]
    commands_run = int((await db.execute(
        select(func.count()).select_from(CommandLog)
        .where(CommandLog.server_id == server.id, CommandLog.created_at >= since,
               CommandLog.status == "success")
    )).scalar() or 0)

    grade = scan.grade if scan else None
    verdict_tone, headline = _verdict(uptime_pct, grade, threat.verdict if threat else None, backups_ok)

    return {
        "server_name": server.name,
        "period_days": days,
        "period_start": since.date().isoformat(),
        "period_end": until.date().isoformat(),
        "tone": verdict_tone,
        "headline": headline,
        "uptime": {
            "percentage": uptime_pct,
            "outages": outages,
            "monitors": monitor_lines,
            "monitored": bool(monitors),
        },
        "security": {
            "grade": grade,
            "score": scan.score if scan else None,
            "scanned_at": scan.created_at.date().isoformat() if scan else None,
            "threat_verdict": threat.verdict if threat else None,
        },
        "backups": {
            "configured": has_jobs,
            "runs": backups_total,
            "successful": backups_ok_count,
            "healthy": backups_ok,
        },
        "work": {
            "completed": done,
            "completed_count": len(done),
            "commands_run": commands_run,
        },
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def plain_summary(report: dict) -> list[str]:
    """The report as a few plain sentences — used in the email body and the PDF intro.

    Written for someone who does not run servers: no grades without explanation, no jargon.
    """
    lines: list[str] = []
    up = report["uptime"]
    if up["monitored"] and up["percentage"] is not None:
        if up["outages"] == 0:
            lines.append(f"Your site was online {up['percentage']}% of the time, with no outages.")
        else:
            lines.append(
                f"Your site was online {up['percentage']}% of the time. "
                f"We recorded {up['outages']} failed check(s) and looked into them."
            )
    else:
        lines.append("Uptime checks are not set up for this server yet.")

    sec = report["security"]
    if sec["grade"]:
        lines.append(
            f"The last security review scored {sec['score']} out of 100 (grade {sec['grade']})."
        )
    if sec["threat_verdict"] in ("compromised", "at_risk"):
        lines.append("We found signs of a security problem and dealt with it — details below.")
    elif sec["threat_verdict"] == "clean":
        lines.append("A malware and intrusion scan found nothing suspicious.")

    b = report["backups"]
    if not b["configured"]:
        lines.append("No backups are configured for this server yet — worth setting up.")
    elif b["healthy"]:
        lines.append(f"All {b['runs']} backup(s) completed successfully.")
    elif b["runs"] == 0:
        lines.append("Backups are configured but none ran in this period.")
    else:
        lines.append(f"{b['successful']} of {b['runs']} backups completed — the rest need attention.")

    work = report["work"]
    if work["completed_count"]:
        lines.append(f"We completed {work['completed_count']} piece(s) of work on this server.")
    return lines
