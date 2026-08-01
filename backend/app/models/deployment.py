"""Deploy targets and their history.

A "target" is one repo deployed to one place on one server. Staging is not a separate
concept in the schema — it is a second target with a different branch and path, which is
exactly what staging is. Modelling it as its own thing would have duplicated every field
to express a difference that is only ever two values.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeployTarget(Base):
    __tablename__ = "deploy_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True)
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="CASCADE"),
        nullable=False, index=True)
    # Which website this deploys, when it deploys one. Nullable because a target with no
    # site is still valid — a worker, a queue consumer, an API behind no vhost. SET NULL so
    # forgetting a site never destroys the history of the code that ran on it.
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo: Mapped[str] = mapped_column(String(500), nullable=False)
    branch: Mapped[str] = mapped_column(String(120), nullable=False, default="main")
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="production")

    shared_paths: Mapped[list | None] = mapped_column(JSONB)
    build_commands: Mapped[list | None] = mapped_column(JSONB)
    after_commands: Mapped[list | None] = mapped_column(JSONB)

    # Push-to-deploy. The secret is what stops the webhook URL being a public deploy
    # button, so it is generated for the owner rather than typed by them.
    auto_deploy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    webhook_secret: Mapped[str] = mapped_column(Text, nullable=False)   # encrypted
    keep_releases: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # Where inside the repository the web server should look. Empty means the repository
    # root; "public" is what Laravel, Symfony and most modern PHP frameworks use.
    web_dir: Mapped[str | None] = mapped_column(String(120))
    # Whether the site's config has actually been pointed at the deployed code. Recorded
    # rather than inferred: a target can have deployed happily while the site still serves
    # its old files, and those are different states.
    serving: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    current_release: Mapped[str | None] = mapped_column(String(40))
    last_status: Mapped[str | None] = mapped_column(String(20))
    last_deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())


class DeployRun(Base):
    __tablename__ = "deploy_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True,
                                          default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deploy_targets.id", ondelete="CASCADE"),
        nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    release: Mapped[str | None] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20), default="deploy")  # deploy | rollback
    trigger: Mapped[str] = mapped_column(String(20), default="manual")  # manual | push
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|success|failed
    # The step it stopped on. Kept separately from the log because "which step failed"
    # is the question actually asked, and finding it in the log is work.
    failed_step: Mapped[str | None] = mapped_column(String(120))
    log: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
