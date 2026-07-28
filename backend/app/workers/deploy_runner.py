"""Runs one deploy, or one rollback, and records what happened.

Deploys take minutes — a clone, dependency install and build are not request-shaped —
so a run is created immediately, executed as a background task, and polled. The caller
gets a run id straight away and nothing hangs on an HTTP timeout, the same shape the MCP
playbook runner already uses.

**A fatal step stops the deploy where it stands.** It does not carry on to the switch,
because the entire point of building in a separate directory is that a failure never
reaches the live site. Non-fatal steps (restart, prune) are recorded and stepped past —
by then the code is already live and aborting would leave the truth ambiguous.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.deployment import DeployRun, DeployTarget
from app.models.server import Server
from app.services import connection_manager, deploy_service as dep

logger = logging.getLogger(__name__)

_STEP_TIMEOUT = 900          # 15 min — a cold `npm ci` on a small box is genuinely slow
_MAX_LOG = 200_000


def _stamp(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")


async def _append(db, run: DeployRun, text: str) -> None:
    run.log = ((run.log or "") + text)[-_MAX_LOG:]
    await db.commit()


async def _execute(run_id, steps: list[dep.DeployStep], server: Server,
                   *, discard: str = "") -> bool:
    """Run the steps in order. Returns True if the deploy reached the end."""
    async with AsyncSessionLocal() as db:
        run = await db.get(DeployRun, run_id)
        if not run:
            return False

        for step in steps:
            await _append(db, run, f"\n━━ {step.name}\n")
            try:
                out, err, code = await asyncio.wait_for(
                    connection_manager.execute(server, step.command),
                    timeout=_STEP_TIMEOUT)
            except asyncio.TimeoutError:
                out, err, code = "", f"Timed out after {_STEP_TIMEOUT // 60} minutes.", 124
            except Exception as exc:  # noqa: BLE001
                out, err, code = "", str(exc), 1

            await _append(db, run, (out or "") + (("\n" + err) if err else ""))

            if code != 0:
                if step.fatal:
                    before = _before_switch(steps, step)
                    if before and discard:
                        # Bin the half-built release. It never went live, and leaving it
                        # would make it the newest release — which is the one a rollback
                        # picks. Best-effort: a failed cleanup must not change the verdict.
                        try:
                            await asyncio.wait_for(
                                connection_manager.execute(server, discard), timeout=120)
                        except Exception:  # noqa: BLE001
                            logger.warning("Couldn't remove the failed release", exc_info=True)
                    run.status = "failed"
                    run.failed_step = step.name
                    run.finished_at = datetime.now(timezone.utc)
                    await _append(
                        db, run,
                        f"\n\n✕ Stopped at “{step.name}”. The site was NOT changed — "
                        "everything up to this point happens in a new folder that nothing "
                        "is serving yet, and that folder has been removed.\n"
                        if before else
                        f"\n\n✕ Failed at “{step.name}”.\n")
                    return False
                await _append(db, run, f"\n(“{step.name}” failed but isn't fatal — carrying on.)\n")

        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        await _append(db, run, "\n\n✓ Done.\n")
        return True


def _before_switch(steps: list[dep.DeployStep], step: dep.DeployStep) -> bool:
    """Did this failure happen before the live site was touched?

    Worth saying explicitly in the log, because the reassuring half of this design is
    invisible otherwise: an owner reading a red failure wants to know whether their site
    is down, and usually it is not.
    """
    names = [s.name for s in steps]
    try:
        return names.index(step.name) < names.index("Go live")
    except ValueError:
        return False


async def start_deploy(target_id, user_id, *, trigger: str = "manual") -> str:
    """Create the run, kick off the work, return the run id immediately."""
    async with AsyncSessionLocal() as db:
        target = await db.get(DeployTarget, target_id)
        if not target:
            raise dep.InvalidDeploy("No such deploy target.")
        server = await db.get(Server, target.server_id)
        if not server or server.connection_type != "ssh":
            raise dep.InvalidDeploy("Deploys need an SSH connection to the server.")

        stamp = _stamp()
        plan = dep.build_plan(
            path=target.path, repo=target.repo, branch=target.branch, stamp=stamp,
            shared=target.shared_paths, build=target.build_commands,
            after=target.after_commands)

        run = DeployRun(target_id=target.id, user_id=user_id, release=plan.release,
                        kind="deploy", trigger=trigger, status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id, steps, discard = run.id, plan.steps, plan.discard

    async def go():
        ok = await _execute(run_id, steps, server, discard=discard)
        async with AsyncSessionLocal() as db2:
            t = await db2.get(DeployTarget, target_id)
            if t:
                t.last_status = "success" if ok else "failed"
                if ok:
                    t.current_release = stamp
                    t.last_deployed_at = datetime.now(timezone.utc)
                await db2.commit()

    asyncio.create_task(go())
    return str(run_id)


async def start_rollback(target_id, user_id) -> str:
    """Roll back to the previous release.

    The release list is read from the SERVER, not from our own records. What is actually
    on disk is the only thing that can be rolled back to — our row could be stale, and a
    rollback that points `current` at a directory that no longer exists takes the site
    down rather than restoring it.
    """
    async with AsyncSessionLocal() as db:
        target = await db.get(DeployTarget, target_id)
        if not target:
            raise dep.InvalidDeploy("No such deploy target.")
        server = await db.get(Server, target.server_id)
        if not server or server.connection_type != "ssh":
            raise dep.InvalidDeploy("Deploys need an SSH connection to the server.")

        out, _err, _code = await connection_manager.execute(
            server, dep.list_releases_command(target.path))
        releases, live = dep.parse_releases(out or "")
        previous = dep.rollback_target(releases, live)     # raises if nowhere to go

        steps = [dep.DeployStep(f"Roll back to {previous}",
                                dep.switch_command(target.path, previous))]
        for i, cmd in enumerate(target.after_commands or [], 1):
            steps.append(dep.DeployStep(f"After rollback ({i})",
                                        f"cd {target.path}/current && {cmd}", fatal=False))

        run = DeployRun(target_id=target.id, user_id=user_id, release=previous,
                        kind="rollback", trigger="manual", status="running")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    async def go():
        ok = await _execute(run_id, steps, server)
        async with AsyncSessionLocal() as db2:
            t = await db2.get(DeployTarget, target_id)
            if t and ok:
                t.current_release = previous
                t.last_status = "rolled-back"
                await db2.commit()

    asyncio.create_task(go())
    return str(run_id)


async def read_releases(target: DeployTarget, server: Server) -> dict:
    """What is on the server right now — read-only."""
    out, _err, _code = await connection_manager.execute(
        server, dep.list_releases_command(target.path))
    releases, live = dep.parse_releases(out or "")
    return {"releases": releases, "current": live}
