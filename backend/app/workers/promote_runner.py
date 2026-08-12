"""Runs one file-copy promotion: staging's files onto the live site.

Copying a whole website is minutes, not a request, so the endpoint returns as soon as the
run row exists and the work happens here — the same shape the clone, staging, deploy and
playbook runners already use.

**This is the only thing in the product that can destroy a working website**, so the runner
adds nothing clever of its own. The command it runs was proven on a real server: back up
first and stop if that fails, build the new version in a folder nobody is serving, then
switch. Everything this file does is bookkeeping around that.

The one judgement here is what happens when the command fails. It fails *safe* by
construction — the switch is the last thing it does — so a failure means the live site is
untouched, and the run says so rather than leaving somebody wondering whether their site is
half-replaced.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models.playbook import PlaybookRun
from app.models.server import Server
from app.services import connection_manager, promote_service as pr

logger = logging.getLogger(__name__)

#: A promotion copies a whole website twice — once beside the live one, once as a backup —
#: and `--checksum` reads every byte of both. Slower than a deploy on purpose.
_TIMEOUT = 1800


async def _finish(run_id, status: str, log: list[str], reason: str | None = None) -> None:
    """Write the outcome onto the run. Best-effort: a bookkeeping failure must not be the
    thing that hides what happened on the server."""
    try:
        async with AsyncSessionLocal() as db:
            run = await db.get(PlaybookRun, run_id)
            if run is None:
                return
            run.status = status
            run.output = "\n".join(log)[-200_000:]
            run.failure_reason = reason
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("could not record the outcome of promote run %s", run_id)


async def run_promote(*, run_id, server_id, staging_root: str, live_root: str,
                      stamp: str, live_domain: str, staging_domain: str) -> None:
    """Put the staging copy's files onto the live site."""
    log = [f"━━ Putting {staging_domain} live at {live_domain}"]

    async with AsyncSessionLocal() as db:
        server = await db.get(Server, server_id)
    if server is None:
        await _finish(run_id, "failed", ["This server could not be loaded."],
                      "This server could not be loaded.")
        return

    command = pr.build_file_promote_command(
        staging_root=staging_root, live_root=live_root, stamp=stamp)
    try:
        out, err, code = await asyncio.wait_for(
            connection_manager.execute(server, command), timeout=_TIMEOUT)
        text = (out or "") + (("\n" + err) if err else "")
    except asyncio.TimeoutError:
        # Said plainly, because the honest answer is "we do not know how far it got".
        await _finish(run_id, "failed", log + ["Timed out."],
                      f"This took longer than {_TIMEOUT // 60} minutes and was stopped. "
                      f"Check the site before trying again.")
        return
    except Exception as exc:  # noqa: BLE001 — a connection error is an outcome, not a crash
        await _finish(run_id, "failed", log + [str(exc)],
                      f"The connection to {server.name} failed, so nothing was changed.")
        return

    log.append(text)
    if code != 0:
        from app.services.playbook_service import extract_failure_reason

        # The command switches last, so any failure leaves the live site as it was. Saying
        # so is the point: the alternative is somebody assuming their site is half-replaced
        # and reaching for a restore they do not need.
        reason = extract_failure_reason(log) or "The promotion did not finish."
        await _finish(run_id, "failed", log,
                      f"{reason} {live_domain} was not changed.")
        return

    log.append(f"━━ Done. {live_domain} is now serving the files from {staging_domain}.")
    await _finish(run_id, "success", log)
