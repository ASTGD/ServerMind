"""service monitors — watch a systemd unit, alert on change, optionally restart

Revision ID: 047
Revises: 046
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_monitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("server_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False),

        sa.Column("unit", sa.String(128), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),

        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("failure_threshold", sa.Integer, nullable=False, server_default="2"),

        sa.Column("auto_restart", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("max_restarts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("restart_window_seconds", sa.Integer, nullable=False, server_default="1800"),

        sa.Column("current_status", sa.String(10), nullable=False, server_default="unknown"),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_state", sa.String(20)),
        sa.Column("last_checked", sa.DateTime(timezone=True)),
        sa.Column("last_status_change", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),

        sa.Column("restart_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("restart_window_started", sa.DateTime(timezone=True)),
        sa.Column("last_restart_at", sa.DateTime(timezone=True)),
        sa.Column("gave_up", sa.Boolean, nullable=False, server_default=sa.text("false")),

        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_service_monitors_user_id", "service_monitors", ["user_id"])
    op.create_index("ix_service_monitors_server_id", "service_monitors", ["server_id"])
    op.create_index("ix_service_monitors_last_checked", "service_monitors", ["last_checked"])
    # One monitor per unit per server: watching the same service twice would double every
    # alert it raises, which is the fastest way to get all of them ignored.
    op.create_unique_constraint("uq_service_monitor_server_unit",
                                "service_monitors", ["server_id", "unit"])


def downgrade() -> None:
    op.drop_constraint("uq_service_monitor_server_unit", "service_monitors", type_="unique")
    op.drop_index("ix_service_monitors_last_checked", table_name="service_monitors")
    op.drop_index("ix_service_monitors_server_id", table_name="service_monitors")
    op.drop_index("ix_service_monitors_user_id", table_name="service_monitors")
    op.drop_table("service_monitors")
