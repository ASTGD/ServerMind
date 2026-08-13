"""File Manager router — SFTP-backed remote file operations."""
from __future__ import annotations

import logging
import posixpath
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies.access import resolve_server
from app.models.server import Server
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.files import (
    DirectoryListing,
    FileContent,
    FileEntry,
    FileMkdirBody,
    FileRenameBody,
    FileWriteBody,
)
from app.services import file_service

router = APIRouter(prefix="/api", tags=["files"])
logger = logging.getLogger(__name__)

DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_server(
    server_id: str, user: User, db: AsyncSession, *, need_execute: bool = False
) -> Server:
    """Resolve a server the user can access. Mutations require execute rights."""
    return await resolve_server(server_id, user, db, need_execute=need_execute)


def _sftp_exc(exc: Exception) -> HTTPException:
    """Map a Paramiko / SFTP error into an HTTP exception."""
    msg = str(exc)
    if "No such file" in msg or "does not exist" in msg.lower():
        return HTTPException(status_code=404, detail=f"Path not found: {msg}")
    if "Permission denied" in msg:
        return HTTPException(status_code=403, detail=f"Permission denied: {msg}")
    return HTTPException(status_code=500, detail=f"SFTP error: {msg}")


# ── List directory ────────────────────────────────────────────────────────────

@router.get("/servers/{server_id}/files", response_model=DirectoryListing)
async def list_directory(
    server_id: str,
    db: DBDep,
    current_user: CurrentUser,
    path: str = Query(default="/"),
    show_hidden: bool = Query(default=False),
) -> DirectoryListing:
    """List the contents of a remote directory."""
    server = await _get_server(server_id, current_user, db)
    try:
        raw = await file_service.list_dir(server, path, show_hidden)
    except Exception as exc:
        raise _sftp_exc(exc)

    normed = posixpath.normpath("/" + path.lstrip("/"))
    parent = posixpath.dirname(normed) if normed != "/" else None

    return DirectoryListing(
        path=normed,
        parent_path=parent,
        entries=[FileEntry(**e) for e in raw],
    )


# ── Read file ─────────────────────────────────────────────────────────────────

@router.get("/servers/{server_id}/files/read", response_model=FileContent)
async def read_file(
    server_id: str,
    db: DBDep,
    current_user: CurrentUser,
    path: str = Query(...),
) -> FileContent:
    """Read a remote file for the in-browser editor (max 2 MB)."""
    server = await _get_server(server_id, current_user, db)
    try:
        result = await file_service.read_file(server, path)
    except Exception as exc:
        raise _sftp_exc(exc)
    return FileContent(path=path, **result)


# ── Write file ────────────────────────────────────────────────────────────────

@router.post("/servers/{server_id}/files/write")
async def write_file(
    server_id: str,
    body: FileWriteBody,
    db: DBDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Save edited content back to a remote file."""
    server = await _get_server(server_id, current_user, db, need_execute=True)
    try:
        await file_service.write_file(server, body.path, body.content)
    except Exception as exc:
        raise _sftp_exc(exc)
    return {"status": "saved", "path": body.path}


# ── Create directory ──────────────────────────────────────────────────────────

@router.post("/servers/{server_id}/files/mkdir", status_code=201)
async def make_directory(
    server_id: str,
    body: FileMkdirBody,
    db: DBDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Create a new remote directory."""
    server = await _get_server(server_id, current_user, db, need_execute=True)
    try:
        await file_service.make_dir(server, body.path)
    except Exception as exc:
        raise _sftp_exc(exc)
    return {"status": "created", "path": body.path}


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/servers/{server_id}/files", status_code=204)
async def delete_path(
    server_id: str,
    db: DBDep,
    current_user: CurrentUser,
    path: str = Query(...),
) -> None:
    """Delete a remote file or directory tree."""
    server = await _get_server(server_id, current_user, db, need_execute=True)
    try:
        await file_service.delete_path(server, path)
    except Exception as exc:
        raise _sftp_exc(exc)


# ── Rename / move ─────────────────────────────────────────────────────────────

@router.post("/servers/{server_id}/files/rename")
async def rename_path(
    server_id: str,
    body: FileRenameBody,
    db: DBDep,
    current_user: CurrentUser,
) -> dict[str, str]:
    """Rename or move a remote file/directory."""
    server = await _get_server(server_id, current_user, db, need_execute=True)
    try:
        await file_service.rename_path(server, body.old_path, body.new_path)
    except Exception as exc:
        raise _sftp_exc(exc)
    return {"status": "renamed", "new_path": body.new_path}


# ── Upload ────────────────────────────────────────────────────────────────────

#: What one upload may carry. Deliberately below the proxy's own limit, so a file that is
#: too big gets THIS message rather than the web server's raw "413" page.
MAX_UPLOAD_BYTES = 64 * 1024 * 1024


def refuse_if_too_big(size: int | None, limit: int | None = None) -> None:
    """One rule, applied at two moments.

    Called first with the size the client DECLARED, before the body is read — because the
    body is read into memory here, and refusing after reading still costs the allocation
    the limit exists to prevent. Then again with the bytes actually received, because a
    client is free to under-report, or not report at all.

    An unknown size is allowed through to the second check rather than refused: plenty of
    clients omit a per-part length, and rejecting every one of those would break ordinary
    uploads to stop a rare one.
    """
    # Read here, not bound as a default argument: a module constant captured in the
    # signature is fixed at import and cannot be changed afterwards — including by a test.
    limit = MAX_UPLOAD_BYTES if limit is None else limit
    if size is not None and size > limit:
        mb = limit // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=(f"That file is {size // (1024 * 1024)} MB, and uploads here are limited "
                    f"to {mb} MB. For something larger, copy it onto the server directly."))


@router.post("/servers/{server_id}/files/upload", status_code=201)
async def upload_file(
    server_id: str,
    db: DBDep,
    current_user: CurrentUser,
    path: str = Form(...),
    file: UploadFile = File(...),
    # `size` is an int, so the response type has to admit one. Declaring `dict[str, str]`
    # made FastAPI reject our OWN response — and it did so AFTER the file had already been
    # written, so every upload succeeded on the server and reported HTTP 500 to the
    # customer. A failure that is really a success is the worst kind: it invites a retry.
) -> dict[str, str | int]:
    """Upload a local file into a remote directory (multipart/form-data)."""
    server = await _get_server(server_id, current_user, db, need_execute=True)
    refuse_if_too_big(file.size)
    data = await file.read()
    refuse_if_too_big(len(data))
    dest = posixpath.join(
        posixpath.normpath("/" + path.lstrip("/")),
        file.filename or "upload",
    )
    try:
        await file_service.upload_file(server, dest, data)
    except Exception as exc:
        raise _sftp_exc(exc)
    return {"status": "uploaded", "path": dest, "size": len(data)}


# ── Download ──────────────────────────────────────────────────────────────────

@router.get("/servers/{server_id}/files/download")
async def download_file(
    server_id: str,
    db: DBDep,
    current_user: CurrentUser,
    path: str = Query(...),
) -> Response:
    """Download a remote file as a binary octet-stream."""
    server = await _get_server(server_id, current_user, db)
    try:
        data = await file_service.download_file(server, path)
    except Exception as exc:
        raise _sftp_exc(exc)

    filename = posixpath.basename(path) or "download"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
