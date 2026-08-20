"""Executes a blueprint run, one step at a time, and narrates it as it goes.

The shape is `setup_runner`'s, because that engine's lessons were paid for on real
servers: detached from any socket (safe to leave the page), every state change written to
the database as it happens, a watchdog wider than the apt-lock wait, and orphan recovery
on startup. What is new here:

- **A step can WAIT for the human.** HTTPS on a domain that is not pointed yet is not a
  failure — it is the normal ending of the flagship blueprint. A waiting step does not
  stop the run; its instruction is collected into ``left_for_you`` and the run finishes
  honestly.
- **A live line per step.** A step silent for minutes reads as frozen (the apt-lock
  lesson), so actions call ``ctx.say(...)`` and the note lands on the row immediately.
- **Stop is honoured between operations.** The status flips to 'stopped' and the loop
  sees it at the next checkpoint. Stop cannot undo what already ran — the screen says so.

No model call anywhere in this file, by design. See blueprint_service's docstring.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.blueprint import BlueprintRun
from app.models.server import Server
from app.services import connection_manager, playbook_service

logger = logging.getLogger(__name__)

_STEP_TIMEOUT = 1800          # same reasoning as setup_runner: must beat the apt wait
_QUIET_LIMIT = 300
_POLL = 5                     # how often we re-read a playbook run we started


def _now():
    return datetime.now(timezone.utc)


class _Stopped(Exception):
    """The owner pressed Stop. Not an error."""


class _Ctx:
    """What an action gets to work with. `say` narrates, `found` records a discovery,
    `state` carries facts between steps (the created site's id, the install run)."""

    def __init__(self, run_id, server: Server, user_id, inputs: dict):
        self.run_id = run_id
        self.server = server
        self.user_id = user_id
        self.inputs = inputs
        self.state: dict = {}
        self._step_index = 0

    async def _load(self, db) -> BlueprintRun | None:
        return await db.get(BlueprintRun, self.run_id)

    async def _check_stop(self, db) -> None:
        run = await self._load(db)
        if run is None or run.status != "running":
            raise _Stopped()

    async def say(self, text: str) -> None:
        """Put a live line on the current step — and honour Stop while we are at it."""
        async with AsyncSessionLocal() as db:
            run = await self._load(db)
            if run is None or run.status != "running":
                raise _Stopped()
            rows = list(run.steps or [])
            if 0 <= self._step_index < len(rows):
                rows[self._step_index] = {**rows[self._step_index], "note": text[:300]}
                run.steps = rows
                await db.commit()

    async def found(self, text: str) -> None:
        async with AsyncSessionLocal() as db:
            run = await self._load(db)
            if run is None:
                return
            items = list(run.found or [])
            if text not in items:
                items.append(text[:300])
                run.found = items
                await db.commit()

    async def run_script(self, script: str) -> tuple[str, int]:
        """Run a shell script on the server with the standard bounds."""
        out, err, code = await asyncio.wait_for(
            connection_manager.execute(self.server, script, read_timeout=_QUIET_LIMIT),
            timeout=_STEP_TIMEOUT)
        text = (out or "") + ("\n" + err if err else "")
        return text, code


class StepResult:
    def __init__(self, state: str, note: str = "", leave: str | None = None):
        assert state in ("done", "failed", "waiting", "skipped")
        self.state = state
        self.note = note
        self.leave = leave      # a 'waiting' step's instruction for the human


# ── the actions ──────────────────────────────────────────────────────────────
# Each is deterministic: existing services and playbooks, never a model. An action that
# needs a fact from an earlier step reads ctx.state, and states plainly when it is absent
# rather than guessing.

async def _act_look(ctx: _Ctx) -> StepResult:
    """One quick read-only round trip: what machine is this, and is there room."""
    await ctx.say("Asking the server what it is…")
    probe = ("grep -m1 PRETTY_NAME /etc/os-release 2>/dev/null | cut -d'\"' -f2; "
             "free -m 2>/dev/null | awk '/^Mem:/{print $2}'; "
             "df -BG --output=avail / 2>/dev/null | tail -1 | tr -dc '0-9'")
    try:
        text, code = await ctx.run_script(probe)
    except Exception:  # noqa: BLE001 — the create step will surface a dead server loudly
        text, code = "", 1
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if code == 0 and lines:
        os_name = lines[0] if lines else "Linux"
        mem = f"{round(int(lines[1]) / 1024)} GB memory" if len(lines) > 1 and lines[1].isdigit() else ""
        disk = f"{lines[2]} GB free" if len(lines) > 2 and lines[2].isdigit() else ""
        facts = " · ".join(x for x in [os_name, mem, disk] if x)
        await ctx.found(facts)
        return StepResult("done", facts)
    return StepResult("done", "Reached the server")


async def _act_prepare(ctx: _Ctx) -> StepResult:
    """Make the server able to serve a website — the existing setup recipe, run inline.

    Each installer narrates through the step's live line, so a four-minute apt install
    reads as movement rather than a hang. Already-prepared servers are recognised and the
    step completes without touching anything: safe to run twice, the resume rule.
    """
    from app.models.playbook import Playbook
    from app.services import setup_service

    await ctx.say("Checking what is already installed…")
    probe = ("W=none; command -v nginx >/dev/null && W=nginx; "
             "command -v apache2 >/dev/null && W=apache2; "
             "P=none; command -v php >/dev/null && P=$(php -r 'echo PHP_VERSION;' 2>/dev/null || echo yes); "
             "D=none; command -v mysql >/dev/null && D=mariadb; "
             "command -v psql >/dev/null && D=postgres; echo \"$W|$P|$D\"")
    text, code = await ctx.run_script(probe)
    web, php, dbe = (text.strip().splitlines()[-1].split("|") + ["none", "none", "none"])[:3] \
        if code == 0 and "|" in text else ("none", "none", "none")

    if web != "none" and php != "none" and dbe != "none":
        await ctx.found(f"Already prepared: {web}, PHP {php}, {dbe}")
        return StepResult("done", "Already prepared — nothing to install")

    recipe = setup_service.build_recipe(
        "websites",
        ssh_port=ctx.server.port or 22,
        login_user=ctx.server.username or "root",
        auth_type=ctx.server.auth_type or "password",
    )
    for step in recipe.steps:
        await ctx.say(f"{step.label}…")
        async with AsyncSessionLocal() as db:
            pb = (await db.execute(
                select(Playbook).where(Playbook.slug == step.slug))).scalar_one_or_none()
        if pb is None or not pb.script_bash:
            if step.optional:
                continue
            return StepResult("failed", f"The installer for '{step.label}' is missing")
        variables = {**playbook_service.declared_defaults(pb), **(step.variables or {})}
        script = playbook_service.substitute_variables(pb.script_bash, variables)
        try:
            text, code = await ctx.run_script(script)
        except TimeoutError:
            if step.optional:
                continue
            return StepResult("failed", f"'{step.label}' went quiet and was cut off")
        if code != 0 and not step.optional:
            reason = playbook_service.extract_failure_reason(text) or f"exit code {code}"
            return StepResult("failed", f"'{step.label}' failed: {reason[:150]}")
    return StepResult("done", "Web server, PHP and database installed; firewall on")


async def _act_create(ctx: _Ctx) -> StepResult:
    from app.models.playbook import PlaybookRun
    from app.models.user import User
    from app.services import site_service

    domain = ctx.inputs["domain"]
    site_type = ctx.inputs["site_type"]
    await ctx.say(f"Creating {domain}…")
    async with AsyncSessionLocal() as db:
        user = await db.get(User, ctx.user_id)
        try:
            site, run_id, script = await site_service.create(
                db, ctx.server, user, domain=domain, site_type=site_type)
        except site_service.SiteError as exc:
            return StepResult("failed", str(exc)[:250])
        ctx.state["site_id"] = str(site.id)
        ctx.state["install_run_id"] = run_id

    # `create` records the request and hands the SCRIPT back — every caller dispatches it
    # itself (the sites router, the MCP tool, and now this). Forgetting this line leaves a
    # PlaybookRun saying 'running' that nothing will ever run — found live, on the first
    # real run of this blueprint, as a create step that never finished.
    from app.workers.playbook_tasks import run_playbook_task
    run_playbook_task.delay(run_id, str(ctx.server.id), script)

    waited = 0.0
    while waited < _STEP_TIMEOUT:
        await ctx.say("Installing — the server is doing the work…")
        await asyncio.sleep(_POLL)
        waited += _POLL
        async with AsyncSessionLocal() as db:
            run = await db.get(PlaybookRun, ctx.state["install_run_id"])
            status = run.status if run else "missing"
        if status == "success":
            return StepResult("done", f"{domain} exists and its installer finished")
        if status in ("failed", "missing"):
            return StepResult("failed", "The installer did not complete — its log has the reason")
    return StepResult("failed", "The installer is still running after 30 minutes — check its log")


async def _act_confirm(ctx: _Ctx) -> StepResult:
    """Never say done without reading the real thing — the codebase's oldest rule."""
    from app.services import site_service

    domain = ctx.inputs["domain"]
    await ctx.say("Opening the page to see if it answers…")
    check = (f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 "
             f"-H 'Host: {domain}' http://127.0.0.1/ ; echo; "
             f"curl -s --max-time 10 -H 'Host: {domain}' http://127.0.0.1/ | head -c 400")
    text, code = await ctx.run_script(check)
    lines = (text or "").splitlines()
    status = (lines[0].strip() if lines else "")
    body = "\n".join(lines[1:])[:400]
    ok_status = status in ("200", "301", "302")
    real_body = bool(body.strip())
    if not (code == 0 and ok_status and real_body):
        return StepResult("failed",
                          f"The site answered HTTP {status or '?'} "
                          f"{'with an empty page' if not real_body else ''} — not a working page")

    await ctx.say("Recording what the scan sees…")
    async with AsyncSessionLocal() as db:
        try:
            await site_service.reconcile_installs(db, ctx.user_id)
        except Exception:  # noqa: BLE001 — the curl above is the proof; this is bookkeeping
            logger.debug("reconcile after blueprint create failed", exc_info=True)
    return StepResult("done", f"Serving a real page (HTTP {status})")


async def _act_https(ctx: _Ctx) -> StepResult:
    from app.models.site import Site
    from app.models.user import User
    from app.services import ssl_service

    domain = ctx.inputs["domain"]
    await ctx.say(f"Checking where {domain} points…")
    async with AsyncSessionLocal() as db:
        site = (await db.execute(select(Site).where(
            Site.server_id == ctx.server.id, Site.domain == domain))).scalars().first()
        if site is None:
            return StepResult("failed", "The site's record disappeared — cannot request a certificate")
        user = await db.get(User, ctx.user_id)
        try:
            plan = await ssl_service.plan_issue(
                domain=site.domain, aliases=site.aliases, server_host=ctx.server.host)
        except ssl_service.SslError as exc:
            # Not pointed yet is the NORMAL case on a brand-new site — a wait, not a
            # failure. The instruction goes to left_for_you and the run carries on.
            return StepResult(
                "waiting", "Waiting for you — the domain does not point here yet",
                leave=(f"Point {domain} at {ctx.server.host} (an A record), then turn on "
                       f"HTTPS from the site's page."))
        try:
            ssl_run = await ssl_service.start_issue(
                db, site=site, server=ctx.server, user=user, plan=plan)
        except ssl_service.SslError as exc:
            return StepResult("failed", str(exc)[:250])

    from app.models.playbook import PlaybookRun
    waited = 0.0
    while waited < 600:
        await ctx.say("Getting the certificate…")
        await asyncio.sleep(_POLL)
        waited += _POLL
        async with AsyncSessionLocal() as db:
            run = await db.get(PlaybookRun, ssl_run)
            status = run.status if run else "missing"
        if status == "success":
            covered = ", ".join(plan["covers"])
            return StepResult("done", f"HTTPS is on — covers {covered}")
        if status in ("failed", "missing"):
            return StepResult("failed", "The certificate request did not complete")
    return StepResult("failed", "The certificate request is taking too long")


async def _act_watch(ctx: _Ctx) -> StepResult:
    from app.models.uptime import UptimeMonitor
    from app.services import site_service

    domain = ctx.inputs["domain"]
    await ctx.say("Setting up the check…")
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(UptimeMonitor).where(
            UptimeMonitor.user_id == ctx.user_id))).scalars().all()
        if any(site_service.monitor_host(m.url) == domain for m in existing):
            return StepResult("done", "Already being watched")
        https_on = ctx.state.get("https_on", False)
        db.add(UptimeMonitor(user_id=ctx.user_id, server_id=ctx.server.id,
                             **site_service.monitor_defaults(domain, https=https_on)))
        await db.commit()
    return StepResult("done", "Checked every minute from outside, like a visitor")


async def _act_backup(ctx: _Ctx) -> StepResult:
    from app.models.backup import Backup
    from app.services import backup_service

    domain = ctx.inputs["domain"]
    folder = f"/var/www/{domain}"
    await ctx.say("Creating the daily backup job…")
    async with AsyncSessionLocal() as db:
        dup = (await db.execute(select(Backup).where(
            Backup.server_id == ctx.server.id, Backup.source == folder))).scalars().first()
        if dup is not None:
            return StepResult("done", "A backup job for this folder already exists")
        job = Backup(server_id=ctx.server.id, user_id=ctx.user_id,
                     name=f"{domain} files (daily)", backup_type="files", source=folder,
                     dest_dir="/var/backups/servermind", retention=7,
                     cron_expression="0 3 * * *", human_schedule="every night at 3am",
                     is_active=True)
        db.add(job)
        await db.commit()
        await db.refresh(job)
        await ctx.say("Running the first backup now…")
        try:
            run = await backup_service.perform_backup(db, ctx.server, job)
            if getattr(run, "status", "") == "success":
                return StepResult("done", "First backup done; then nightly at 3am")
            return StepResult("skipped",
                              "The job is scheduled, but the first run failed — check Backups")
        except Exception as exc:  # noqa: BLE001
            return StepResult("skipped", f"The job is scheduled; first run failed: {str(exc)[:120]}")


async def _act_safety(ctx: _Ctx) -> StepResult:
    from app.services import security_service, threat_service

    await ctx.say("Running the security check…")
    try:
        sec = await security_service.run_scan(ctx.server)
        grade = sec.get("grade", "?")
    except Exception:  # noqa: BLE001
        grade = None
    await ctx.say("Looking for anything malicious…")
    try:
        threat = await threat_service.run_scan(ctx.server, fast_only=True)
        verdict = threat.get("verdict", "unknown")
    except Exception:  # noqa: BLE001
        verdict = None
    if grade is None and verdict is None:
        return StepResult("skipped", "The checks could not run — try them from Security")
    bits = []
    if grade:
        bits.append(f"security grade {grade}")
    if verdict:
        nice = {"clean": "no malware found", "unknown": "malware check could not see everything"}
        bits.append(nice.get(verdict, f"malware verdict: {verdict}"))
    await ctx.found("Safety: " + ", ".join(bits))
    note = ", ".join(bits)
    return StepResult("done", note[0].upper() + note[1:] if note else note)


ACTIONS = {
    "look": _act_look,
    "prepare": _act_prepare,
    "create": _act_create,
    "confirm": _act_confirm,
    "https": _act_https,
    "watch": _act_watch,
    "backup": _act_backup,
    "safety": _act_safety,
}


# ── the loop ─────────────────────────────────────────────────────────────────

async def _mark(run_id, index: int, **patch) -> None:
    async with AsyncSessionLocal() as db:
        run = await db.get(BlueprintRun, run_id)
        if run is None:
            return
        rows = list(run.steps or [])
        if 0 <= index < len(rows):
            rows[index] = {**rows[index], **patch}
            run.steps = rows
        await db.commit()


async def _run_steps(run_id, server: Server, user_id, inputs: dict) -> None:
    ctx = _Ctx(run_id, server, user_id, inputs)
    async with AsyncSessionLocal() as db:
        run = await db.get(BlueprintRun, run_id)
        if run is None:
            return
        step_rows = list(run.steps or [])

    leaves: list[str] = []
    for index, row in enumerate(step_rows):
        ctx._step_index = index
        async with AsyncSessionLocal() as db:
            run = await db.get(BlueprintRun, run_id)
            if run is None or run.status != "running":
                return
            run.current = index
            await db.commit()
        await _mark(run_id, index, state="running", started_at=_now().isoformat())

        action = ACTIONS.get(row.get("key"))
        try:
            if action is None:
                result = StepResult("failed", f"Unknown step '{row.get('key')}'")
            else:
                result = await action(ctx)
        except _Stopped:
            return
        except TimeoutError:
            result = StepResult(
                "skipped" if row.get("optional") else "failed",
                "The server went quiet and the connection timed out")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Blueprint step %s crashed", row.get("key"))
            result = StepResult(
                "skipped" if row.get("optional") else "failed", str(exc)[:200])

        # An optional step's failure becomes a skip: the run carries on and the note says
        # why. A required step's failure ends the run — half a job is a state nobody can
        # reason about.
        state = result.state
        if state == "failed" and row.get("optional"):
            state = "skipped"
        if result.leave:
            leaves.append(result.leave)
        if row.get("key") == "https" and state == "done":
            ctx.state["https_on"] = True

        await _mark(run_id, index, state=state, note=result.note,
                    finished_at=_now().isoformat())

        if state == "failed":
            async with AsyncSessionLocal() as db:
                run = await db.get(BlueprintRun, run_id)
                if run is None:
                    return
                run.status = "failed"
                run.finished_at = _now()
                run.message = (f"Stopped at “{row['label']}”. {result.note or 'It did not complete.'} "
                               "Everything before this step is done and stays done.")
                run.left_for_you = leaves
                await db.commit()
            return

    async with AsyncSessionLocal() as db:
        run = await db.get(BlueprintRun, run_id)
        if run is None or run.status != "running":
            return
        run.status = "done"
        run.finished_at = _now()
        run.left_for_you = leaves
        waiting = sum(1 for r in (run.steps or []) if r.get("state") == "waiting")
        skipped = sum(1 for r in (run.steps or []) if r.get("state") == "skipped")
        domain = inputs.get("domain", "the site")
        msg = f"{domain} is set up."
        if waiting:
            msg += " One thing is waiting for you — see below."
        if skipped:
            msg += f" {skipped} optional step{'s were' if skipped != 1 else ' was'} skipped."
        run.message = msg
        await db.commit()


async def start(run_id, server: Server, user_id, inputs: dict) -> None:
    """Kick the run off in the background and return immediately — a caller (an HTTP
    request, an MCP tool call) must never wait on a fifteen-minute job."""
    async def go():
        try:
            await _run_steps(run_id, server, user_id, inputs)
        except Exception:  # noqa: BLE001
            logger.exception("Blueprint run %s crashed", run_id)
            async with AsyncSessionLocal() as db:
                run = await db.get(BlueprintRun, run_id)
                if run and run.status == "running":
                    run.status = "failed"
                    run.finished_at = _now()
                    run.message = "Something went wrong. What finished stays finished."
                    await db.commit()

    asyncio.create_task(go())


async def stop(db, run: BlueprintRun) -> None:
    """Honest about its limits: refuses what comes next; cannot undo what already ran."""
    if run.status != "running":
        return
    run.status = "stopped"
    run.finished_at = _now()
    done = sum(1 for r in (run.steps or []) if r.get("state") == "done")
    run.message = (f"Stopped by you. {done} step{'s' if done != 1 else ''} had already "
                   "finished and stay finished — stopping does not undo them.")
    await db.commit()


async def recover_orphaned() -> int:
    """A record left saying 'running' forever is worse than one that admits it stopped."""
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(BlueprintRun).where(
            BlueprintRun.status == "running"))).scalars().all()
        for r in rows:
            r.status = "failed"
            r.finished_at = _now()
            r.message = ("This stopped when ServerAlly restarted. The steps already "
                         "finished are still done.")
        if rows:
            await db.commit()
        return len(rows)
