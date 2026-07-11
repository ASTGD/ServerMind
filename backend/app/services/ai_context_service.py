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


# Fleet health (Ally Brain Phase 4) — one short health string per server so the fleet
# chat can answer "which server needs attention?" with real numbers. Bounded: only the
# first _MAX_FLEET_HEALTH servers get a health line (the server list itself is complete).
_MAX_FLEET_HEALTH = 30


async def build_fleet_health(db: AsyncSession, servers: list[Server]) -> dict[str, str]:
    """Map of server-id (str) → one-line health summary for the fleet prompt.

    Two DISTINCT ON queries total (latest metric + latest completed security scan per
    server) — never per-server queries, never SSH. Servers with no data are simply
    absent from the map.
    """
    ids = [s.id for s in servers[:_MAX_FLEET_HEALTH]]
    if not ids:
        return {}

    metrics = (
        (
            await db.execute(
                select(ServerMetric)
                .where(ServerMetric.server_id.in_(ids))
                .distinct(ServerMetric.server_id)
                .order_by(ServerMetric.server_id, ServerMetric.recorded_at.desc())
            )
        )
        .scalars()
        .all()
    )
    scans = (
        (
            await db.execute(
                select(SecurityScan)
                .where(SecurityScan.server_id.in_(ids), SecurityScan.status == "completed")
                .distinct(SecurityScan.server_id)
                .order_by(SecurityScan.server_id, SecurityScan.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    # Installed software (titles only) — so fleet chat KNOWS what's already on each box
    # ("install WordPress on X" → "X already has WordPress"). One query for the fleet.
    runs = (
        await db.execute(
            select(PlaybookRun.server_id, Playbook.title, Playbook.slug)
            .join(Playbook, Playbook.id == PlaybookRun.playbook_id)
            .where(PlaybookRun.server_id.in_(ids), PlaybookRun.status == "success")
            .order_by(PlaybookRun.completed_at.desc().nullslast())
        )
    ).all()
    by_metric = {m.server_id: m for m in metrics}
    by_scan = {s.server_id: s for s in scans}
    by_installed: dict = {}
    for sid, title, slug in runs:
        seen = by_installed.setdefault(sid, {"slugs": set(), "titles": []})
        if slug not in seen["slugs"] and len(seen["titles"]) < 4:
            seen["slugs"].add(slug)
            seen["titles"].append(title)

    health: dict[str, str] = {}
    for sid in ids:
        parts: list[str] = []
        m = by_metric.get(sid)
        if m:
            nums: list[str] = []
            if m.cpu_percent is not None:
                nums.append(f"CPU {m.cpu_percent:.0f}%")
            if m.ram_percent is not None:
                nums.append(f"RAM {m.ram_percent:.0f}%")
            if m.disk_percent is not None:
                nums.append(f"disk {m.disk_percent:.0f}%")
            if nums:
                parts.append(f"health ({_age(m.recorded_at)}): " + ", ".join(nums))
        scan = by_scan.get(sid)
        if scan:
            sec = f"security ({_age(scan.created_at)}): grade {scan.grade}"
            if scan.critical_count or scan.high_count:
                sec += f" ({scan.critical_count} critical, {scan.high_count} high)"
            parts.append(sec)
        installed = by_installed.get(sid)
        if installed and installed["titles"]:
            parts.append("installed: " + " · ".join(installed["titles"]))
        if parts:
            health[str(sid)] = "; ".join(parts)
    return health


# ── Full chat-context assembly (shared by the live WS handler + the Dev Door) ──────
#
# The exact context Ally sees before planning a chat message: the server profile,
# what Ally remembers, the autonomy mode, the OTHER reachable servers (with health),
# a read-only file scout, a live snapshot, and the skill menu. Extracted here so the
# WebSocket chat path and the dev dry-run build byte-identical prompts — the Dev Door's
# whole point is "see exactly what Ally sees". Best-effort throughout (a context failure
# degrades to None, exactly as the inline version did — it never blocks the chat).

from dataclasses import dataclass


@dataclass
class ChatContext:
    """Everything plan_commands takes as per-message context (each block optional)."""

    server_profile: str | None = None
    memories: str | None = None
    ally_mode: str | None = None
    other_servers: str | None = None
    scout: str | None = None
    live_snapshot: str | None = None
    skill_menu: str | None = None


async def build_chat_context(
    server: Server,
    user_input: str,
    *,
    acting_user_id: str | None = None,
    skill=None,  # skill_service.Skill | None
    want_scout: bool = True,
    want_live: bool = True,
) -> ChatContext:
    """Assemble the per-message chat context for ``server`` / ``user_input``.

    Mirrors the assembly that used to live inline in websocket/terminal.py so both the
    live chat and the Dev Door dry-run produce the same prompt. ``want_scout`` /
    ``want_live`` let a caller skip the two SSH probes. Owns its own DB sessions.
    """
    import uuid

    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services import (
        live_look_service,
        memory_service,
        scout_service,
        skill_service,
        team_service,
    )

    ctx = ChatContext(
        skill_menu=skill_service.menu_for(server.os_type) if skill is None else None,
    )
    owner_id = acting_user_id or server.user_id
    other_roster: list[Server] = []

    # DB-derived context (profile, memories, mode, other-server health). One session.
    try:
        async with AsyncSessionLocal() as db:
            ctx.server_profile = await build_server_profile(db, server)
            ctx.memories = await memory_service.block_for_server(db, server.id, owner_id)
            actor = await db.get(User, uuid.UUID(str(owner_id)))
            if actor is not None:
                ctx.ally_mode = getattr(actor, "ally_mode", None)  # Track D autonomy
                roster = await team_service.mission_roster(db, actor, None)
                other_roster = [s for s in roster if str(s.id) != str(server.id)]
                if other_roster:
                    health = await build_fleet_health(db, other_roster)
                    lines = []
                    for s in other_roster:
                        base = f"- {s.name} — {s.os_type or 'unknown'}, status: {s.status or 'unknown'}"
                        h = health.get(str(s.id))
                        lines.append(f"{base}\n  {h}" if h else base)
                    ctx.other_servers = "\n".join(lines)
    except Exception as exc:  # noqa: BLE001 — context must never block chat
        logger.warning("chat context build failed for %s: %s", server.id, exc)

    # Track B pre-mission Scout — read-only file recon for a file / cross-server request.
    if want_scout:
        try:
            if scout_service.should_scout(user_input, bool(other_roster)):
                ctx.scout = await scout_service.scout(server, user_input, other_roster)
        except Exception as exc:  # noqa: BLE001 — the scout must never block chat
            logger.info("scout skipped for %s: %s", server.id, exc)

    # Ally Context C1 Live Look — a fast read-only snapshot for a problem report.
    if want_live and live_look_service.should_look(user_input, skill is not None):
        try:
            ctx.live_snapshot = await live_look_service.snapshot(server)
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.info("live look skipped for %s: %s", server.id, exc)

    return ctx
