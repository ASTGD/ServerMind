"""server setups — one-button provisioning of a fresh server

Revision ID: 050
Revises: 049
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "server_setups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("server_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("steps", postgresql.JSONB),
        sa.Column("current", sa.Integer, server_default="0"),
        sa.Column("failed_step", sa.String(120)),
        sa.Column("message", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_server_setups_server_id", "server_setups", ["server_id"])


def downgrade() -> None:
    op.drop_index("ix_server_setups_server_id", table_name="server_setups")
    op.drop_table("server_setups")
