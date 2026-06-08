"""create playbooks, user_scripts, and playbook_runs tables

Revision ID: 004
Revises: 003
Create Date: 2026-06-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "playbooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(255), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("os_family", sa.String(20), nullable=True),
        sa.Column("script_type", sa.String(20), nullable=True),
        sa.Column("script_bash", sa.Text(), nullable=True),
        sa.Column("script_powershell", sa.Text(), nullable=True),
        sa.Column("variables", JSONB, nullable=True),
        sa.Column("supported_os", ARRAY(sa.String()), nullable=True),
        sa.Column("est_runtime_sec", sa.Integer(), nullable=True),
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("tags", ARRAY(sa.String()), nullable=True),
        sa.Column("version", sa.String(20), nullable=False, server_default="'1.0.0'"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_playbooks_slug", "playbooks", ["slug"])
    op.create_index("ix_playbooks_os_family", "playbooks", ["os_family"])
    op.create_index("ix_playbooks_category", "playbooks", ["category"])

    op.create_table(
        "user_scripts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("script_type", sa.String(20), nullable=True),
        sa.Column("script_content", sa.Text(), nullable=False),
        sa.Column("variables", JSONB, nullable=True),
        sa.Column("source", sa.String(20), nullable=True),
        sa.Column("forked_from", UUID(as_uuid=True), sa.ForeignKey("playbooks.id"), nullable=True),
        sa.Column("tags", ARRAY(sa.String()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_user_scripts_user_id", "user_scripts", ["user_id"])

    op.create_table(
        "playbook_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("server_id", UUID(as_uuid=True), sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("playbook_id", UUID(as_uuid=True), sa.ForeignKey("playbooks.id"), nullable=True),
        sa.Column("user_script_id", UUID(as_uuid=True), sa.ForeignKey("user_scripts.id"), nullable=True),
        sa.Column("variables_used", JSONB, nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_playbook_runs_server_id", "playbook_runs", ["server_id"])
    op.create_index("ix_playbook_runs_user_id", "playbook_runs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_playbook_runs_user_id", table_name="playbook_runs")
    op.drop_index("ix_playbook_runs_server_id", table_name="playbook_runs")
    op.drop_table("playbook_runs")
    op.drop_index("ix_user_scripts_user_id", table_name="user_scripts")
    op.drop_table("user_scripts")
    op.drop_index("ix_playbooks_category", table_name="playbooks")
    op.drop_index("ix_playbooks_os_family", table_name="playbooks")
    op.drop_index("ix_playbooks_slug", table_name="playbooks")
    op.drop_table("playbooks")
