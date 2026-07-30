"""Which PHP versions a server has, and which one each website runs on.

Read on every request rather than cached: a stale PHP version shown as current is worse
than showing nothing, because someone would switch a site "to 8.3" that is already on it,
or believe a site is safe on a version it no longer uses.

Switching is the only write here, and it is the one operation in this file that can take a
live website down — an application written for an older PHP can throw a fatal error on a
newer one. So the switch proves the site still serves afterwards and puts the old version
back if it does not; the router's job is to report which of those happened, honestly.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import audit_service, connection_manager, php_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/servers/{server_id}", tags=["php"])

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class SwitchIn(BaseModel):
    """Move one site's config onto another installed PHP version."""
    config: str          # the vhost path this server reported for the site
    domain: str          # what to request when checking the site still works
    version: str


@router.get("/php")
async def get_php(server_id: str, db: DBDep, current_user: CurrentUser) -> dict:
    server = await resolve_server(server_id, current_user, db)
    if server.connection_type != "ssh":
        # Honest rather than empty: PHP management reads and edits files over SSH.
        raise HTTPException(
            status_code=400,
            detail="PHP versions can only be read on a server we reach over SSH.")
    return await php_service.read(server)


@router.post("/php/switch")
async def switch_php(server_id: str, body: SwitchIn, db: DBDep,
                     current_user: CurrentUser) -> dict:
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    if server.connection_type != "ssh":
        raise HTTPException(status_code=400,
                            detail="This server is not managed over SSH.")

    try:
        version = php_service.valid_version(body.version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # The config path must be one this server actually reported, never a path a client
    # invented — otherwise this endpoint would rewrite any file on the box.
    current = await php_service.read(server)
    known = {s["config"] for s in current.get("sites", [])}
    if body.config not in known:
        raise HTTPException(
            status_code=422,
            detail="That site's configuration was not found on this server. Reload the page "
                   "and try again.")
    if version not in current.get("versions", []):
        raise HTTPException(
            status_code=422,
            detail=f"PHP {version} is not installed on this server. Install it first.")

    cmd = php_service.build_switch_command(body.config, version, body.domain)
    out, err, code = await connection_manager.execute(server, cmd)
    ok, message = php_service.explain_switch(code, out or err)

    await audit_service.audit(
        db, current_user, "php.site_switched" if ok else "php.site_switch_failed",
        target_type="server", target_id=server_id,
        meta={"config": body.config, "version": version, "ok": ok})

    if not ok:
        # 409, not 500: nothing is broken — the change was refused or undone.
        raise HTTPException(status_code=409, detail=message)
    return {"ok": True, "message": message, "php": await php_service.read(server)}
