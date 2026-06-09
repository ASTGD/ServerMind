"""create team_members and server_access tables

Revision ID: 009
Revises: 008
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_members",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
        ),
        sa.Column("role", sa.String(20)),
        sa.Column("invited_email", sa.String(255)),
        sa.Column("invite_token", sa.String(255)),
        sa.Column("invite_accepted", sa.Boolean, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_team_members_owner_id", "team_members", ["owner_id"])
    op.create_index("ix_team_members_member_id", "team_members", ["member_id"])
    op.create_index("ix_team_members_invite_token", "team_members", ["invite_token"])

    op.create_table(
        "server_access",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "team_member_id",
            UUID(as_uuid=True),
            sa.ForeignKey("team_members.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("can_execute", sa.Boolean, server_default=sa.text("false")),
        sa.Column("can_view_logs", sa.Boolean, server_default=sa.text("true")),
    )
    op.create_index("ix_server_access_team_member_id", "server_access", ["team_member_id"])
    op.create_index("ix_server_access_server_id", "server_access", ["server_id"])


def downgrade() -> None:
    op.drop_index("ix_server_access_server_id", table_name="server_access")
    op.drop_index("ix_server_access_team_member_id", table_name="server_access")
    op.drop_table("server_access")
    op.drop_index("ix_team_members_invite_token", table_name="team_members")
    op.drop_index("ix_team_members_member_id", table_name="team_members")
    op.drop_index("ix_team_members_owner_id", table_name="team_members")
    op.drop_table("team_members")
