"""mail health per domain — will this domain's email actually arrive

Revision ID: 052
Revises: 051
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sites.id", ondelete="CASCADE")),
        sa.Column("domain", sa.String(253), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("verdict", sa.String(12), server_default="unknown"),
        sa.Column("score", sa.Integer, server_default="0"),
        sa.Column("findings", postgresql.JSONB),
        sa.Column("summary", sa.Text),
        sa.Column("has_mx", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("spf", sa.Text),
        sa.Column("dkim_selector", sa.String(64)),
        sa.Column("dmarc", sa.Text),
        sa.Column("sending_ip", sa.String(45)),
        sa.Column("last_checked", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_mail_health_user_id", "mail_health", ["user_id"])
    op.create_index("ix_mail_health_domain", "mail_health", ["domain"])
    op.create_index("ix_mail_health_last_checked", "mail_health", ["last_checked"])
    # One row per domain per customer — this is a current state, not a log.
    op.create_unique_constraint("uq_mail_health_user_domain", "mail_health",
                                ["user_id", "domain"])


def downgrade() -> None:
    op.drop_constraint("uq_mail_health_user_domain", "mail_health", type_="unique")
    op.drop_index("ix_mail_health_last_checked", table_name="mail_health")
    op.drop_index("ix_mail_health_domain", table_name="mail_health")
    op.drop_index("ix_mail_health_user_id", table_name="mail_health")
    op.drop_table("mail_health")
