"""ServerAlly MCP server — Phase 0 spike (docs/MCP-SERVER-PLAN.md §9).

Lets a customer connect their *own* AI client and manage their ServerAlly assets
by conversation. The customer's AI calls our tools; their subscription pays for
the thinking; our AI cost is zero. This server is a thin adapter — no business
logic lives here.

Phase 0 is **authless + local-only**: it resolves a single dev user (env
``MCP_DEV_USER_EMAIL``, else the first user) so the real Rule-7 access path
(``team_service.accessible_servers``) is exercised end to end from a real client.
Phase 1 replaces ``_resolve_caller`` with an OAuth-bearer → User resolver; every
tool body below stays unchanged.

Design rules that hold from day one:
- **No business logic** — each tool is a thin adapter over an existing service.
- **Never returns a credential** — a strict field whitelist (``_server_public``);
  ``encrypted_cred`` and ``fingerprint`` are excluded by construction.
- **Deterministic** — no model call, 0 AI actions.
"""
from __future__ import annotations

import json
import logging
import os
from enum import Enum

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.server import Server
from app.models.user import User
from app.services import team_service

logger = logging.getLogger(__name__)

# Stateless JSON over Streamable HTTP — simplest to scale/proxy and the right
# shape for the Phase-1 OAuth bearer flow. Served at exactly ``/mcp`` (inner path
# "/" here, mounted at "/mcp" in main.py).
mcp_server = FastMCP(
    "serverally_mcp",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


class ResponseFormat(str, Enum):
    """Output format for tool responses."""

    MARKDOWN = "markdown"
    JSON = "json"


# ── Helpers ──────────────────────────────────────────────────────────────────

# The ONLY fields a tool may expose. A strict allowlist: ``encrypted_cred`` and
# ``fingerprint`` are never present here, so no tool can leak them (enforced by
# test in Phase 2, mirroring ``test_user_detail_never_exposes_a_credential``).
def _server_public(s: Server) -> dict:
    """Serialise a Server to a credential-free public dict."""
    os_str = " ".join(x for x in (s.os_type, s.os_version) if x) or "unknown"
    return {
        "id": str(s.id),
        "name": s.name,
        "host": s.host,
        "port": s.port,
        "username": s.username,
        "connection_type": s.connection_type,  # ssh | winrm | hosting | rdp
        "panel_type": s.panel_type,
        "category": s.category,
        "os": os_str,
        "arch": s.arch,
        "shell": s.shell,
        "status": s.status,
        "tags": list(s.tags or []),
        "last_seen": s.last_seen.isoformat() if s.last_seen else None,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def _resolve_caller(db) -> User | None:
    """Phase-0 authless caller resolver.

    Uses ``MCP_DEV_USER_EMAIL`` if set; otherwise, for a useful local demo, the
    account that owns the most servers; otherwise the first user. Phase 1 replaces
    this entirely with OAuth-bearer resolution — tool bodies don't change.
    """
    email = os.environ.get("MCP_DEV_USER_EMAIL")
    if email:
        u = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if u is not None:
            return u
        logger.warning("MCP_DEV_USER_EMAIL=%s not found; falling back to top owner", email)

    # Prefer an account that actually owns servers, so the demo shows a real fleet.
    top = (await db.execute(
        select(User)
        .join(Server, Server.user_id == User.id)
        .group_by(User.id)
        .order_by(func.count(Server.id).desc())
    )).scalars().first()
    if top is not None:
        return top

    return (await db.execute(select(User).order_by(User.created_at))).scalars().first()


def _servers_markdown(servers: list[dict]) -> str:
    """Human-readable server list for display in the customer's AI client."""
    if not servers:
        return "No servers found for this account."
    lines = [f"# Your servers ({len(servers)})", ""]
    for s in servers:
        panel = f" / {s['panel_type']}" if s["panel_type"] else ""
        lines.append(f"## {s['name']} — {s['status']}")
        lines.append(f"- **Host**: {s['host']}:{s['port']}  ·  **User**: {s['username']}")
        lines.append(f"- **OS**: {s['os']} ({s['arch'] or 'arch unknown'})")
        lines.append(f"- **Connection**: {s['connection_type']}{panel}  ·  **Category**: {s['category'] or '—'}")
        if s["tags"]:
            lines.append(f"- **Tags**: {', '.join(s['tags'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ── Tools ────────────────────────────────────────────────────────────────────

@mcp_server.tool(
    name="serverally_list_servers",
    annotations={
        "title": "List ServerAlly servers",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def serverally_list_servers(
    response_format: ResponseFormat = ResponseFormat.MARKDOWN,
) -> str:
    """List every server in the caller's ServerAlly account.

    Read-only. Returns all servers the account can access (owned plus servers a
    teammate has granted), scoped by ServerAlly's access rules (Rule 7). Never
    returns credentials — no passwords, SSH keys, or host fingerprints.

    Args:
        response_format (ResponseFormat): 'markdown' (default, human-readable) or
            'json' (machine-readable).

    Returns:
        str: In 'markdown' mode, a readable list of servers with host, OS, and
        status. In 'json' mode, a JSON object:

        {
          "count": int,
          "servers": [
            {
              "id": str, "name": str, "host": str, "port": int,
              "username": str, "connection_type": str, "panel_type": str|null,
              "category": str|null, "os": str, "arch": str|null, "shell": str,
              "status": str, "tags": [str], "last_seen": str|null,
              "created_at": str|null
            }
          ]
        }

        Never includes ``encrypted_cred`` or ``fingerprint``.

    Examples:
        - "What servers do I have?" → call with response_format='markdown'
        - "List my servers as JSON" → call with response_format='json'
    """
    async with AsyncSessionLocal() as db:
        user = await _resolve_caller(db)
        if user is None:
            return "Error: no ServerAlly user found. Create an account first."
        servers = await team_service.accessible_servers(db, user)
        public = [_server_public(s) for s in servers]

    if response_format == ResponseFormat.JSON:
        return json.dumps({"count": len(public), "servers": public}, indent=2)
    return _servers_markdown(public)
