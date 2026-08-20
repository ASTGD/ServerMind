"""Blueprints — the pure rules, and the engine driven end to end against the real DB.

The engine tests use a real BlueprintRun row and a stubbed server connection, because the
properties that matter — a waiting step does NOT stop the run, a failed required step DOES,
stop is honoured mid-run, an optional failure becomes a skip — live in the loop, and a test
that does not run the loop proves nothing about it.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from app.services import blueprint_service as bs


# ── the rules ────────────────────────────────────────────────────────────────

def test_a_missing_input_is_asked_for_never_guessed():
    """The decided behaviour (2026-08-21): a guessed domain is a website nobody wanted."""
    bp = bs.get("set-up-website")
    with pytest.raises(bs.BlueprintError) as exc:
        bs.check_inputs(bp, {"site_type": "wordpress"})
    assert "domain" in str(exc.value)
    assert "provide" in str(exc.value)


def test_every_required_input_missing_is_named_in_one_message():
    bp = bs.get("set-up-website")
    with pytest.raises(bs.BlueprintError) as exc:
        bs.check_inputs(bp, {})
    msg = str(exc.value)
    assert "domain" in msg and "site_type" in msg


def test_a_site_type_we_cannot_install_is_refused_with_the_choices():
    bp = bs.get("set-up-website")
    with pytest.raises(bs.BlueprintError) as exc:
        bs.check_inputs(bp, {"domain": "shop.com", "site_type": "django"})
    assert "wordpress" in str(exc.value)


def test_the_choices_come_from_the_sites_catalogue_not_a_second_list():
    """A type offered here that site creation refuses is a dead end. One source."""
    from app.services.site_service import CHOOSABLE_TYPES

    bp = bs.get("set-up-website")
    offered = next(i for i in bp.inputs if i.name == "site_type").choices
    for t in offered:
        assert t in CHOOSABLE_TYPES, f"blueprint offers '{t}', site creation does not"


def test_an_unknown_blueprint_names_what_exists():
    with pytest.raises(bs.BlueprintError) as exc:
        bs.get("does-not-exist")
    assert "set-up-website" in str(exc.value)


class _Srv:
    def __init__(self, connection_type="ssh", panel_type=None, name="Box"):
        self.connection_type = connection_type
        self.panel_type = panel_type
        self.name = name


def test_a_panel_server_is_refused_before_anything_runs():
    """The panel would revert our vhost later, at a moment nobody can connect to what
    we did — the same reason the site installers refuse panels."""
    bp = bs.get("set-up-website")
    with pytest.raises(bs.BlueprintError) as exc:
        bs.check_server(bp, _Srv(panel_type="cyberpanel"))
    assert "cyberpanel" in str(exc.value)


def test_a_windows_server_is_refused_plainly():
    bp = bs.get("set-up-website")
    with pytest.raises(bs.BlueprintError) as exc:
        bs.check_server(bp, _Srv(connection_type="winrm"))
    assert "SSH" in str(exc.value)


def test_the_whole_plan_is_visible_before_anything_runs():
    bp = bs.get("set-up-website")
    rows = bs.build_steps(bp, {"domain": "shop.com", "site_type": "laravel"})
    assert all(r["state"] == "pending" for r in rows)
    assert any("Laravel" in r["label"] for r in rows)
    assert [r["key"] for r in rows] == [s.key for s in bp.steps]


def test_watch_backup_and_safety_are_optional_but_https_is_not():
    """Optional means the run survives their failure. HTTPS failing (as opposed to
    WAITING) is a real fault and must stop the run."""
    bp = bs.get("set-up-website")
    optional = {s.key for s in bp.steps if s.optional}
    assert optional == {"watch", "backup", "safety"}


def test_every_step_key_has_an_action_in_the_runner():
    """A step the runner cannot execute would fail at minute ten of a customer's run."""
    from app.workers import blueprint_runner

    for bp in bs.CATALOGUE.values():
        for s in bp.steps:
            assert s.key in blueprint_runner.ACTIONS, f"{bp.key}: no action for '{s.key}'"


# ── the engine, driven ───────────────────────────────────────────────────────

from app.database import AsyncSessionLocal, engine  # noqa: E402
from app.models.blueprint import BlueprintRun  # noqa: E402
from app.workers import blueprint_runner as br  # noqa: E402


@pytest.fixture(autouse=True)
async def _fresh_pool():
    """Each async test gets its own event loop; a pooled connection from the last loop
    cannot be reused on this one (the test_ssl_multi_name lesson)."""
    yield
    await engine.dispose()


async def _make_run(db, steps):
    from app.models.user import User

    user = (await db.execute(select(User).limit(1))).scalar_one()
    from app.models.server import Server
    server = (await db.execute(select(Server).limit(1))).scalar_one_or_none()
    if server is None:
        pytest.skip("dev DB has no server row")
    run = BlueprintRun(user_id=user.id, server_id=server.id,
                       blueprint_key="set-up-website", title="test",
                       inputs={"domain": "bp-test.example.com", "site_type": "php"},
                       status="running", steps=steps)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run, server, user


def _steps(*keys, optional=()):
    return [{"key": k, "label": k, "state": "pending", "note": "",
             "optional": k in optional} for k in keys]


@pytest.fixture
def actions(monkeypatch):
    """Replace the real actions with scripted ones, keeping the LOOP real."""
    def install(mapping):
        table = {}
        for key, result in mapping.items():
            async def act(ctx, _r=result):
                if isinstance(_r, Exception):
                    raise _r
                return _r
            table[key] = act
        monkeypatch.setattr(br, "ACTIONS", table)
    return install


@pytest.mark.asyncio
async def test_a_waiting_step_does_not_stop_the_run(actions):
    """The third status, built in phase 1 on purpose: HTTPS on an unpointed domain is the
    NORMAL ending of the flagship blueprint, and the run must finish honestly past it."""
    actions({
        "https": br.StepResult("waiting", "Waiting for you",
                               leave="Point the domain at 1.2.3.4"),
        "watch": br.StepResult("done", "watching"),
    })
    async with AsyncSessionLocal() as db:
        run, server, user = await _make_run(db, _steps("https", "watch"))
    try:
        await br._run_steps(run.id, server, user.id, run.inputs)
        async with AsyncSessionLocal() as db:
            fresh = await db.get(BlueprintRun, run.id)
            assert fresh.status == "done"
            assert fresh.steps[0]["state"] == "waiting"
            assert fresh.steps[1]["state"] == "done", "the run must continue past a wait"
            assert fresh.left_for_you == ["Point the domain at 1.2.3.4"]
            assert "waiting for you" in (fresh.message or "").lower()
    finally:
        async with AsyncSessionLocal() as db:
            await db.delete(await db.get(BlueprintRun, run.id)); await db.commit()


@pytest.mark.asyncio
async def test_a_failed_required_step_stops_the_run_and_keeps_what_finished(actions):
    actions({
        "look": br.StepResult("done", "fine"),
        "create": br.StepResult("failed", "the installer broke"),
        "watch": br.StepResult("done", "should never run"),
    })
    async with AsyncSessionLocal() as db:
        run, server, user = await _make_run(db, _steps("look", "create", "watch"))
    try:
        await br._run_steps(run.id, server, user.id, run.inputs)
        async with AsyncSessionLocal() as db:
            fresh = await db.get(BlueprintRun, run.id)
            assert fresh.status == "failed"
            assert fresh.steps[0]["state"] == "done"
            assert fresh.steps[1]["state"] == "failed"
            assert fresh.steps[2]["state"] == "pending", "nothing after a failure may run"
            assert "stays done" in fresh.message.lower() or "before this step" in fresh.message.lower()
    finally:
        async with AsyncSessionLocal() as db:
            await db.delete(await db.get(BlueprintRun, run.id)); await db.commit()


@pytest.mark.asyncio
async def test_an_optional_steps_failure_becomes_a_skip_and_the_run_continues(actions):
    actions({
        "backup": br.StepResult("failed", "no space"),
        "safety": br.StepResult("done", "grade A"),
    })
    async with AsyncSessionLocal() as db:
        run, server, user = await _make_run(
            db, _steps("backup", "safety", optional=("backup", "safety")))
    try:
        await br._run_steps(run.id, server, user.id, run.inputs)
        async with AsyncSessionLocal() as db:
            fresh = await db.get(BlueprintRun, run.id)
            assert fresh.status == "done"
            assert fresh.steps[0]["state"] == "skipped"
            assert fresh.steps[0]["note"] == "no space", "the skip must keep its reason"
            assert fresh.steps[1]["state"] == "done"
    finally:
        async with AsyncSessionLocal() as db:
            await db.delete(await db.get(BlueprintRun, run.id)); await db.commit()


@pytest.mark.asyncio
async def test_stop_is_honoured_between_steps(actions):
    """Stop flips the status; the loop must see it at the next checkpoint and go no
    further — and never overwrite the stopped status with 'done'."""
    stopped_marker = {}

    async def stop_then_ok(ctx):
        async with AsyncSessionLocal() as db:
            r = await db.get(BlueprintRun, ctx.run_id)
            r.status = "stopped"
            await db.commit()
        stopped_marker["hit"] = True
        return br.StepResult("done", "finished anyway")

    async def never(ctx):
        stopped_marker["second"] = True
        return br.StepResult("done", "")

    import app.workers.blueprint_runner as mod
    async with AsyncSessionLocal() as db:
        run, server, user = await _make_run(db, _steps("look", "create"))
    orig = mod.ACTIONS
    mod.ACTIONS = {"look": stop_then_ok, "create": never}
    try:
        await br._run_steps(run.id, server, user.id, run.inputs)
        assert stopped_marker.get("hit")
        assert "second" not in stopped_marker, "a stopped run must not start another step"
        async with AsyncSessionLocal() as db:
            fresh = await db.get(BlueprintRun, run.id)
            assert fresh.status == "stopped", "finishing must not overwrite a stop"
    finally:
        mod.ACTIONS = orig
        async with AsyncSessionLocal() as db:
            await db.delete(await db.get(BlueprintRun, run.id)); await db.commit()


@pytest.mark.asyncio
async def test_a_crashing_action_fails_the_step_not_the_process(actions):
    actions({"look": RuntimeError("boom")})
    async with AsyncSessionLocal() as db:
        run, server, user = await _make_run(db, _steps("look"))
    try:
        await br._run_steps(run.id, server, user.id, run.inputs)
        async with AsyncSessionLocal() as db:
            fresh = await db.get(BlueprintRun, run.id)
            assert fresh.status == "failed"
            assert "boom" in fresh.steps[0]["note"]
    finally:
        async with AsyncSessionLocal() as db:
            await db.delete(await db.get(BlueprintRun, run.id)); await db.commit()


@pytest.mark.asyncio
async def test_recover_orphaned_closes_a_run_a_restart_interrupted():
    async with AsyncSessionLocal() as db:
        run, server, user = await _make_run(db, _steps("look"))
    try:
        n = await br.recover_orphaned()
        assert n >= 1
        async with AsyncSessionLocal() as db:
            fresh = await db.get(BlueprintRun, run.id)
            assert fresh.status == "failed"
            assert "restart" in fresh.message.lower()
            assert "still done" in fresh.message.lower()
    finally:
        async with AsyncSessionLocal() as db:
            await db.delete(await db.get(BlueprintRun, run.id)); await db.commit()


@pytest.mark.asyncio
async def test_a_stop_during_the_final_step_is_not_overwritten_by_done():
    """The loop's mid-run checkpoint cannot catch this one: with no next step, the only
    guard is the finish block itself re-checking the status before writing 'done'."""
    async def stop_mid_action(ctx):
        async with AsyncSessionLocal() as db:
            r = await db.get(BlueprintRun, ctx.run_id)
            r.status = "stopped"
            await db.commit()
        return br.StepResult("done", "finished anyway")

    import app.workers.blueprint_runner as mod
    async with AsyncSessionLocal() as db:
        run, server, user = await _make_run(db, _steps("look"))
    orig = mod.ACTIONS
    mod.ACTIONS = {"look": stop_mid_action}
    try:
        await br._run_steps(run.id, server, user.id, run.inputs)
        async with AsyncSessionLocal() as db:
            fresh = await db.get(BlueprintRun, run.id)
            assert fresh.status == "stopped", "the finish block must re-check before writing done"
    finally:
        mod.ACTIONS = orig
        async with AsyncSessionLocal() as db:
            await db.delete(await db.get(BlueprintRun, run.id)); await db.commit()


@pytest.mark.asyncio
async def test_the_create_step_actually_dispatches_the_installer(monkeypatch):
    """Found live, on the first real run: `site_service.create` records the request and
    hands the SCRIPT back — the CALLER dispatches it. This step did not, so a PlaybookRun
    sat saying 'running' forever while the checklist said 'Installing…'. The test runs the
    real action and asserts the script reaches the task queue."""
    from types import SimpleNamespace

    from app.services import site_service
    from app.workers import playbook_tasks

    dispatched = {}

    async def fake_create(db, server, user, *, domain, site_type, **kw):
        return (SimpleNamespace(id="site-1"), "run-1", "#!/bin/bash\necho hi")

    monkeypatch.setattr(site_service, "create", fake_create)
    monkeypatch.setattr(playbook_tasks.run_playbook_task, "delay",
                        lambda *a: dispatched.update(run_id=a[0], script=a[2]))

    class _PollDone(Exception):
        pass

    async def no_sleep(_s):
        raise _PollDone()          # stop before the poll loop; the dispatch already happened

    monkeypatch.setattr(br.asyncio, "sleep", no_sleep)

    async with AsyncSessionLocal() as db:
        run, server, user = await _make_run(db, _steps("create"))
    ctx = br._Ctx(run.id, server, user.id, run.inputs)
    try:
        with pytest.raises(_PollDone):
            await br._act_create(ctx)
        assert dispatched.get("run_id") == "run-1", "the installer script was never dispatched"
        assert "echo hi" in dispatched.get("script", "")
    finally:
        async with AsyncSessionLocal() as db:
            await db.delete(await db.get(BlueprintRun, run.id)); await db.commit()


@pytest.mark.asyncio
async def test_a_report_blueprint_shows_every_red_row_instead_of_stopping(monkeypatch):
    """A pre-launch report that stops at the first problem hides the other checks — the
    opposite of its job. A failed report check stays RED (not skipped: red is the finding)
    and the run continues to the end."""
    table = {}
    for key, res in {
        "dns_check": br.StepResult("failed", "not pointed"),
        "https_check": br.StepResult("failed", "no certificate"),
        "page_check": br.StepResult("done", "serving"),
    }.items():
        async def act(ctx, _r=res):
            return _r
        table[key] = act
    monkeypatch.setattr(br, "ACTIONS", table)

    steps = [{"key": k, "label": k, "state": "pending", "note": "", "optional": False,
              "report": True} for k in ("dns_check", "https_check", "page_check")]
    async with AsyncSessionLocal() as db:
        run, server, user = await _make_run(db, steps)
    try:
        await br._run_steps(run.id, server, user.id, run.inputs)
        async with AsyncSessionLocal() as db:
            fresh = await db.get(BlueprintRun, run.id)
            assert fresh.status == "done", "a report with findings still FINISHES"
            assert fresh.steps[0]["state"] == "failed"
            assert fresh.steps[1]["state"] == "failed", "the second problem must also be found"
            assert fresh.steps[2]["state"] == "done"
            assert "2 checks need attention" in fresh.message
    finally:
        async with AsyncSessionLocal() as db:
            await db.delete(await db.get(BlueprintRun, run.id)); await db.commit()


def test_a_build_blueprint_still_stops_at_a_failure():
    """The report rule must not leak into build blueprints — building past a failure
    leaves half a job. Pinned structurally: set-up-website rows carry no report flag."""
    from app.services import blueprint_service as b

    rows = b.build_steps(b.get("set-up-website"), {"domain": "a.com", "site_type": "php"})
    assert all("report" not in r for r in rows)
    rows = b.build_steps(b.get("site-ready-to-go-live"), {"domain": "a.com"})
    assert all(r.get("report") for r in rows)
