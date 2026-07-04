"""Hosting router — control-panel operations for connection_type='hosting'."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.server import Server
from app.models.user import User
from app.schemas.hosting import (
    ActionResult,
    CreateDatabaseBody,
    CreateEmailBody,
    CreateWebsiteBody,
    Database,
    EmailAccount,
    Website,
)
from app.services import hosting_service
from app.services.hosting_service import HostingError

router = APIRouter(prefix="/api/servers/{server_id}/hosting", tags=["hosting"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


async def _hosting_server(server_id: str, user: User, db: AsyncSession, *, need_execute: bool = False) -> Server:
    server = await resolve_server(server_id, user, db, need_execute=need_execute)
    # Hosting endpoints serve a panel connection, OR an SSH server that has a control
    # panel installed (panel_type set) — the latter drives the panel's CLI over SSH (H1).
    if server.connection_type != "hosting" and not (server.connection_type == "ssh" and server.panel_type):
        raise HTTPException(status_code=400, detail="This server is not a hosting account.")
    return server


def _wrap(exc: HostingError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(exc))


# ── Websites ────────────────────────────────────────────────────────────────

@router.get("/websites", response_model=list[Website])
async def list_websites(server_id: str, db: DBDep, current_user: CurrentUser):
    server = await _hosting_server(server_id, current_user, db)
    try:
        return await hosting_service.list_websites(server)
    except HostingError as exc:
        raise _wrap(exc)


@router.post("/websites", response_model=ActionResult, status_code=201)
async def create_website(server_id: str, body: CreateWebsiteBody, db: DBDep, current_user: CurrentUser):
    server = await _hosting_server(server_id, current_user, db, need_execute=True)
    try:
        result = await hosting_service.create_website(server, body.model_dump())
        return ActionResult(status="created", detail=result)
    except HostingError as exc:
        raise _wrap(exc)


@router.delete("/websites/{domain}", response_model=ActionResult)
async def delete_website(server_id: str, domain: str, db: DBDep, current_user: CurrentUser):
    server = await _hosting_server(server_id, current_user, db, need_execute=True)
    try:
        result = await hosting_service.delete_website(server, domain)
        return ActionResult(status="deleted", detail=result)
    except HostingError as exc:
        raise _wrap(exc)


@router.post("/websites/{domain}/ssl", response_model=ActionResult)
async def issue_ssl(server_id: str, domain: str, db: DBDep, current_user: CurrentUser):
    server = await _hosting_server(server_id, current_user, db, need_execute=True)
    try:
        result = await hosting_service.issue_ssl(server, domain)
        return ActionResult(status="issued", detail=result)
    except HostingError as exc:
        raise _wrap(exc)


# ── Databases ───────────────────────────────────────────────────────────────

@router.get("/databases", response_model=list[Database])
async def list_databases(server_id: str, db: DBDep, current_user: CurrentUser):
    server = await _hosting_server(server_id, current_user, db)
    try:
        return await hosting_service.list_databases(server)
    except HostingError as exc:
        raise _wrap(exc)


@router.post("/databases", response_model=ActionResult, status_code=201)
async def create_database(server_id: str, body: CreateDatabaseBody, db: DBDep, current_user: CurrentUser):
    server = await _hosting_server(server_id, current_user, db, need_execute=True)
    try:
        result = await hosting_service.create_database(server, body.model_dump())
        return ActionResult(status="created", detail=result)
    except HostingError as exc:
        raise _wrap(exc)


# ── Email ─────────────────────────────────────────────────────────────────────

@router.get("/email", response_model=list[EmailAccount])
async def list_email(server_id: str, db: DBDep, current_user: CurrentUser, domain: str | None = Query(default=None)):
    server = await _hosting_server(server_id, current_user, db)
    try:
        return await hosting_service.list_email(server, domain)
    except HostingError as exc:
        raise _wrap(exc)


@router.post("/email", response_model=ActionResult, status_code=201)
async def create_email(server_id: str, body: CreateEmailBody, db: DBDep, current_user: CurrentUser):
    server = await _hosting_server(server_id, current_user, db, need_execute=True)
    try:
        result = await hosting_service.create_email(server, body.model_dump())
        return ActionResult(status="created", detail=result)
    except HostingError as exc:
        raise _wrap(exc)
