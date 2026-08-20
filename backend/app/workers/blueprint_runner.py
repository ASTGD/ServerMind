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

        if state == "failed" and row.get("report"):
            # A report blueprint: the red row IS the finding. Stopping at the first
            # problem would hide the other checks — the opposite of a pre-launch report.
            continue

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
        failed = sum(1 for r in (run.steps or []) if r.get("state") == "failed")
        domain = inputs.get("domain", "the site")
        if failed:
            msg = (f"{failed} check{'s' if failed != 1 else ''} need attention — "
                   "each one says where to fix it.")
        elif run.blueprint_key == "set-up-website":
            msg = f"{domain} is set up."
        elif run.blueprint_key == "site-ready-to-go-live":
            msg = f"{domain} checks out."
        else:
            msg = "Done — what we found is below."
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


# ── actions for 'take-over-server' ───────────────────────────────────────────
# Read-only by design except the last (creating monitors). This blueprint's promise is
# that it looks and records — fixing is the owner's decision, so nothing here changes the
# machine. The one write (uptime checks) runs from ServerAlly, not on the server.

async def _act_find_sites(ctx: _Ctx) -> StepResult:
    from app.services import site_service

    await ctx.say("Walking the web roots…")
    # discover returns (sites, truncated, error, privilege) — in that order. The first
    # version of this unpacked it as (found, complete, …), which INVERTED the meaning: a
    # truncated scan would have been allowed to mark sites absent, and a full one refused.
    # `complete` is computed the way the sites router computes it: from what the probe
    # could actually READ — the Phase-0 rule, "you may add what you saw, you may conclude
    # nothing from what you did not".
    found, truncated, _error, level = await site_service.discover(ctx.server)
    complete = site_service.privilege.can_read_everything(level) and not truncated
    async with AsyncSessionLocal() as db:
        await site_service.sync(db, ctx.server, found, complete=complete)
        await db.commit()
    if not found:
        note = "No websites found" if complete else \
            "Could not see everything — no conclusion about websites"
        return StepResult("done", note)
    names = ", ".join(sorted(d.domain for d in found)[:6])
    more = f" and {len(found) - 6} more" if len(found) > 6 else ""
    await ctx.found(f"{len(found)} website{'s' if len(found) != 1 else ''}: {names}{more}")
    ctx.state["site_count"] = len(found)
    return StepResult("done", f"{len(found)} website{'s' if len(found) != 1 else ''} recorded"
                              + ("" if complete else " — the scan could not see everything"))


async def _act_who_access(ctx: _Ctx) -> StepResult:
    """Who can get in: SSH keys and firewall openings, listed — never touched."""
    from app.services import firewall_service as fw
    from app.services import sshkey_service

    await ctx.say("Reading the SSH keys…")
    keys_line = "could not be read"
    try:
        out, code = await ctx.run_script(
            sshkey_service.home_probe(ctx.server.username or "root"))
        if code == 0:
            _path, keys, _note = sshkey_service.parse_home_probe(out)
            keys_line = f"{len(keys)} SSH key{'s' if len(keys) != 1 else ''} can sign in"
            await ctx.found(keys_line + (
                ": " + "; ".join(k.comment or k.fingerprint[:20] for k in keys[:4]) if keys else ""))
    except Exception:  # noqa: BLE001
        pass

    await ctx.say("Reading the firewall…")
    fw_line = "firewall could not be read"
    try:
        out, _code = await ctx.run_script(fw.discovery_probe(ctx.server.port or 22))
        if (out or "").strip():
            state = fw.parse_probe(out, ssh_port=ctx.server.port or 22)
            if not state.active:
                fw_line = "No firewall is active — every port is open"
            else:
                fw_line = (f"Firewall on ({state.manager}) · "
                           f"{len(state.rules)} rule{'s' if len(state.rules) != 1 else ''}")
            await ctx.found(fw_line)
    except Exception:  # noqa: BLE001
        pass
    return StepResult("done", f"{keys_line} · {fw_line}")


async def _act_certs(ctx: _Ctx) -> StepResult:
    from app.models.site import Site
    from app.services import ssl_service

    async with AsyncSessionLocal() as db:
        sites = (await db.execute(select(Site).where(
            Site.server_id == ctx.server.id, Site.is_present.is_(True),
            Site.has_ssl.is_(True)))).scalars().all()
    if not sites:
        return StepResult("done", "No HTTPS sites to check")
    soon, checked = [], 0
    for site in sites[:10]:
        await ctx.say(f"Checking {site.domain}'s certificate…")
        info = await ssl_service.inspect(f"https://{site.domain}/")
        if info.get("expires_at") is None:
            continue
        checked += 1
        days = ssl_service.days_left(info["expires_at"])
        if isinstance(days, int) and days <= 14:
            soon.append(f"{site.domain} ({days}d)")
    if soon:
        await ctx.found("Certificates running out: " + ", ".join(soon))
        return StepResult("done", f"{checked} checked · running out soon: {', '.join(soon)}")
    return StepResult("done", f"{checked} certificate{'s' if checked != 1 else ''} checked — none expiring soon")


async def _act_watch_all(ctx: _Ctx) -> StepResult:
    """The one write: an uptime check per site that is live. Runs from ServerAlly."""
    from app.models.site import Site
    from app.models.uptime import UptimeMonitor
    from app.services import site_service

    await ctx.say("Setting up the checks…")
    made = 0
    async with AsyncSessionLocal() as db:
        sites = (await db.execute(select(Site).where(
            Site.server_id == ctx.server.id, Site.is_present.is_(True)))).scalars().all()
        watchable = [s for s in sites if site_service.should_watch(s.status, s.is_present)]
        known = {site_service.monitor_host(m.url) for m in (await db.execute(
            select(UptimeMonitor).where(UptimeMonitor.user_id == ctx.user_id))).scalars().all()}
        for site in watchable:
            if site.domain in known:
                continue
            db.add(UptimeMonitor(user_id=ctx.user_id, server_id=ctx.server.id,
                                 **site_service.monitor_defaults(site.domain, https=bool(site.has_ssl))))
            known.add(site.domain)
            made += 1
        if made:
            await db.commit()
    if made == 0:
        return StepResult("done", "Every site is already being watched")
    return StepResult("done", f"Now watching {made} site{'s' if made != 1 else ''}, every minute")


# ── actions for 'site-ready-to-go-live' ──────────────────────────────────────
# Entirely read-only. Each check's note IS the report line, and a failure names its fix —
# a failed check here fails the STEP (so the list shows red where it matters) but every
# check is judged independently: the run itself finishes, because a pre-launch report that
# stops at the first problem hides the other four.

def _bp_site(ctx: _Ctx):
    from app.models.site import Site

    async def get():
        async with AsyncSessionLocal() as db:
            return (await db.execute(select(Site).where(
                Site.server_id == ctx.server.id,
                Site.domain == ctx.inputs["domain"]))).scalars().first()
    return get()


async def _act_dns_check(ctx: _Ctx) -> StepResult:
    from app.services import ssl_service

    domain = ctx.inputs["domain"]
    await ctx.say(f"Looking up {domain}…")
    check = await ssl_service.check_dns(domain, ctx.server.host)
    if check.get("ready"):
        return StepResult("done", f"{domain} points at this server")
    note = f"{domain} does not point at this server yet — create an A record to {ctx.server.host}"
    return StepResult("waiting", note,
                      leave=f"Point {domain} (and www.{domain}) at {ctx.server.host} at your domain registrar.")


async def _act_https_check(ctx: _Ctx) -> StepResult:
    from app.services import ssl_service

    domain = ctx.inputs["domain"]
    await ctx.say("Reading the certificate a visitor would get…")
    info = await ssl_service.inspect(f"https://{domain}/")   # never raises, by contract
    if info.get("expires_at") is not None:
        days = ssl_service.days_left(info["expires_at"])
        return StepResult("done", f"HTTPS is on — {days} days left "
                                  f"({info.get('issuer') or 'unknown issuer'})")
    err = (info.get("error") or "").lower()
    if "expired" in err:
        return StepResult("failed", "The certificate has EXPIRED — visitors see a security "
                                    "warning. Renew it from the site's HTTPS page.")
    return StepResult("waiting", "HTTPS is not answering yet",
                      leave=f"Turn on HTTPS for {domain} from the site's page (needs DNS pointed first).")


async def _act_page_check(ctx: _Ctx) -> StepResult:
    """A 200 is not proof — read the body. The rule the verify gate and uptime already
    follow, applied to the launch check."""
    domain = ctx.inputs["domain"]
    await ctx.say("Opening the page…")
    check = (f"curl -sk -o /dev/null -w '%{{http_code}}' --max-time 10 "
             f"-H 'Host: {domain}' http://127.0.0.1/ ; echo; "
             f"curl -sk --max-time 10 -H 'Host: {domain}' http://127.0.0.1/ | head -c 500")
    text, code = await ctx.run_script(check)
    lines = (text or "").splitlines()
    status = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip()
    if code == 0 and status in ("200", "301", "302") and body:
        low = body.lower()
        if "error" in low[:200] and ("fatal" in low or "exception" in low):
            return StepResult("failed", f"HTTP {status}, but the page shows an error — read the site's logs")
        return StepResult("done", f"Serving real content (HTTP {status})")
    if status and not body:
        return StepResult("failed", f"HTTP {status} with an EMPTY page — the classic broken-PHP signature")
    return StepResult("failed", f"The site did not answer (HTTP {status or '?'})")


async def _act_watch_check(ctx: _Ctx) -> StepResult:
    from app.models.uptime import UptimeMonitor
    from app.services import site_service

    domain = ctx.inputs["domain"]
    async with AsyncSessionLocal() as db:
        monitors = (await db.execute(select(UptimeMonitor).where(
            UptimeMonitor.user_id == ctx.user_id))).scalars().all()
    ours = [mo for mo in monitors if site_service.monitor_host(mo.url) == domain]
    if ours and ours[0].is_active:
        return StepResult("done", "Watched every minute from outside")
    return StepResult("failed", "Nothing is watching this site — add a check on the "
                                "server's Monitoring page (one click)")


async def _act_backup_check(ctx: _Ctx) -> StepResult:
    from app.models.backup import Backup

    domain = ctx.inputs["domain"]
    async with AsyncSessionLocal() as db:
        jobs = (await db.execute(select(Backup).where(
            Backup.server_id == ctx.server.id, Backup.is_active.is_(True)))).scalars().all()
    covering = [j for j in jobs if domain in (j.source or "") or (j.source or "") in ("/var/www", "/home")]
    if not covering:
        return StepResult("failed", "No backup job covers this site — set one up on Backups")
    job = covering[0]
    if job.last_status == "success":
        return StepResult("done", f"Backed up ({job.human_schedule or job.cron_expression or 'scheduled'}) — last run succeeded")
    if job.last_status:
        return StepResult("failed", f"A backup job exists but its last run {job.last_status} — check Backups")
    return StepResult("done", "A backup job exists — it has not run yet")


ACTIONS.update({
    "find_sites": _act_find_sites,
    "who_access": _act_who_access,
    "certs": _act_certs,
    "watch_all": _act_watch_all,
    "dns_check": _act_dns_check,
    "https_check": _act_https_check,
    "page_check": _act_page_check,
    "watch_check": _act_watch_check,
    "backup_check": _act_backup_check,
})


# ── actions for 'move-website' ───────────────────────────────────────────────
# Files ride the PROVEN clone flow (create on the destination, copy, placeholder removed,
# ownership repaired). The database moves by IDENTICAL CREDENTIALS: the same database
# name, account and password are created on the destination and the data imported — so
# the site's configuration needs no rewrite at all, which removes the one step of a move
# that silently breaks things. Proof is a Host-header fetch on the DESTINATION before any
# DNS is touched, and the old site is never deleted.

async def _move_site_and_dest(ctx: _Ctx):
    """The site being moved, and the destination server. Resolved fresh each step."""
    from app.models.site import Site

    async with AsyncSessionLocal() as db:
        site = (await db.execute(select(Site).where(
            Site.server_id == ctx.server.id,
            Site.domain == ctx.inputs["domain"]))).scalars().first()
        dest = None
        ref = (ctx.inputs.get("to_server") or "").strip()
        if ref:
            rows = (await db.execute(select(Server).where(
                Server.user_id == ctx.user_id))).scalars().all()
            dest = next((s for s in rows if s.name == ref or str(s.id) == ref), None)
    return site, dest


async def _act_fit(ctx: _Ctx) -> StepResult:
    from app.services import clone_service as clone
    from app.services import staging_service

    site, dest = await _move_site_and_dest(ctx)
    if site is None:
        return StepResult("failed", f"{ctx.server.name} has no website called "
                                    f"'{ctx.inputs['domain']}' on record")
    if dest is None:
        return StepResult("failed", f"You have no server called '{ctx.inputs['to_server']}'. "
                                    "Give its exact name in ServerAlly.")
    try:
        clone.check_request(site, ctx.server, dest, site.domain)
    except clone.CloneError as exc:
        return StepResult("failed", str(exc)[:250])

    await ctx.say("Measuring the site and reading its database settings…")
    text, code = await ctx.run_script(staging_service.build_survey_command(site.doc_root or ""))
    try:
        survey = staging_service.parse_survey(text, code)
    except staging_service.StagingError as exc:
        return StepResult("failed", str(exc)[:250])

    await ctx.say(f"Checking {dest.name} has room…")
    out, _err, _code = await connection_manager.execute(dest, clone.build_fit_command("/var/www"))
    try:
        clone.check_fit(survey["bytes"], clone.parse_free(out or ""))
    except clone.CloneError as exc:
        return StepResult("failed", str(exc)[:250])

    ctx.state["dest_id"] = str(dest.id)
    ctx.state["survey"] = survey
    size = staging_service.human(survey["bytes"])
    db_note = f", database {survey['source_db']}" if survey.get("source_db") else ", no database"
    await ctx.found(f"{site.domain}: {size}{db_note} → {dest.name}")
    return StepResult("done", f"{size} to move{db_note} — {dest.name} has room")


async def _act_copy_files(ctx: _Ctx) -> StepResult:
    import uuid as _uuid

    from app.models.playbook import PlaybookRun
    from app.models.user import User
    from app.services import clone_service as clone
    from app.services import site_service
    from app.workers import clone_runner

    site, dest = await _move_site_and_dest(ctx)
    if site is None or dest is None:
        return StepResult("failed", "The site or the destination disappeared mid-run")

    await ctx.say("Looking at what is there…")
    out, err, code = await connection_manager.execute(
        ctx.server, clone.build_survey_command(site.doc_root or ""))
    try:
        survey = clone.parse_survey((out or "") + (err or ""), code)
    except clone.CloneError as exc:
        return StepResult("failed", str(exc)[:250])

    await ctx.say(f"Creating {site.domain} on {dest.name}…")
    async with AsyncSessionLocal() as db:
        user = await db.get(User, ctx.user_id)
        try:
            new_site, run_id, script = await site_service.create(
                db, dest, user, domain=site.domain, site_type=clone.site_type_for(survey))
        except site_service.SiteError as exc:
            return StepResult("failed", str(exc)[:250])
        ctx.state["new_site_id"] = str(new_site.id)

    asyncio.create_task(clone_runner.run_clone(
        run_id=_uuid.UUID(run_id), script=script,
        source_server_id=ctx.server.id, source_site_id=site.id,
        dest_server_id=dest.id, new_site_id=new_site.id,
        survey=survey, same_server=False))

    waited = 0.0
    while waited < _STEP_TIMEOUT:
        await ctx.say(f"Copying {clone.human(survey.bytes)} to {dest.name}…")
        await asyncio.sleep(_POLL)
        waited += _POLL
        async with AsyncSessionLocal() as db:
            run = await db.get(PlaybookRun, run_id)
            status = run.status if run else "missing"
        if status == "success":
            return StepResult("done", f"{clone.human(survey.bytes)} copied to {dest.name}")
        if status in ("failed", "missing"):
            return StepResult("failed", "The copy did not complete — its log has the reason")
    return StepResult("failed", "The copy is still running after 30 minutes")


async def _act_move_db(ctx: _Ctx) -> StepResult:
    import secrets as _secrets

    from app.services import database_service, file_service

    survey = ctx.state.get("survey") or {}
    db_name = (survey.get("source_db") or "").strip()
    if not db_name or survey.get("config") in ("", "none"):
        return StepResult("done", "This site has no database — nothing to move")

    _site, dest = await _move_site_and_dest(ctx)
    if dest is None:
        return StepResult("failed", "The destination disappeared mid-run")
    engine = survey.get("engine") or "mysql"
    if engine not in ("mysql", "mariadb"):
        return StepResult("failed", f"Moving a {engine} database is not supported yet — "
                                    "move it by hand, then switch DNS")

    # Read the site's own database credentials FROM its config, server-side. They travel
    # over the SSH channel only (the same path the .env editor uses) and are never logged
    # or stored — they exist so the DESTINATION can be given the identical account, which
    # is what makes a config rewrite unnecessary.
    await ctx.say("Reading the site's database settings…")
    cfg = survey.get("config")
    doc = ctx.inputs["domain"]
    if cfg == "wordpress":
        # wp-cli writes `define( 'DB_USER',` — with a SPACE — while hand-written configs
        # use `define('DB_USER',`. The first version matched `define..` (exactly two
        # characters) and read nothing from every wp-cli site, which is every site our own
        # installer makes. Match the constant name alone, and strip the \r a CRLF config
        # would leave on the value.
        read = ("awk -F\"'\" '{gsub(/\\r/,\"\")} /DB_USER/{u=$4} /DB_PASSWORD/{p=$4} "
                "END{print u; print p}' "
                f"$(ls /var/www/{doc}/wp-config.php /var/www/{doc}/public/wp-config.php 2>/dev/null | head -1)")
    else:
        read = (f"awk -F= '/^DB_USERNAME=/{{u=$2}} /^DB_PASSWORD=/{{p=$2}} "
                f"END{{print u; print p}}' /var/www/{doc}/.env")
    text, code = await ctx.run_script(read)
    lines = [ln.strip().strip('"') for ln in (text or "").splitlines()]
    db_user = lines[0] if lines else ""
    db_pass = lines[1] if len(lines) > 1 else ""
    if code != 0 or not db_user or not db_pass:
        return StepResult("failed", "Could not read the site's database credentials from "
                                    "its configuration — move the database by hand")

    stamp = _secrets.token_hex(4)
    dump_path = f"/tmp/sa-move-{stamp}.sql"
    await ctx.say(f"Dumping {db_name}…")
    # As the local superuser over the socket — no password on any command line, the rule
    # every database feature here follows. Mode 600 and removed however this ends.
    dump = (f"set -e; umask 077; mysqldump --single-transaction {shlex_quote(db_name)} "
            f"> {dump_path}; wc -c < {dump_path}")
    text, code = await ctx.run_script(dump)
    if code != 0:
        await ctx.run_script(f"rm -f {dump_path}")
        return StepResult("failed", f"Could not dump {db_name} — is it a MySQL/MariaDB database?")
    size = (text or "").strip().splitlines()[-1] if text else "0"
    if not size.isdigit() or int(size) == 0:
        await ctx.run_script(f"rm -f {dump_path}")
        # An empty dump imported is a database that exists and holds nothing — WordPress
        # renders that as the install wizard. Refused, the staging rule.
        return StepResult("failed", "The database dump came out empty — refusing to move it")

    await ctx.say(f"Carrying the data to {dest.name}…")
    try:
        moved = await file_service.transfer_between(ctx.server, dump_path, dest, dump_path)
    except Exception as exc:  # noqa: BLE001
        await ctx.run_script(f"rm -f {dump_path}")
        return StepResult("failed", f"Could not carry the dump across: {str(exc)[:150]}")

    await ctx.say(f"Creating {db_name} on {dest.name} with the same account…")
    try:
        await database_service.create_database(
            dest, engine="mysql", db_name=db_name, user=db_user,
            password=db_pass, host="localhost")
    except database_service.DatabaseError as exc:
        msg = str(exc)
        if "already exists" not in msg.lower():
            await ctx.run_script(f"rm -f {dump_path}")
            await connection_manager.execute(dest, f"rm -f {dump_path}")
            return StepResult("failed", f"Could not create the database on {dest.name}: {msg[:150]}")

    await ctx.say("Importing…")
    imp = f"set -e; mysql {shlex_quote(db_name)} < {dump_path}; rm -f {dump_path}"
    _out, _err, code2 = await connection_manager.execute(dest, imp)
    await ctx.run_script(f"rm -f {dump_path}")
    if code2 != 0:
        return StepResult("failed", f"The import on {dest.name} failed — the dump was removed")
    return StepResult("done", f"{db_name} moved ({int(size):,} bytes) — same name and "
                              "account, so the site's configuration needed no changes")


async def _act_prove(ctx: _Ctx) -> StepResult:
    """The whole point of the order: proven working on the DESTINATION before any DNS
    changes. A Host-header fetch does what a visitor's browser will do after the switch."""
    _site, dest = await _move_site_and_dest(ctx)
    if dest is None:
        return StepResult("failed", "The destination disappeared mid-run")
    domain = ctx.inputs["domain"]
    await ctx.say(f"Fetching the site from {dest.name} as a visitor would…")
    # `--resolve` pins the domain to the box itself, so a redirect the application issues
    # (WordPress sends / to its canonical URL or its installer) is FOLLOWED on the same
    # machine instead of leaving for DNS that is not switched yet. The first version used
    # a Host header and refused to follow — and a 302 has no body by nature, so a site
    # behaving exactly like its source read as "empty page". Found live, on the first
    # full move.
    r = f"--resolve {domain}:80:127.0.0.1 --resolve {domain}:443:127.0.0.1"
    check = (f"curl -sk -o /dev/null -w '%{{http_code}}' --max-time 15 -L --max-redirs 3 "
             f"{r} http://{domain}/ ; echo; "
             f"curl -sk --max-time 15 -L --max-redirs 3 {r} http://{domain}/ | head -c 400")
    out, _err, code = await connection_manager.execute(dest, check)
    lines = (out or "").splitlines()
    status = lines[0].strip() if lines else ""
    body = "\n".join(lines[1:]).strip()
    if code == 0 and status == "200" and body:
        return StepResult("done", f"The new server serves it (HTTP {status}, real content)")
    return StepResult("failed",
                      f"The new server answered HTTP {status or '?'}"
                      f"{' with an empty page' if not body else ''} — DNS was NOT handed "
                      "over; the old site still serves and nothing is lost")


async def _act_handover(ctx: _Ctx) -> StepResult:
    _site, dest = await _move_site_and_dest(ctx)
    host = dest.host if dest else "the new server"
    domain = ctx.inputs["domain"]
    return StepResult(
        "waiting", "Waiting for you — the DNS switch is yours",
        leave=(f"When you are ready, change {domain}'s A record to {host}. The old site "
               f"on {ctx.server.name} keeps serving until then, and stays there afterwards "
               "until you remove it yourself. After the switch, get a certificate on the "
               "new server from the site's HTTPS page."))


from shlex import quote as shlex_quote  # noqa: E402 — used by the move actions

ACTIONS.update({
    "fit": _act_fit,
    "copy_files": _act_copy_files,
    "move_db": _act_move_db,
    "prove": _act_prove,
    "handover": _act_handover,
})
