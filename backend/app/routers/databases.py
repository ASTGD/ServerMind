"""Databases on a server — see them, add one, remove one.

Read on every request rather than kept in a table. A cached list drifts from what the
server actually has the moment anything else touches it — an installer, a migration, the
customer over SSH — and a database shown as present when it is gone is worse than
showing nothing, because someone will point an application at it.

Creating and deleting both need execute permission (Rule 7). Deleting is the most
destructive thing on this screen: there is no copy of a dropped database anywhere in this
system, so it is guarded by the typed name matching, not by a dialog someone clicks
through.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import audit_service, database_service as dbs

router = APIRouter(prefix="/api/servers/{server_id}/databases", tags=["databases"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


class CreateIn(BaseModel):
    engine: str = Field(max_length=20)
    name: str = Field(max_length=63)
    user: str = Field(max_length=63)
    # Which machine the application runs on. Defaults to this one, which is what every
    # database made before this existed used and what a site on the same server needs.
    host: str = Field(default="localhost", max_length=64)
    # Never echoed back and never stored. The customer chose it and is about to paste it
    # into an application's configuration; a second copy here would only be another place
    # for it to leak from.
    password: str = Field(max_length=200)


class DropIn(BaseModel):
    # The host is part of a MySQL user's identity, so removing one created for another
    # machine needs the same address it was created with.
    host: str = Field(default="localhost", max_length=64)
    engine: str = Field(max_length=20)
    name: str = Field(max_length=63)
    confirm_name: str = Field(max_length=63)
    drop_user: str | None = Field(default=None, max_length=63)


def _supported(server) -> None:
    """Windows and hosting panels are not this screen's job, and should say so plainly."""
    if server.connection_type != "ssh":
        raise HTTPException(
            400,
            "This screen manages databases on a Linux server over SSH. A hosting panel "
            "manages its own databases — use its own screen for those.",
        )



async def _check_reachable(server, host: str, current_user, db: AsyncSession) -> str:
    """The address has to be one of the customer's OWN servers.

    The same rule the database-server firewall follows, deliberately: allowing a user from
    an address the firewall blocks produces a login that can never work, and allowing one
    from an address that is not theirs is how a database ends up reachable by a stranger.

    Anything else is refused with the reason, rather than accepted and silently useless.
    """
    import re as _re

    from app.models.server import Server as _Server

    host = (host or "").strip()
    if not host or host == "localhost":
        return "localhost"
    rows = (await db.execute(
        select(_Server).where(_Server.user_id == current_user.id,
                              _Server.id != server.id))).scalars().all()
    mine = {(r.host or "").strip() for r in rows}
    if host in mine:
        return host
    if _re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        raise HTTPException(
            422, f"{host} is not one of your servers. A database user can only be allowed "
                 f"from a server in your own account — the firewall would refuse anything "
                 f"else anyway.")
    raise HTTPException(422, f"“{host}” is not an address of one of your servers.")


@router.get("")
async def list_databases(server_id: str, current_user: CurrentUser, db: DBDep) -> dict:
    """What database engines are installed here, and what is in them."""
    server = await resolve_server(server_id, current_user, db)
    _supported(server)
    out = await dbs.list_databases(server)
    # So the create form can offer "which machine will connect" without the customer
    # having to know any addresses — and can only offer ones that will actually work.
    import re as _re

    from app.models.server import Server as _Server
    rows = (await db.execute(
        select(_Server).where(_Server.user_id == current_user.id,
                              _Server.id != server.id))).scalars().all()
    out["own_servers"] = [
        {"name": r.name, "host": (r.host or "").strip()} for r in rows
        if _re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", (r.host or "").strip())]
    return out


@router.post("", status_code=201)
async def create_database(server_id: str, body: CreateIn,
                          current_user: CurrentUser, db: DBDep) -> dict:
    """Create a database and a user with rights to that one database only."""
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    _supported(server)
    try:
        host = await _check_reachable(server, body.host, current_user, db)
        result = await dbs.create_database(
            server, engine=body.engine, db_name=body.name,
            user=body.user, password=body.password, host=host)
    except dbs.DatabaseError as exc:
        raise HTTPException(422, str(exc)) from exc

    # The name and user are recorded; the password deliberately is not, so reading the
    # audit trail can never hand someone a live database credential.
    await audit_service.audit(db, current_user, "database.created",
                              target_type="server", target_id=server_id,
                              meta={"engine": body.engine, "database": result["name"],
                                    "user": result["user"], "host": result["host"]})
    return result


@router.post("/drop")
async def drop_database(server_id: str, body: DropIn,
                        current_user: CurrentUser, db: DBDep) -> dict:
    """Delete a database. Irreversible, and guarded by the typed name."""
    server = await resolve_server(server_id, current_user, db, need_execute=True)
    _supported(server)
    try:
        result = await dbs.drop_database(
            server, engine=body.engine, db_name=body.name,
            confirm_name=body.confirm_name, drop_user=body.drop_user, host=body.host)
    except dbs.DatabaseError as exc:
        raise HTTPException(422, str(exc)) from exc

    await audit_service.audit(db, current_user, "database.dropped",
                              target_type="server", target_id=server_id,
                              meta={"engine": body.engine, "database": result["name"],
                                    "dropped_user": result["dropped_user"]})
    return result
