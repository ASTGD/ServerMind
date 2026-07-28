"""Deploy targets, runs, rollback — and the push-to-deploy webhook.

The webhook is the only unauthenticated route here. It is reachable by anyone who learns
the URL, so the HMAC signature is not a formality — it is the entire access control. An
unsigned or wrongly-signed call is refused before the payload is even parsed.
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.deployment import DeployRun, DeployTarget
from app.models.server import Server
from app.models.user import User
from app.services import audit_service, deploy_service as dep, team_service
from app.services.crypto_service import decrypt, encrypt
from app.services.rate_limit_service import limiter
from app.workers import deploy_runner

router = APIRouter(prefix="/api", tags=["deployments"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class TargetIn(BaseModel):
    name: str = Field(max_length=255)
    repo: str = Field(max_length=500)
    branch: str = Field(default="main", max_length=120)
    path: str = Field(max_length=255)
    environment: str = Field(default="production", max_length=20)
    shared_paths: list[str] = Field(default_factory=list)
    build_commands: list[str] = Field(default_factory=list)
    after_commands: list[str] = Field(default_factory=list)
    auto_deploy: bool = False
    keep_releases: int = Field(default=5, ge=2, le=20)


def _public(t: DeployTarget, server_name: str | None = None,
            *, secret: bool = False) -> dict:
    out = {
        "id": str(t.id), "server_id": str(t.server_id), "server_name": server_name,
        "name": t.name, "repo": t.repo, "branch": t.branch, "path": t.path,
        "environment": t.environment,
        "shared_paths": t.shared_paths or [], "build_commands": t.build_commands or [],
        "after_commands": t.after_commands or [], "auto_deploy": t.auto_deploy,
        "keep_releases": t.keep_releases, "current_release": t.current_release,
        "last_status": t.last_status,
        "last_deployed_at": t.last_deployed_at.isoformat() if t.last_deployed_at else None,
        "webhook_url": f"/api/deploy/hook/{t.id}",
    }
    # The secret is shown ONLY when explicitly asked for — on create, and behind a
    # deliberate "reveal" call — so it is not sitting in every list response waiting to
    # be logged by something.
    if secret:
        out["webhook_secret"] = decrypt(t.webhook_secret)
    return out


def _public_run(r: DeployRun) -> dict:
    return {"id": str(r.id), "release": r.release, "kind": r.kind, "trigger": r.trigger,
            "status": r.status, "failed_step": r.failed_step, "log": r.log,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None}


async def _target(target_id: str, db: AsyncSession, user: User,
                  *, execute: bool = False) -> DeployTarget:
    t = await db.get(DeployTarget, target_id)
    if not t:
        raise HTTPException(status_code=404, detail="No such deploy target.")
    # Access flows through the SERVER's rules (Rule 7), so a team member with rights to
    # the server can deploy to it — ownership of the row is not the question.
    await resolve_server(str(t.server_id), user, db, need_execute=execute)
    return t


@router.get("/deploy/targets")
async def list_targets(db: DBDep, current_user: CurrentUser) -> dict:
    servers = await team_service.accessible_servers(db, current_user)
    names = {s.id: s.name for s in servers}
    if not servers:
        return {"targets": [], "count": 0}
    rows = (await db.execute(
        select(DeployTarget).where(DeployTarget.server_id.in_(list(names)))
        .order_by(DeployTarget.name)
    )).scalars().all()
    return {"targets": [_public(t, names.get(t.server_id)) for t in rows],
            "count": len(rows)}


@router.post("/servers/{server_id}/deploy/targets", status_code=201)
async def create_target(server_id: str, body: TargetIn, db: DBDep,
                        current_user: CurrentUser) -> dict:
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    try:
        path = dep.valid_path(body.path)
        repo = dep.valid_repo(body.repo)
        branch = dep.valid_branch(body.branch)
        shared = dep.valid_shared(body.shared_paths)
        build = dep.valid_commands(body.build_commands, label="build")
        after = dep.valid_commands(body.after_commands, label="after-deploy")
    except dep.InvalidDeploy as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    clash = (await db.execute(
        select(DeployTarget).where(DeployTarget.server_id == server.id,
                                   DeployTarget.path == path)
    )).scalar_one_or_none()
    if clash:
        raise HTTPException(
            status_code=409,
            detail=f"“{clash.name}” already deploys into {path} on this server.")

    t = DeployTarget(
        user_id=current_user.id, server_id=server.id, name=body.name.strip()[:255],
        repo=repo, branch=branch, path=path, environment=body.environment,
        shared_paths=shared, build_commands=build, after_commands=after,
        auto_deploy=body.auto_deploy, keep_releases=body.keep_releases,
        webhook_secret=encrypt(secrets.token_urlsafe(32)))
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _public(t, server.name, secret=True)


@router.put("/deploy/targets/{target_id}")
async def update_target(target_id: str, body: TargetIn, db: DBDep,
                        current_user: CurrentUser) -> dict:
    t = await _target(target_id, db, current_user, execute=True)
    try:
        t.path = dep.valid_path(body.path)
        t.repo = dep.valid_repo(body.repo)
        t.branch = dep.valid_branch(body.branch)
        t.shared_paths = dep.valid_shared(body.shared_paths)
        t.build_commands = dep.valid_commands(body.build_commands, label="build")
        t.after_commands = dep.valid_commands(body.after_commands, label="after-deploy")
    except dep.InvalidDeploy as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    t.name = body.name.strip()[:255]
    t.environment = body.environment
    t.auto_deploy = body.auto_deploy
    t.keep_releases = body.keep_releases
    await db.commit()
    await db.refresh(t)
    return _public(t)


@router.get("/deploy/targets/{target_id}/secret")
async def reveal_secret(target_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    """Show the webhook secret again, for pasting into GitHub."""
    t = await _target(target_id, db, current_user, execute=True)
    return {"webhook_secret": decrypt(t.webhook_secret)}


@router.delete("/deploy/targets/{target_id}", status_code=204)
async def delete_target(target_id: str, db: DBDep, current_user: CurrentUser) -> None:
    """Forget the target. Nothing on the server is touched.

    Deleting released code because someone removed a row would be a destructive
    surprise; the files stay and can be removed deliberately.
    """
    t = await _target(target_id, db, current_user, execute=True)
    await db.delete(t)
    await db.commit()


@router.get("/deploy/targets/{target_id}/releases")
async def releases(target_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    t = await _target(target_id, db, current_user)
    server = await db.get(Server, t.server_id)
    try:
        return await deploy_runner.read_releases(t, server)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail=f"Couldn't read releases: {exc}") from exc


@router.post("/deploy/targets/{target_id}/deploy", status_code=202)
async def deploy_now(target_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    t = await _target(target_id, db, current_user, execute=True)
    try:
        run_id = await deploy_runner.start_deploy(t.id, current_user.id)
    except dep.InvalidDeploy as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await audit_service.audit(db, current_user, "deploy.start",
                              meta={"target": t.name, "repo": t.repo, "branch": t.branch})
    return {"run_id": run_id, "status": "running"}


@router.post("/deploy/targets/{target_id}/rollback", status_code=202)
async def rollback(target_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    t = await _target(target_id, db, current_user, execute=True)
    try:
        run_id = await deploy_runner.start_rollback(t.id, current_user.id)
    except dep.InvalidDeploy as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await audit_service.audit(db, current_user, "deploy.rollback",
                              meta={"target": t.name})
    return {"run_id": run_id, "status": "running"}


@router.get("/deploy/targets/{target_id}/runs")
async def runs(target_id: str, db: DBDep, current_user: CurrentUser,
               limit: int = 20) -> dict:
    t = await _target(target_id, db, current_user)
    rows = (await db.execute(
        select(DeployRun).where(DeployRun.target_id == t.id)
        .order_by(DeployRun.started_at.desc()).limit(min(limit, 100))
    )).scalars().all()
    return {"runs": [_public_run(r) for r in rows], "count": len(rows)}


@router.get("/deploy/runs/{run_id}")
async def run_detail(run_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    r = await db.get(DeployRun, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="No such deploy run.")
    await _target(str(r.target_id), db, current_user)
    return _public_run(r)


# ── push-to-deploy ────────────────────────────────────────────────────────────
@router.post("/deploy/hook/{target_id}")
@limiter.limit("30/minute")
async def github_hook(target_id: str, request: Request, db: DBDep,
                      x_hub_signature_256: str | None = Header(default=None),
                      x_github_event: str | None = Header(default=None)) -> dict:
    """GitHub push webhook. Unauthenticated by necessity, signed by requirement.

    The body is read raw and verified BEFORE being parsed: a signature checked after
    parsing has already let unverified input through a parser, and the whole point is
    that nothing unverified is acted upon.
    """
    t = await db.get(DeployTarget, target_id)
    # A wrong id and a wrong signature return the same 404 on purpose — otherwise this
    # endpoint tells an unauthenticated caller which target ids exist.
    if not t or not t.auto_deploy:
        raise HTTPException(status_code=404, detail="Not found.")

    body = await request.body()
    if not dep.verify_github_signature(decrypt(t.webhook_secret), body,
                                       x_hub_signature_256):
        logger.warning("Rejected an unsigned deploy hook for target %s", target_id)
        raise HTTPException(status_code=404, detail="Not found.")

    if x_github_event == "ping":
        return {"ok": True, "message": "Webhook is connected."}
    if x_github_event and x_github_event != "push":
        return {"ok": True, "message": f"Ignoring {x_github_event} events."}

    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(status_code=422, detail="Unreadable payload.")

    go, why = dep.should_deploy(payload, t.branch)
    if not go:
        return {"ok": True, "deployed": False, "message": why}

    run_id = await deploy_runner.start_deploy(t.id, t.user_id, trigger="push")
    return {"ok": True, "deployed": True, "run_id": run_id, "message": why}
