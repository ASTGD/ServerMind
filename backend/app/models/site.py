"""The websites an account runs, discovered from their servers.

**Stored, not discovered on demand.** An agency with fifty servers needs the list to open
instantly and to be searchable across the whole fleet; probing fifty servers on every page load
would take a minute and fail whenever one is offline. So a scan writes here, and the page reads
here.

A site that stops appearing is marked ``gone`` rather than deleted. Deleting would erase the
answer to "when did this disappear?", which during an incident is exactly the question — and a
server that was merely unreachable during a scan must not silently empty someone's inventory.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Where the domain came from. Kept so the UI can be honest about how much we know: an Apache
# `-S` listing gives a name and nothing else, while nginx gives the root and the certificate.
SOURCES = ("nginx", "apache", "openlitespeed", "cyberpanel", "cpanel", "manual")

#: What is running on a site. `app` is a program that keeps running behind a reverse proxy —
#: Node, Python, Go — as opposed to files a web server reads. It is one entry rather than one
#: per runtime because what we can DO for it is the same in every case, and the probe reports
#: which runtime it actually found.
APP_TYPES = ("wordpress", "laravel", "php", "static", "app", "unknown")

#: Where a site is in its life.
#:
#: ``live`` is the only state that claims the site exists on the server, and it is only ever
#: reached by OBSERVING it — a scan found it. An installer exiting 0 is not enough: the same
#: "content, not status" rule the mission verification gate follows, for the same reason.
#:
#: ``installing`` exists because until now a site could only be FOUND, never made. The row is
#: written the moment the customer asks, so there is a record of what was requested, and a
#: failure has somewhere to be explained instead of vanishing.
#: ``removing`` and ``remove_failed`` are their own states rather than a reuse of the
#: install pair. Reusing ``installing`` for a removal is what made a finished removal get
#: judged by the original install's run — the site left the server and stayed on the screen.
STATUSES = ("installing", "live", "failed", "removing", "remove_failed")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Nullable: a customer's website is a real thing whether or not we can log into the
    # machine behind it. A site added by hand — on a host we do not manage — has no server,
    # and that is the case no competitor can serve at all.
    server_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("servers.id", ondelete="SET NULL"), index=True,
        nullable=True
    )

    domain: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(253)), default=list, nullable=False)
    doc_root: Mapped[str | None] = mapped_column(String(500))

    source: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    app_type: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(40))
    # Whether the web server config references a certificate — NOT whether it is valid or
    # unexpired. Expiry is the uptime monitor's job, checked from outside where a visitor is.
    has_ssl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # False once a scan stops finding it. Never deleted — see the module docstring.
    is_present: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    #: See STATUSES. Defaults to ``live`` because every row that existed before this column
    #: got there by being discovered, which is exactly what live means.
    status: Mapped[str] = mapped_column(String(20), default="live", nullable=False,
                                        server_default="live")
    #: Why the install failed, in words the customer can act on. Kept on the row rather than
    #: only in a run log, because "I asked for a site and nothing happened" is answered here.
    install_error: Mapped[str | None] = mapped_column(String(500))
    #: The playbook run doing the work, so the UI can show live progress and, afterwards,
    #: exactly what was executed.
    install_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("playbook_runs.id", ondelete="SET NULL"), nullable=True
    )
    #: What the customer chose to put here ("wordpress", "laravel", "nextcloud"…).
    #:
    #: Distinct from `app_type`, which is what a SCAN concluded. Keeping both is what lets us
    #: say "you asked for WordPress and what is actually there is a plain PHP site" — a
    #: single field would have to pick one and silently lose the other.
    requested_type: Mapped[str | None] = mapped_column(String(30))

    #: Who decided what `app_type` says: a scan, or the person who owns the site.
    #:
    #: Detection is better than asking WHEN IT WORKS, and has nothing to fall back on when
    #: it does not — a site we cannot name stays `unknown` for ever and gets no application
    #: section at all. So the owner can say what it is, and that answer lives in `app_type`
    #: like any other, because everything already reads that field.
    #:
    #: This exists for one rule: **a scan may fill a gap, but it may not overrule a person.**
    #: Without it the next discovery run would quietly undo the choice, and the customer
    #: would watch their setting revert for no visible reason.
    type_source: Mapped[str] = mapped_column(String(20), nullable=False,
                                             server_default="detected", default="detected")

    # ── Staging ──────────────────────────────────────────────────────────────
    #
    # A staging site is an ORDINARY site row plus these three facts. That is the design:
    # every screen already built works on it the day it exists, rather than a second kind of
    # thing with its own half of each feature.
    #
    # SET NULL, never CASCADE. Deleting the live site must leave the copy standing — it is a
    # real website with real files, and cascading would delete somebody's work as a side
    # effect of tidying up. It simply stops being staging.
    parent_site_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True, index=True)
    environment: Mapped[str] = mapped_column(String(20), default="production",
                                             nullable=False)
    #: Whether the vhost sends `X-Robots-Tag: noindex`. A header rather than a robots.txt
    #: file — see `robots_service`: robots.txt does not stop a page being indexed, and a
    #: file inside the site is overwritten by the next deploy.
    no_index: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # One row per domain per server. The same domain CAN legitimately exist on two servers
        # (a migration in progress, a staging copy), so the constraint is not global.
        UniqueConstraint("server_id", "domain", name="uq_site_server_domain"),
        Index("ix_sites_user_domain", "user_id", "domain"),
    )
