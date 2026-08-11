"""What we learn the first time we reach a newly added server — in ONE place.

There are two doors into the `servers` table: adding a machine by hand, and importing one
from a connected cloud account. Only the first one looked at what it had just added.

That is not a cosmetic gap. The manual add connects once and records four things, and each
of them is load-bearing:

| What                          | Why it matters                                              |
|-------------------------------|-------------------------------------------------------------|
| status (+ `last_seen`)        | otherwise the asset reads "unknown" until a worker runs      |
| **the host-key fingerprint**  | **`ssh_service` skips verification entirely when the pin is NULL** |
| os_type / os_version / arch   | the playbook OS guard and the whole Sites layer read these   |
| `panel_type`                  | decides whether the Control-panel section exists at all      |

The fingerprint is the serious one. `_get_client` only compares when there is something to
compare against (`if want_fp and fingerprint != want_fp`), so a NULL pin means no check at
all. Every other place that writes the pin is a button a person has to press — "Test
connection" and "Trust new key"; **nothing automatic pins a server**, and the metrics worker
that connects to it every five minutes does not. So an imported machine connected
**unverified, on every connection, until somebody happened to press Test**, and the "Server
identity changed" alert that caught a rebuilt box on 3 August could never fire for it. That
is the same shape as the bug found that day, one door up: a verification step that is easy to
not call.

So the fix is the one the plan asked for — *the same code, not a copy*. A copy would drift,
and this is the second time that exact drift has cost something.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

#: How many servers we probe at once during an import.
#:
#: Not about our own resources — it is about theirs. Fifty simultaneous SSH connections from
#: one address is what a brute-force looks like, and fail2ban is installed on a great many of
#: the machines our customers ask us to manage, including by our own hardening playbook. A
#: cap keeps an import from getting ServerAlly banned from the fleet it just imported.
CONCURRENCY = 5


def infer_category(connection_type: str, panel_type: str | None) -> str:
    """The stored Assets label for a new asset.

    Kept only because `/api/v1` publishes it. Where an asset actually appears is derived on
    every read (`lib/assetGroups`), because two doors wrote this column and disagreed — the
    very bug this module exists to close.
    """
    if connection_type == "winrm":
        return "windows"
    if connection_type == "rdp":
        return "windows_rdp"
    if connection_type == "hosting":
        return "hosting"
    if connection_type == "ssh" and panel_type:
        return "hosting"
    return "vps"


def record_os(server: Server, info: dict) -> None:
    """Write what `detect_os` found onto the row.

    Its own function because THREE places were doing it — the manual add, the cloud import
    and the explicit "Detect system" button — and each copy had to remember that a control
    panel changes what the asset IS. One of them forgetting is how a CyberPanel machine ends
    up with no Control-panel section.
    """
    server.os_type = info.get("os_type")
    server.os_version = info.get("os_version")
    server.arch = info.get("arch")
    # A control panel on an SSH box makes it a panel asset: the Control-panel section, and
    # CLI-over-SSH rather than a vhost we would write ourselves and the panel would revert.
    if server.connection_type == "ssh":
        server.panel_type = info.get("panel")
        if info.get("panel"):
            server.category = "hosting"


async def probe(db, server: Server) -> None:
    """Connect once, write down what we found, commit.

    **Best-effort by construction.** A server that cannot be reached is a normal thing to add
    — the address may be typed wrong, the firewall may not be open yet — and refusing to save
    it would be the wrong answer. So every failure here is swallowed and the row simply keeps
    the status it already had.
    """
    from app.services import metrics_service
    from app.services.ssh_service import is_auth_error

    try:
        result = await connection_manager.test_connection(server)
        if result.ok:
            server.status = "online"
            server.last_seen = datetime.now(timezone.utc)
            if result.fingerprint:
                # Trust on first use. Until this is written, every later connection to this
                # server skips host-key verification — see the module docstring.
                server.fingerprint = result.fingerprint
            try:
                record_os(server, await metrics_service.detect_os(server))
            except Exception:  # noqa: BLE001 — OS detect is a bonus; the status is already set
                logger.debug("OS detect failed for %s", server.id, exc_info=True)
        elif result.host_key_changed:
            server.status = "host_changed"
        elif is_auth_error(message=result.error):
            server.status = "auth_failed"
        else:
            server.status = "offline"
        await db.commit()
        await db.refresh(server)
    except Exception:  # noqa: BLE001 — never let the probe fail the add
        logger.debug("Probe failed for %s", server.id, exc_info=True)


async def probe_many(server_ids: list[uuid.UUID]) -> None:
    """Probe newly imported servers in the background, a few at a time.

    Runs AFTER the import has answered, because an import of fifty machines would otherwise
    hold the request open for minutes and time out behind any proxy — and the customer would
    be watching a spinner to learn something the page fills in by itself.

    Each probe gets **its own session**: an `AsyncSession` is not safe to share across
    concurrent tasks, and one that is would still serialise the very work we came here to
    overlap.
    """
    from sqlalchemy import select

    from app.database import AsyncSessionLocal

    limit = asyncio.Semaphore(CONCURRENCY)

    async def one(server_id: uuid.UUID) -> None:
        async with limit:
            try:
                async with AsyncSessionLocal() as session:
                    server = (await session.execute(
                        select(Server).where(Server.id == server_id))).scalar_one_or_none()
                    if server is not None:
                        await probe(session, server)
            except Exception:  # noqa: BLE001 — one unreachable machine must not stop the rest
                logger.debug("Background probe failed for %s", server_id, exc_info=True)

    await asyncio.gather(*(one(sid) for sid in server_ids))
