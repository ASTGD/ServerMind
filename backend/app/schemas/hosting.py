"""Pydantic schemas for Hosting Mode (control panel operations)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Website(BaseModel):
    domain: str
    state: str | None = None
    php: str | None = None
    admin: str | None = None
    type: str | None = None
    id: int | str | None = None


class Database(BaseModel):
    db_name: str | None = None
    size: int | str | None = None


class EmailAccount(BaseModel):
    email: str | None = None
    domain: str | None = None


class CreateWebsiteBody(BaseModel):
    domain: str = Field(min_length=3)
    email: str | None = None
    package: str | None = None
    php: str | None = None
    owner: str | None = None


class CreateDatabaseBody(BaseModel):
    domain: str | None = None       # required by CyberPanel
    db_name: str = Field(min_length=1)
    db_user: str | None = None
    db_password: str | None = None


class CreateEmailBody(BaseModel):
    user: str = Field(min_length=1)
    domain: str = Field(min_length=3)
    password: str = Field(min_length=1)


class ActionResult(BaseModel):
    status: str
    detail: dict | None = None
