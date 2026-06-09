"""create server_metrics and alerts tables

Revision ID: 006
Revises: 005
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "server_metrics",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cpu_percent", sa.Numeric(5, 2)),
        sa.Column("ram_percent", sa.Numeric(5, 2)),
        sa.Column("ram_used_mb", sa.Integer),
        sa.Column("ram_total_mb", sa.Integer),
        sa.Column("disk_percent", sa.Numeric(5, 2)),
        sa.Column("disk_used_gb", sa.Numeric(10, 2)),
        sa.Column("disk_total_gb", sa.Numeric(10, 2)),
        sa.Column("load_1", sa.Numeric(6, 3)),
        sa.Column("load_5", sa.Numeric(6, 3)),
        sa.Column("load_15", sa.Numeric(6, 3)),
        sa.Column("uptime_seconds", sa.BigInteger),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_server_metrics_server_id", "server_metrics", ["server_id"])
    op.create_index("ix_server_metrics_recorded_at", "server_metrics", ["recorded_at"])

    op.create_table(
        "alerts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("metric", sa.String(50)),
        sa.Column("condition", sa.String(20)),
        sa.Column("threshold", sa.Numeric(10, 2)),
        sa.Column("channel", sa.String(20)),
        sa.Column("channel_target", sa.String(500)),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("last_triggered", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_alerts_server_id", "alerts", ["server_id"])
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_alerts_user_id", table_name="alerts")
    op.drop_index("ix_alerts_server_id", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("ix_server_metrics_recorded_at", table_name="server_metrics")
    op.drop_index("ix_server_metrics_server_id", table_name="server_metrics")
    op.drop_table("server_metrics")
