"""Runs one clone: build the new site, then copy the old one's files onto it.

A clone is minutes of work — packing a site, moving it, unpacking it — so the request
returns as soon as the new site row exists and the rest happens here, the same shape the
deploy runner and the playbook runner already use.

**It deliberately reuses the ordinary install machinery instead of inventing a second one.**
The destination site is created through `site_service.create`, which gives it a row, a
status of `installing`, and a `PlaybookRun` to attribute the work to. This runner executes
that run and marks it at the end — so the existing reconciler turns the site live when a
scan actually SEES it, a failure is written onto the site where the customer will read it,
and the site page shows "Setting up" for a clone exactly as it does for any other install.
A separate clone table would have meant a second set of states saying the same things.

**A failure never leaves half a site pretending to be whole.** The steps are ordered so
that everything which can be refused — the size, the room, the layout — is refused before
any file moves, and a copy that fails marks the run failed, which shows as *Setup failed*
with the reason on the site itself.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.playbook import PlaybookRun
from app.models.server import Server
from app.models.site import Site
from app.services import clone_service as clone, connection_manager

logger = logging.getLogger(__name__)

#: The installer is quick; packing and unpacking a large site is not. Both are bounded so a
#: stuck step ends as a readable failure rather than a job that never finishes.
_INSTALL_TIMEOUT = 600
_COPY_TIMEOUT = 1800


async def _run(server: Server, command: str, timeout: int) -> tuple[str, int]:
    try:
        out, err, code = await asyncio.wait_for(
            connection_manager.execute(server, command), timeout=timeout)
    except asyncio.TimeoutError:
        return f"Timed out after {timeout // 60} minutes.", 124
    except Exception as exc:  # noqa: BLE001 — a connection error is an outcome, not a crash
        return str(exc), 1
    return (out or "") + (("\n" + err) if err else ""), code


async def _finish(run_id, status: str, log: list[str], reason: str | None = None) -> None:
    """Write the outcome onto the run the site is watching. Best-effort by design: a
    bookkeeping failure must not be the thing that hides what happened on the server."""
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
        logger.exception("could not record the outcome of clone run %s", run_id)


async def _copy_deploy_setup(source_site_id, new_site_id) -> str | None:
    """Give the copy the same repository setup, pointed at its own folder.

    Ploi copies the repository along with the files, and it is a row rather than anything on
    the server. Two things deliberately do NOT come across:

    * the webhook secret — a shared one would mean one leaked URL deploys both sites;
    * push-to-deploy itself, which stays OFF. A clone made for a look that starts deploying
      on the next push to `main` is a surprise nobody asked for.
    """
    from app.models.deployment import DeployTarget
    from app.services import crypto_service, deploy_service

    async with AsyncSessionLocal() as db:
        source = (await db.execute(
            select(DeployTarget).where(DeployTarget.site_id == source_site_id)
        )).scalars().first()
        if source is None:
            return None
        site = await db.get(Site, new_site_id)
        if site is None or not site.doc_root:
            return None
        try:
            path = deploy_service.valid_path(deploy_service.deploy_root_for(site.doc_root))
        except deploy_service.InvalidDeploy:
            return None
        db.add(DeployTarget(
            user_id=site.user_id, server_id=site.server_id, site_id=site.id,
            name=site.domain, repo=source.repo, branch=source.branch, path=path,
            web_dir=source.web_dir, shared_paths=source.shared_paths,
            build_commands=source.build_commands, after_commands=source.after_commands,
            keep_releases=source.keep_releases,
            auto_deploy=False,
            webhook_secret=crypto_service.encrypt(secrets.token_hex(24)),
        ))
        await db.commit()
        return source.repo


async def run_clone(*, run_id, script: str, source_server_id, source_site_id,
                    dest_server_id, new_site_id, survey: clone.Survey,
                    same_server: bool) -> None:
    """Build the new site and put the old one's files on it."""
    log: list[str] = []

    async with AsyncSessionLocal() as db:
        source_server = await db.get(Server, source_server_id)
        dest_server = (source_server if same_server
                       else await db.get(Server, dest_server_id))
        site = await db.get(Site, new_site_id)
    if source_server is None or dest_server is None or site is None:
        await _finish(run_id, "failed", ["The servers for this clone could not be loaded."],
                      "The servers for this clone could not be loaded.")
        return

    domain = site.domain

    # 1 ─ build the empty site. Until this works there is nowhere for the files to go, and
    #     its own guards are what refuse a domain that is already configured here.
    log.append(f"━━ Creating {domain} on {dest_server.name}")
    out, code = await _run(dest_server, script, _INSTALL_TIMEOUT)
    log.append(out)
    if code != 0:
        from app.services.playbook_service import extract_failure_reason

        await _finish(run_id, "failed", log,
                      extract_failure_reason(log) or "The new site could not be created.")
        return

    # 2 ─ ask the server where it serves the new site from, then work out where the copy
    #     goes. Both can still refuse, and both refuse before any file has moved.
    out, code = await _run(dest_server, clone.build_docroot_command(domain), 120)
    log.append(out)
    try:
        dest_root = clone.parse_docroot(out)
        target = clone.destination_target(survey.scope, dest_root)
    except clone.CloneError as exc:
        log.append(str(exc))
        await _finish(run_id, "failed", log, str(exc))
        return

    # 3 ─ the copy itself.
    if same_server:
        log.append(f"━━ Copying {clone.human(survey.bytes)} into {target}")
        out, code = await _run(dest_server,
                               clone.build_local_copy_command(survey.source, target),
                               _COPY_TIMEOUT)
        log.append(out)
    else:
        archive = clone.archive_path(domain)
        log.append(f"━━ Packing up {clone.human(survey.bytes)} on {source_server.name}")
        out, code = await _run(source_server,
                               clone.build_pack_command(survey.source, archive),
                               _COPY_TIMEOUT)
        log.append(out)
        if code == 0:
            log.append(f"━━ Moving it to {dest_server.name}")
            try:
                from app.services import file_service

                moved = await file_service.transfer_between(
                    source_server, archive, dest_server, archive)
                log.append(f"Moved {clone.human(moved)}.")
            except Exception as exc:  # noqa: BLE001 — a transfer failure is an outcome
                log.append(str(exc))
                code = 1
        # Whatever happened, the packed copy of somebody's whole website does not stay in a
        # temp folder on the source — including when packing itself died partway and left
        # half an archive behind.
        await _run(source_server, clone.build_discard_command(archive), 120)
        if code == 0:
            log.append(f"━━ Unpacking into {target}")
            out, code = await _run(dest_server,
                                   clone.build_unpack_command(archive, target),
                                   _COPY_TIMEOUT)
            log.append(out)

    if code != 0:
        ok, message = clone.explain(code, out)
        await _finish(run_id, "failed", log, message)
        return

    # 4 ─ ownership. Files unpacked by root are files the web server cannot write, which is
    #     the same failure our own cron work found: uploads stop and the site breaks later,
    #     pointing nowhere near the clone that caused it.
    #
    #     Aimed at `target` — the folder the files actually LANDED in — and not at the
    #     folder the web server serves. For a framework site those are different, and
    #     repairing only the served folder was proven on a real machine to leave `.env`,
    #     `artisan` and `storage/` owned by root: the site comes up, and then cannot write.
    from app.services import permissions_service as perms

    try:
        out, code = await _run(dest_server, perms.build_command(target), 600)
        log.append(out)
    except perms.PermissionsError as exc:
        log.append(f"Ownership was left as it was: {exc}")

    repo = await _copy_deploy_setup(source_site_id, new_site_id)
    if repo:
        log.append(f"Connected the same repository ({repo}). Push-to-deploy is off.")

    log.append(f"━━ Done. {domain} is a copy of the original's files.")
    await _finish(run_id, "success", log)
