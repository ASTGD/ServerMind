"""Runs one staging copy: build the site, copy the files, give it its own data.

A staging copy is minutes of work — an rsync of a whole website and a database dump and
import — so the request returns as soon as the new site row exists and the rest happens
here, the same shape the clone, deploy and playbook runners already use.

**A staging copy is a clone plus three things**, and it deliberately reuses the ordinary
machinery for the parts that are not new. The site itself is created through
`site_service.create`, which is what gives it a *virtual host* — without one the copy is
files on a disk that nobody can visit, which is not a website. What staging adds on top is
its own database with the live data in it, a configuration repointed at that database, and
search engines told to stay away.

**One rule outranks everything else here: a staging copy must never be left pointing at the
live database.** Copy a live site's files and leave its configuration alone and the copy is
now READING AND WRITING live data — somebody "testing" a bulk delete deletes real orders.
So every step after the files are copied removes the copied files and drops the copy's
database if it fails. What is left behind then is an empty site with a placeholder page,
which can reach nothing, rather than something half-made that looks finished.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.database import AsyncSessionLocal
from app.models.playbook import PlaybookRun
from app.models.server import Server
from app.models.site import Site
from app.services import clone_service as clone
from app.services import connection_manager, robots_service as rb
from app.services import staging_service as st

logger = logging.getLogger(__name__)

#: The installer is quick; copying a whole website and its database is not. Both are bounded
#: so a stuck step ends as a readable failure rather than a job that never finishes.
_INSTALL_TIMEOUT = 600
_COPY_TIMEOUT = 1800
_DATA_TIMEOUT = 1800


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
        logger.exception("could not record the outcome of staging run %s", run_id)


async def _set_doc_root(site_id, doc_root: str) -> None:
    """Record where the copy is served from, so its own pages work before the next scan.

    The status is deliberately NOT touched: a site becomes live when a scan SEES it, which
    is the same rule every other install follows.
    """
    try:
        async with AsyncSessionLocal() as db:
            site = await db.get(Site, site_id)
            if site is not None:
                site.doc_root = doc_root
                await db.commit()
    except Exception:  # noqa: BLE001
        logger.info("could not record the staging site's document root")


async def _undo(server: Server, target: str, db_name: str, db_user: str,
                log: list[str], engine: str = "mysql", domain: str = "") -> None:
    """Take the copy away — the files first, then the database made for them.

    This is what makes the rule enforceable. Anything that fails after the files are on disk
    would otherwise leave an application configured to talk to the LIVE database, which is
    worse than no staging site at all.

    The database RECORD goes too. It names a database that is about to be dropped, and a
    file left pointing at one that no longer exists would have the remover try to drop it
    again later — reporting a failure about something that was never there.
    """
    from app.services import database_service

    # No target means nothing was ever copied — the site itself never got built. Saying
    # files "could not be removed" there would send somebody looking for files that were
    # never written.
    if target:
        out, _code = await _run(server, st.build_discard_command(target), 300)
        if "discarded" in out:
            log.append("The copied files were removed.")
        else:
            log.append(f"The copied files at {target} could not be removed — remove them "
                       f"by hand.")
    if db_name:
        try:
            await database_service.drop_database(server, engine=engine,
                                                 db_name=db_name, user=db_user)
            log.append("The database made for the copy was removed.")
        except Exception:  # noqa: BLE001 — an orphan database is worth a line, not a crash
            log.append(f"The database {db_name} made for the copy could not be removed.")
        if domain:
            # Best-effort, and deliberately not worth a line in the log: the record is
            # bookkeeping, and a leftover file is a much smaller problem than the database
            # it named.
            await _run(server, st.build_forget_db_record(domain), 60)


async def run_staging(*, run_id, script: str, server_id, source_site_id, new_site_id,
                      survey: dict, db_name: str = "", db_user: str = "",
                      db_pass: str = "", source_db: str = "",
                      engine: str = "mysql") -> None:
    """Build the staging site and make it a real copy of the live one."""
    log: list[str] = []

    async with AsyncSessionLocal() as db:
        server = await db.get(Server, server_id)
        site = await db.get(Site, new_site_id)
        source = await db.get(Site, source_site_id)
    if server is None or site is None or source is None:
        await _finish(run_id, "failed", ["This staging copy could not be loaded."],
                      "This staging copy could not be loaded.")
        return

    domain, source_domain = site.domain, source.domain

    # 1 ─ build the site. Until this works there is nowhere for the files to go AND nothing
    #     serving them: this step is what writes the virtual host.
    log.append(f"━━ Creating {domain} on {server.name}")
    out, code = await _run(server, script, _INSTALL_TIMEOUT)
    log.append(out)
    if code != 0:
        from app.services.playbook_service import extract_failure_reason

        # Nothing has been copied yet, so there is nothing pointing anywhere. The database
        # made ahead of the files is the only thing to take back.
        await _undo(server, "", db_name, db_user, log, engine)
        await _finish(run_id, "failed", log,
                      extract_failure_reason(log) or "The staging site could not be created.")
        return

    # 2 ─ ask the server where it serves the new site from. Asked rather than assumed: the
    #     copy going anywhere else is a copy nobody can visit.
    out, code = await _run(server, clone.build_docroot_command(domain), 120)
    log.append(out)
    try:
        dest_root = clone.parse_docroot(out)
        target = clone.destination_target(survey.get("scope", "docroot"), dest_root)
    except clone.CloneError as exc:
        await _undo(server, "", db_name, db_user, log, engine)
        await _finish(run_id, "failed", log, str(exc))
        return
    await _set_doc_root(new_site_id, dest_root)

    # 3 ─ the copy, and the repoint that makes it safe. They are one command because the
    #     rule is one rule: a copy that cannot be repointed removes itself.
    log.append(f"━━ Copying {st.human(survey.get('bytes', 0))} into {target}")
    out, code = await _run(server, st.build_stage_command(
        source=survey["source"], target=target, domain=domain,
        source_domain=source_domain, config=survey.get("config", "none"),
        db_name=db_name, db_user=db_user, db_pass=db_pass), _COPY_TIMEOUT)
    log.append(out)
    ok, message = st.explain(code, out)
    if not ok:
        await _undo(server, target, db_name, db_user, log, engine, domain)
        await _finish(run_id, "failed", log, message)
        return

    # 4 ─ its own data. An empty database is not a copy — for WordPress it is the install
    #     wizard — so a copy that cannot be filled is removed rather than handed over.
    if db_name and source_db:
        log.append(f"━━ Copying the data from {source_db}")
        out, code = await _run(server, st.build_copy_data_command(
            engine=engine, source_db=source_db, target_db=db_name), _DATA_TIMEOUT)
        log.append(out)
        ok, message = st.explain_data(code, out)
        log.append(message)
        if not ok:
            await _undo(server, target, db_name, db_user, log, engine, domain)
            await _finish(run_id, "failed", log, message)
            return

    # 5 ─ ownership. Files written by root are files the web server cannot write: the site
    #     comes up and then cannot save anything, days later, pointing nowhere near here.
    from app.services import permissions_service as perms

    try:
        out, _code = await _run(server, perms.build_command(target), 600)
        log.append(out)
    except perms.PermissionsError as exc:
        log.append(f"Ownership was left as it was: {exc}")

    # 6 ─ keep it out of search results. A staging copy that gets indexed hands the live
    #     site's own content a competitor, under a domain nobody meant to publish.
    await _block_robots(server, domain, dest_root, log)

    log.append(f"━━ Done. {domain} is a copy with its own database and its own settings.")
    await _finish(run_id, "success", log)


async def _block_robots(server: Server, domain: str, doc_root: str,
                        log: list[str]) -> None:
    """Ask search engines to stay away. Best-effort: the copy is already a working copy, so
    a failure here is worth saying rather than worth throwing the whole thing away for."""
    from app.services import php_service

    try:
        state = await php_service.read(server)
        config = php_service.config_for_site(state.get("sites", []), doc_root, domain)
        if config is None:
            log.append("Search engines could not be blocked — this site's configuration "
                       "file was not found. Turn it on from the site's Manage screen.")
            return
        path = config["config"]
        apache = "/apache2/" in path or "/httpd/" in path
        out, code = await _run(
            server, rb.build_command(path, domain, block=True, apache=apache), 180)
        ok, message = rb.explain(code, out, block=True)
        log.append(message if ok else f"Search engines were not blocked: {message}")
    except Exception as exc:  # noqa: BLE001
        log.append(f"Search engines were not blocked: {exc}")
