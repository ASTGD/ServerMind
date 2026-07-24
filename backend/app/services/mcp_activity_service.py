"""MCP activity feed — record what a connected AI *does*, live (docs/MCP-SERVER-PLAN.md).

Each action is written at START (``running``) and updated at FINISH (``ok`` / ``blocked``
/ ``error``), so a plain poll shows the "⏳ running… → ✓ done" transition. A friendly
label is derived from the tool + command so the feed reads like "Installing docker.io"
rather than a raw command line. The command text is secret-redacted before it is stored,
so a password in a command never lands in the feed or the DB.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import desc, select

from app.database import AsyncSessionLocal
from app.models.mcp_activity import McpActivity
from app.services.secret_redact import redact_secrets

logger = logging.getLogger(__name__)

# Friendly names for the non-shell action tools.
_TOOL_LABELS = {
    "run_command": "Command",
    "run_security_scan": "Security scan",
    "run_threat_scan": "Threat scan",
    "run_playbook": "Run playbook",
    "run_backup": "Run backup",
    "create_site": "Create website",
    "issue_ssl": "Issue SSL certificate",
    "create_database": "Create database",
}

_VERB = {
    "start": "Starting", "stop": "Stopping", "restart": "Restarting", "reload": "Reloading",
    "enable": "Enabling", "disable": "Disabling", "status": "Checking",
}


def _label_from_command(cmd: str) -> str:
    """Best-effort human summary of a shell command ("Installing docker.io"). Falls back to
    a truncated echo of the command — never fails, purely cosmetic."""
    c = (cmd or "").strip()
    if not c:
        return "Ran a command"
    low = c.lower()
    # Package install / remove (apt, dnf, yum, apk, zypper) — grab the first package-ish arg.
    m = re.search(r"\b(?:apt|apt-get|dnf|yum|apk|zypper)\b[^\n]*?\binstall\b\s+(?:-\S+\s+)*([\w.+-]+)", low)
    if m:
        return f"Installing {m.group(1)}"
    m = re.search(r"\b(?:apt|apt-get|dnf|yum|apk|zypper)\b[^\n]*?\b(?:remove|purge|uninstall)\b\s+(?:-\S+\s+)*([\w.+-]+)", low)
    if m:
        return f"Removing {m.group(1)}"
    # systemctl <verb> <svc>  /  service <svc> <verb>
    m = re.search(r"\b(?:systemctl|service)\s+(start|stop|restart|reload|enable|disable|status)\s+([\w.@-]+)", low)
    if m:
        return f"{_VERB.get(m.group(1), m.group(1).title())} {m.group(2)}"
    m = re.search(r"\bservice\s+([\w.@-]+)\s+(start|stop|restart|reload)", low)
    if m:
        return f"{_VERB.get(m.group(2), m.group(2).title())} {m.group(1)}"
    # docker / docker compose
    if re.match(r"docker[- ]compose\b", low):
        return "Docker Compose"
    m = re.match(r"docker\s+([a-z]+)", low)
    if m:
        return f"Docker {m.group(1)}"
    short = c if len(c) <= 60 else c[:60].rstrip() + "…"
    return f"Ran: {short}"


def friendly_label(tool: str, command: str | None = None) -> str:
    """The label shown in the feed. For run_command, summarise the command; else the tool name."""
    if tool == "run_command" and command:
        return _label_from_command(command)
    return _TOOL_LABELS.get(tool, tool.replace("_", " ").title())


async def start(
    *, user_id, client_id: str | None, client_name: str | None, tool: str,
    server_id=None, server_name: str | None = None, command: str | None = None,
) -> str | None:
    """Record an action starting (``status='running'``). Returns the new activity id (str)
    for a later ``finish``, or None on failure. Opens its OWN session so it never disturbs
    the calling tool's session. The command is secret-redacted before storage."""
    try:
        redacted = None
        if command:
            redacted, _ = redact_secrets(command)
        async with AsyncSessionLocal() as db:
            row = McpActivity(
                user_id=user_id, client_id=client_id, client_name=client_name, tool=tool,
                server_id=server_id, server_name=server_name, status="running",
                label=friendly_label(tool, command)[:255], command=redacted,
            )
            db.add(row)
            await db.commit()
            return str(row.id)
    except Exception:  # noqa: BLE001 — the feed must never break a tool
        logger.debug("mcp activity start failed", exc_info=True)
        return None


async def finish(activity_id: str | None, *, status: str, exit_code: int | None = None, detail: str | None = None) -> None:
    """Mark an action finished (ok / blocked / error) with its outcome. Own session,
    best-effort — a recording failure never breaks a tool."""
    if not activity_id:
        return
    try:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(McpActivity).where(McpActivity.id == activity_id)
            )).scalar_one_or_none()
            if row is None:
                return
            row.status = status
            row.exit_code = exit_code
            if detail:
                row.detail = detail[:2000]
            row.finished_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.debug("mcp activity finish failed", exc_info=True)


async def record_done(
    *, user_id, client_id: str | None, client_name: str | None, tool: str,
    server_id=None, server_name: str | None = None, status: str = "ok", detail: str | None = None,
) -> None:
    """Record an already-finished action in one shot (no separate running row). For fast
    tools that don't need a live 'running…' state. Own session, best-effort."""
    try:
        async with AsyncSessionLocal() as db:
            db.add(McpActivity(
                user_id=user_id, client_id=client_id, client_name=client_name, tool=tool,
                server_id=server_id, server_name=server_name, status=status,
                label=friendly_label(tool)[:255], detail=(detail or "")[:2000] or None,
                finished_at=datetime.now(timezone.utc),
            ))
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.debug("mcp activity record_done failed", exc_info=True)


async def recent(db, user_id, limit: int = 60) -> list[McpActivity]:
    """The user's most recent actions, newest first (for the feed)."""
    rows = (await db.execute(
        select(McpActivity).where(McpActivity.user_id == user_id)
        .order_by(desc(McpActivity.started_at)).limit(limit)
    )).scalars().all()
    return list(rows)


def serialize(row: McpActivity) -> dict:
    """Feed-shaped, credential-free dict."""
    return {
        "id": str(row.id),
        "client_name": row.client_name or row.client_id or "An app",
        "tool": row.tool,
        "server_name": row.server_name,
        "status": row.status,          # running | ok | blocked | error
        "label": row.label,
        "command": row.command,        # already secret-redacted
        "exit_code": row.exit_code,
        "detail": row.detail,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }
