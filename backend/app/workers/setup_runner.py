"""Runs a server setup, one installer at a time, and records where it got to.

Detached on purpose. The screen tells the customer *"it is safe to leave this page"*, and
that has to be true — so the loop lives in a background task and every step is written to
the database as it completes. Come back in an hour, on another device, and the checklist
is exactly where it should be.

Each step reuses an existing playbook rather than new provisioning code. That is the whole
point of the feature: the installers were already there and tested; what was missing was
something that ran them in order so the customer did not have to know the order.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.playbook import Playbook
from app.models.server import Server
from app.models.server_setup import ServerSetup
from app.services import connection_manager, playbook_service, setup_service

logger = logging.getLogger(__name__)

_STEP_TIMEOUT = 900          # a cold apt install on a small VPS is genuinely slow
_MAX_OUTPUT = 4000           # per step; the log is for diagnosis, not archaeology


def _now():
    return datetime.now(timezone.utc)


async def _script_for(db, step: setup_service.Step, server: Server) -> str | None:
    pb = (await db.execute(
        select(Playbook).where(Playbook.slug == step.slug))).scalar_one_or_none()
    if pb is None:
        return None
    raw = pb.script_bash
    if not raw:
        return None
    return playbook_service.substitute_variables(raw, step.variables or {})


async def _run_steps(setup_id, steps: list[setup_service.Step], server: Server) -> None:
    for index, step in enumerate(steps):
        async with AsyncSessionLocal() as db:
            setup = await db.get(ServerSetup, setup_id)
            if setup is None or setup.status != "running":
                return                                   # stopped, or the record is gone
            script = await _script_for(db, step, server)
            rows = list(setup.steps or [])
            rows[index] = {**rows[index], "state": "running",
                           "started_at": _now().isoformat()}
            setup.steps = rows
            setup.current = index
            await db.commit()

        if script is None:
            state, note = ("skipped" if step.optional else "failed"), "installer not found"
        else:
            try:
                out, err, code = await asyncio.wait_for(
                    connection_manager.execute(server, script), timeout=_STEP_TIMEOUT)
                text = ((out or "") + ("\n" + err if err else ""))[-_MAX_OUTPUT:]
                if code == 0:
                    state, note = "done", ""
                else:
                    state = "skipped" if step.optional else "failed"
                    note = playbook_service.extract_failure_reason(text) or \
                        f"exit code {code}"
            except asyncio.TimeoutError:
                state = "skipped" if step.optional else "failed"
                note = f"took longer than {_STEP_TIMEOUT // 60} minutes"
            except Exception as exc:                     # noqa: BLE001
                state = "skipped" if step.optional else "failed"
                note = str(exc)[:200]

        async with AsyncSessionLocal() as db:
            setup = await db.get(ServerSetup, setup_id)
            if setup is None:
                return
            rows = list(setup.steps or [])
            rows[index] = {**rows[index], "state": state, "note": note,
                           "finished_at": _now().isoformat()}
            setup.steps = rows
            if state == "failed":
                # Stop here rather than carrying on. Half a stack is a state nobody can
                # reason about — including Ally, later, when asked why the server is odd.
                setup.status = "failed"
                setup.failed_step = step.label
                setup.finished_at = _now()
                setup.message = (
                    f"Stopped at “{step.label}”. {note or 'It did not complete.'} "
                    "Nothing after this step was run — ask Ally to take a look.")
                await db.commit()
                return
            setup.current = index + 1
            await db.commit()

    async with AsyncSessionLocal() as db:
        setup = await db.get(ServerSetup, setup_id)
        if setup and setup.status == "running":
            setup.status = "done"
            setup.finished_at = _now()
            skipped = sum(1 for r in (setup.steps or []) if r.get("state") == "skipped")
            setup.message = (
                "This server is ready. You can add a website to it now."
                + (f" {skipped} optional step{'' if skipped == 1 else 's'} "
                   f"{'was' if skipped == 1 else 'were'} skipped — the server works "
                   "without them." if skipped else ""))
            await db.commit()


async def start(setup_id, steps: list[setup_service.Step], server: Server) -> None:
    """Kick the run off in the background and return immediately."""
    async def go():
        try:
            await _run_steps(setup_id, steps, server)
        except Exception:                                 # noqa: BLE001
            logger.exception("Server setup %s crashed", setup_id)
            async with AsyncSessionLocal() as db:
                s = await db.get(ServerSetup, setup_id)
                if s and s.status == "running":
                    s.status = "failed"
                    s.message = "Something went wrong. Ask Ally to check the server."
                    s.finished_at = _now()
                    await db.commit()

    asyncio.create_task(go())


async def recover_orphaned() -> int:
    """On startup, close out setups a restart interrupted.

    A record left saying "running" forever is worse than one that admits it stopped: the
    customer waits for something that is not happening.
    """
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(ServerSetup).where(ServerSetup.status == "running"))).scalars().all()
        for s in rows:
            s.status = "failed"
            s.finished_at = _now()
            s.message = ("This stopped when ServerAlly restarted. The steps already "
                         "finished are still done — start it again to continue.")
        if rows:
            await db.commit()
        return len(rows)
