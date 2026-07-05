"""Proactive fleet intelligence — Ally reviews the whole fleet and says what needs
attention, before the user asks.

DELIBERATELY DETERMINISTIC (zero AI cost): it reads data ServerAlly already collects
— latest metrics, the last security grade, the last threat verdict, backups, and
online/last-seen — and turns it into a health SCORE (0-100) plus RANKED, plain-English
findings, each with a one-click ACTION (open Ally with a fix prompt, or jump to the
right page). The AI stays where it adds value: actually fixing (the seeded mission).

All batched queries (DISTINCT ON per server — never per-server, never SSH), so the
report is cheap and instant. The scoring/finding logic is pure (``_analyze_server``)
so it's fully unit-testable without a DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import ServerMetric
from app.models.backup import Backup
from app.models.playbook import Playbook, PlaybookRun
from app.models.security_scan import SecurityScan
from app.models.server import Server
from app.models.threat_scan import ThreatScan

_MAX_FLEET = 60


@dataclass
class Finding:
    id: str            # stable key, e.g. "disk-full"
    severity: str      # critical | high | medium | low | info
    title: str         # plain-English headline
    detail: str        # the specifics
    penalty: int       # points off the health score
    action: dict       # {kind: "chat"|"page", label, seed?/path?}


@dataclass
class ServerHealth:
    server_id: str
    name: str
    score: int
    grade: str         # A–F derived from score
    status: str        # online | offline | unknown | hosting
    headline: str      # the worst finding's title, or "All good"
    findings: list[Finding] = field(default_factory=list)


# ── grade + severity helpers ──────────────────────────────────────────────────
_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _grade(score: int) -> str:
    return "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"


def _sec_page(sid: str, label: str) -> dict:
    return {"kind": "page", "label": label, "path": f"/servers/{sid}/security"}


def _backups_page(sid: str, label: str) -> dict:
    return {"kind": "page", "label": label, "path": f"/servers/{sid}/backups"}


def _chat(label: str, seed: str) -> dict:
    return {"kind": "chat", "label": label, "seed": seed}


# ── the pure analyzer (no DB) ─────────────────────────────────────────────────

def _analyze_server(
    server: Server,
    metric: ServerMetric | None,
    security: SecurityScan | None,
    threat: ThreatScan | None,
    backups: list[Backup],
    has_installed: bool,
) -> ServerHealth:
    """Turn one server's latest signals into a scored, ranked health summary. Pure —
    every input is a plain object, so this is unit-tested directly."""
    sid = str(server.id)
    findings: list[Finding] = []
    is_hosting = server.connection_type == "hosting"
    status = "hosting" if is_hosting else (server.status or "unknown")

    # Offline is the loudest signal — and makes stale metrics meaningless, so we skip
    # the resource checks below when it's down.
    offline = status == "offline"
    if offline:
        findings.append(Finding(
            "offline", "high", "Server is offline",
            "ServerAlly can't reach this server right now.", 35,
            _chat("Ask Ally", "This server looks offline — can you help me work out why and get it back up?"),
        ))

    # Active-compromise verdict (proactive threat monitoring, Phase 1/2).
    if threat is not None:
        v = threat.verdict
        if v == "compromised":
            findings.append(Finding(
                "threat-compromised", "critical", "This server may be compromised",
                "The last threat scan found strong signs of an active compromise.", 45,
                _sec_page(sid, "Review & respond"),
            ))
        elif v == "at_risk":
            findings.append(Finding(
                "threat-at-risk", "high", "Signs of a possible compromise",
                "The last threat scan flagged indicators worth investigating.", 28,
                _sec_page(sid, "Review threats"),
            ))
        elif v == "suspicious":
            findings.append(Finding(
                "threat-suspicious", "medium", "A few suspicious signals",
                "The last threat scan saw something worth a look.", 12,
                _sec_page(sid, "Review threats"),
            ))

    # Resource pressure (skip if offline — the numbers are stale).
    if metric is not None and not offline:
        disk = metric.disk_percent
        if disk is not None:
            used = f"{metric.disk_used_gb:.0f} GB of {metric.disk_total_gb:.0f} GB" if metric.disk_total_gb else f"{disk:.0f}%"
            if disk >= 92:
                findings.append(Finding(
                    "disk-critical", "high", "Disk is almost full",
                    f"Disk is {disk:.0f}% used ({used}). Things break when it fills up.", 25,
                    _chat("Clean it up with Ally", "My disk is almost full — find what's using the space and clean it up safely."),
                ))
            elif disk >= 82:
                findings.append(Finding(
                    "disk-high", "medium", "Disk filling up",
                    f"Disk is {disk:.0f}% used ({used}) — worth clearing before it's a problem.", 13,
                    _chat("Clean it up with Ally", "My disk is getting full — find what's using the space and clean it up safely."),
                ))
        ram = metric.ram_percent
        if ram is not None and ram >= 92:
            findings.append(Finding(
                "ram-high", "medium", "Memory almost exhausted",
                f"RAM is {ram:.0f}% used — the server may start slowing down or killing processes.", 10,
                _chat("Ask Ally", "My server is very low on memory — what's using it and what can I do?"),
            ))
        cpu = metric.cpu_percent
        if cpu is not None and cpu >= 95:
            findings.append(Finding(
                "cpu-high", "low", "CPU is maxed out",
                f"CPU is at {cpu:.0f}%. If it stays there, the server will feel slow.", 6,
                _chat("Ask Ally", "My server's CPU is very high — can you find what's using it and why?"),
            ))

    # Security posture (SSH servers).
    if not is_hosting:
        if security is not None:
            g = security.grade
            crit = f" — {security.critical_count} critical, {security.high_count} high" if (security.critical_count or security.high_count) else ""
            if g == "F":
                findings.append(Finding(
                    "security-f", "high", "Weak security posture",
                    f"Last security scan graded this {g} ({security.score}/100){crit}.", 22,
                    _sec_page(sid, "See the fixes"),
                ))
            elif g == "D":
                findings.append(Finding(
                    "security-d", "medium", "Security needs attention",
                    f"Last security scan graded this {g} ({security.score}/100){crit}.", 13,
                    _sec_page(sid, "See the fixes"),
                ))
            elif g == "C":
                findings.append(Finding(
                    "security-c", "low", "A few security wins available",
                    f"Last security scan graded this {g} ({security.score}/100).", 5,
                    _sec_page(sid, "See the fixes"),
                ))
        elif not offline:
            findings.append(Finding(
                "security-never", "low", "Security never checked",
                "Run a quick security scan to see how this server is doing.", 4,
                _sec_page(sid, "Run a scan"),
            ))

    # Backups — only nag when there's something worth protecting (installed software).
    if not is_hosting and has_installed:
        active = [b for b in backups if b.is_active]
        if not backups:
            findings.append(Finding(
                "backups-none", "medium", "No backups configured",
                "This server runs real workloads but has no backup — one bad day could lose it.", 9,
                _backups_page(sid, "Set up backups"),
            ))
        elif active and any(b.last_status == "failed" for b in active):
            findings.append(Finding(
                "backups-failed", "medium", "Last backup failed",
                "A configured backup last run failed — your restore point may be stale.", 11,
                _backups_page(sid, "Check backups"),
            ))

    findings.sort(key=lambda f: (_SEV_RANK.get(f.severity, 0), f.penalty), reverse=True)
    score = max(0, min(100, 100 - sum(f.penalty for f in findings)))
    # Any critical finding (e.g. an active compromise) is a failing grade on its own,
    # regardless of the arithmetic.
    if any(f.severity == "critical" for f in findings):
        score = min(score, 35)
    headline = findings[0].title if findings else "All good"
    return ServerHealth(sid, server.name, score, _grade(score), status, headline, findings)


# ── DB-backed fleet analysis ──────────────────────────────────────────────────

async def analyze_fleet(db: AsyncSession, servers: list[Server]) -> list[ServerHealth]:
    """Analyze every given server (the caller passes the user's accessible servers).
    Worst-first so what needs attention is on top. Batched queries only."""
    servers = servers[:_MAX_FLEET]
    ids = [s.id for s in servers]
    if not ids:
        return []

    async def _latest(model, extra=None):
        stmt = select(model).where(model.server_id.in_(ids))
        if extra is not None:
            stmt = stmt.where(extra)
        stmt = stmt.distinct(model.server_id).order_by(model.server_id, model.created_at.desc())
        return {r.server_id: r for r in (await db.execute(stmt)).scalars().all()}

    metrics = {
        m.server_id: m for m in (await db.execute(
            select(ServerMetric).where(ServerMetric.server_id.in_(ids))
            .distinct(ServerMetric.server_id)
            .order_by(ServerMetric.server_id, ServerMetric.recorded_at.desc())
        )).scalars().all()
    }
    security = await _latest(SecurityScan, SecurityScan.status == "completed")
    threats = await _latest(ThreatScan, ThreatScan.status == "completed")

    backups_by: dict = {}
    for b in (await db.execute(select(Backup).where(Backup.server_id.in_(ids)))).scalars().all():
        backups_by.setdefault(b.server_id, []).append(b)

    installed_ids = {
        sid for (sid,) in (await db.execute(
            select(PlaybookRun.server_id).where(
                PlaybookRun.server_id.in_(ids), PlaybookRun.status == "success"
            ).distinct()
        )).all()
    }

    results = [
        _analyze_server(
            s, metrics.get(s.id), security.get(s.id), threats.get(s.id),
            backups_by.get(s.id, []), s.id in installed_ids,
        )
        for s in servers
    ]
    results.sort(key=lambda h: h.score)  # worst first
    return results


def to_dict(h: ServerHealth) -> dict:
    d = asdict(h)
    d["needs_attention"] = h.score < 75 or any(f.severity in ("critical", "high") for f in h.findings)
    return d


def summarize(fleet: list[ServerHealth]) -> dict:
    """A one-glance headline for the whole fleet."""
    attention = [h for h in fleet if h.score < 75 or any(f.severity in ("critical", "high") for f in h.findings)]
    critical = sum(1 for h in fleet for f in h.findings if f.severity == "critical")
    return {
        "total": len(fleet),
        "needs_attention": len(attention),
        "critical_findings": critical,
        "worst_grade": max((h.grade for h in fleet), default="A", key=lambda g: "ABCDF".index(g) if g in "ABCDF" else 0),
    }
