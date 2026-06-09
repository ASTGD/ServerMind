"""Pydantic schemas for file manager operations."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FileEntry(BaseModel):
    """One item in a directory listing."""

    name: str
    path: str
    type: str          # "file" | "dir" | "link"
    size: int | None
    permissions: str
    modified: datetime | None
    is_binary: bool = False

    model_config = {"from_attributes": True}


class DirectoryListing(BaseModel):
    """Response for a directory listing request."""

    path: str
    parent_path: str | None
    entries: list[FileEntry]


class FileContent(BaseModel):
    """Response for a file read request."""

    path: str
    content: str
    is_binary: bool
    size: int


class FileWriteBody(BaseModel):
    """Request body for writing (saving) a file."""

    path: str
    content: str


class FileMkdirBody(BaseModel):
    """Request body for creating a directory."""

    path: str


class FileRenameBody(BaseModel):
    """Request body for renaming or moving a file/directory."""

    old_path: str
    new_path: str
