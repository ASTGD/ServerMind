"""deploy targets + runs — releases/symlink deployments with rollback

Revision ID: 049
Revises: 048
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deploy_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("repo", sa.String(500), nullable=False),
        sa.Column("branch", sa.String(120), nullable=False, server_default="main"),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False, server_default="production"),
        sa.Column("shared_paths", postgresql.JSONB),
        sa.Column("build_commands", postgresql.JSONB),
        sa.Column("after_commands", postgresql.JSONB),
        sa.Column("auto_deploy", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("webhook_secret", sa.Text, nullable=False),
        sa.Column("keep_releases", sa.Integer, nullable=False, server_default="5"),
        sa.Column("current_release", sa.String(40)),
        sa.Column("last_status", sa.String(20)),
        sa.Column("last_deployed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_deploy_targets_user_id", "deploy_targets", ["user_id"])
    op.create_index("ix_deploy_targets_server_id", "deploy_targets", ["server_id"])
    # One target per folder per server. Two targets deploying into the same directory
    # would race each other's symlink and produce a release nobody asked for.
    op.create_unique_constraint("uq_deploy_target_server_path",
                                "deploy_targets", ["server_id", "path"])

    op.create_table(
        "deploy_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("target_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("deploy_targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("release", sa.String(40)),
        sa.Column("kind", sa.String(20), server_default="deploy"),
        sa.Column("trigger", sa.String(20), server_default="manual"),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("failed_step", sa.String(120)),
        sa.Column("log", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_deploy_runs_target_id", "deploy_runs", ["target_id"])
    op.create_index("ix_deploy_runs_started_at", "deploy_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_deploy_runs_started_at", table_name="deploy_runs")
    op.drop_index("ix_deploy_runs_target_id", table_name="deploy_runs")
    op.drop_table("deploy_runs")
    op.drop_constraint("uq_deploy_target_server_path", "deploy_targets", type_="unique")
    op.drop_index("ix_deploy_targets_server_id", table_name="deploy_targets")
    op.drop_index("ix_deploy_targets_user_id", table_name="deploy_targets")
    op.drop_table("deploy_targets")
