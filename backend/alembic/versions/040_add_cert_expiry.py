"""certificate expiry tracking on uptime_monitors

Revision ID: 040
Revises: 039
Create Date: 2026-07-25

Pro #9 (docs/PRO-FEATURES-PLAN.md). An expired HTTPS certificate takes a site down as
completely as a dead server, and it always announces itself weeks ahead — the most
preventable outage there is. Checked daily against the URL the monitor already watches.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("uptime_monitors", sa.Column("cert_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("uptime_monitors", sa.Column("cert_days_left", sa.Integer(), nullable=True))
    op.add_column("uptime_monitors", sa.Column("cert_issuer", sa.String(length=255), nullable=True))
    op.add_column("uptime_monitors", sa.Column("cert_state", sa.String(length=12), nullable=True))
    op.add_column("uptime_monitors", sa.Column("cert_error", sa.String(length=300), nullable=True))
    op.add_column("uptime_monitors", sa.Column("cert_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("uptime_monitors", sa.Column("cert_warn_days", sa.Integer(), nullable=False, server_default="14"))


def downgrade() -> None:
    for col in ("cert_warn_days", "cert_checked_at", "cert_error", "cert_state",
                "cert_issuer", "cert_days_left", "cert_expires_at"):
        op.drop_column("uptime_monitors", col)
