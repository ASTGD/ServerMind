"""Compact, safe server context for Ally's chat prompts (Ally Brain Phase 3).

Builds a short plain-text profile of one server from data ServerAlly already stores —
latest metrics, last security scan, what our playbooks installed, recent AI activity.
Read-only DB queries only (never SSH at chat time). No secrets: no command outputs, no
access cards, no credentials — only titles, numbers, and the user's own past requests.
Best-effort: callers treat None/failure as "no profile" and continue.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import ServerMetric
from app.models.command_log import CommandLog
from app.models.playbook import Playbook, PlaybookRun
from app.models.security_scan import SecurityScan
from app.models.server import Server

logger = logging.getLogger(__name__)

_MAX_INSTALLED = 8
_MAX_COMMANDS = 5
_MAX_INPUT_CHARS = 80


def _age(ts: datetime | None) -> str:
    """Human age of a timestamp: 'just now', '5 min ago', '3 h ago', '2 d ago'."""
    if ts is None:
        return "unknown time"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    secs = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
    if secs < 90:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins} min ago"
    hours = mins // 60
    if hours < 48:
        return f"{hours} h ago"
    return f"{hours // 24} d ago"


async def build_server_profile(db: AsyncSession, server: Server) -> str | None:
    """The 'medical file' Ally sees for one server: health, security grade, installs,
    recent activity — each line with its age so the model can judge freshness."""
    lines: list[str] = []

    # Latest metrics snapshot (metrics_worker writes every 5 min when enabled).
    metric = (
        await db.execute(
            select(ServerMetric)
            .where(ServerMetric.server_id == server.id)
            .order_by(ServerMetric.recorded_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if metric:
        parts: list[str] = []
        if metric.cpu_percent is not None:
            parts.append(f"CPU {metric.cpu_percent:.0f}%")
        if metric.ram_percent is not None:
            ram = f"RAM {metric.ram_percent:.0f}%"
            if metric.ram_used_mb and metric.ram_total_mb:
                ram += f" ({metric.ram_used_mb}/{metric.ram_total_mb} MB)"
            parts.append(ram)
        if metric.disk_percent is not None:
            disk = f"disk {metric.disk_percent:.0f}%"
            if metric.disk_used_gb is not None and metric.disk_total_gb:
                disk += f" ({metric.disk_used_gb:.0f}/{metric.disk_total_gb:.0f} GB)"
            parts.append(disk)
        if metric.uptime_seconds:
            days = int(metric.uptime_seconds) // 86400
            parts.append(f"up {days} d" if days else "up <1 d")
        if parts:
            lines.append(f"Health ({_age(metric.recorded_at)}): " + ", ".join(parts))

    # Latest completed security scan — grade + severity tallies only.
    scan = (
        await db.execute(
            select(SecurityScan)
            .where(SecurityScan.server_id == server.id, SecurityScan.status == "completed")
            .order_by(SecurityScan.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if scan:
        lines.append(
            f"Security ({_age(scan.created_at)}): grade {scan.grade}, score {scan.score}/100 — "
            f"{scan.critical_count} critical, {scan.high_count} high, {scan.medium_count} medium issues"
        )

    # What our playbooks installed — titles only (never access cards or variables).
    rows = (
        await db.execute(
            select(PlaybookRun, Playbook)
            .join(Playbook, Playbook.id == PlaybookRun.playbook_id)
            .where(PlaybookRun.server_id == server.id, PlaybookRun.status == "success")
            .order_by(
                PlaybookRun.completed_at.desc().nullslast(),
                PlaybookRun.started_at.desc(),
            )
        )
    ).all()
    titles: list[str] = []
    seen: set[str] = set()
    for _run, pb in rows:
        if pb.slug in seen:
            continue
        seen.add(pb.slug)
        titles.append(pb.title)
        if len(titles) >= _MAX_INSTALLED:
            break
    if titles:
        lines.append("Installed by ServerAlly: " + " · ".join(titles))

    # Recent AI activity — the user's own past requests + outcome (never outputs).
    logs = (
        (
            await db.execute(
                select(CommandLog)
                .where(CommandLog.server_id == server.id)
                .order_by(CommandLog.created_at.desc())
                .limit(_MAX_COMMANDS)
            )
        )
        .scalars()
        .all()
    )
    if logs:
        acts: list[str] = []
        for log in logs:
            text = (log.user_input or "").strip().replace("\n", " ")
            if len(text) > _MAX_INPUT_CHARS:
                text = text[:_MAX_INPUT_CHARS] + "…"
            acts.append(f'"{text}" → {log.status or "unknown"} ({_age(log.created_at)})')
        lines.append("Recent AI activity (newest first): " + "; ".join(acts))

    return "\n".join(lines) if lines else None
