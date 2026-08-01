"""A deploy target can belong to a site.

Deploys were per-SERVER, which answers "put this repo somewhere on that machine" but not
the question anyone actually has — "put my code on THIS website". A site with fifteen
neighbours could not say which of the server's deploys was its own.

Nullable, because a target that is not tied to a site is still perfectly valid: a worker, a
queue consumer, an API with no vhost. ``SET NULL`` rather than ``CASCADE`` for the same
reason removing a channel must not remove its alert rules — forgetting a site should not
silently destroy the deployment history of the code that ran on it.

Revision ID: 056
Revises: 055
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deploy_targets",
                  sa.Column("site_id", sa.dialects.postgresql.UUID(as_uuid=True),
                            nullable=True))
    op.create_foreign_key("deploy_targets_site_id_fkey", "deploy_targets", "sites",
                          ["site_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_deploy_targets_site_id", "deploy_targets", ["site_id"])

    # Where the web server should look once code is deployed. Empty means the repository's
    # own root; "public" is what Laravel, Symfony and most modern PHP frameworks use. It is
    # asked for rather than guessed, because getting it wrong points a live site at the
    # wrong folder.
    op.add_column("deploy_targets",
                  sa.Column("web_dir", sa.String(length=120), nullable=True))
    # Whether the site's own web-server config has actually been pointed at the deployed
    # code. Recorded rather than inferred: a target can exist and have deployed happily
    # while the site still serves its old files, and those are different states.
    op.add_column("deploy_targets",
                  sa.Column("serving", sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("deploy_targets", "serving")
    op.drop_column("deploy_targets", "web_dir")
    op.drop_index("ix_deploy_targets_site_id", table_name="deploy_targets")
    op.drop_constraint("deploy_targets_site_id_fkey", "deploy_targets", type_="foreignkey")
    op.drop_column("deploy_targets", "site_id")
