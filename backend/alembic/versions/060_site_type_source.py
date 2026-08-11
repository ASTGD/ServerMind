"""Who decided what this site is — a scan, or the person who owns it.

`app_type` already carries the answer and everything reads it, so the choice lands THERE
rather than in a second field that 72 call sites would have to learn about. What is new is
only who put it there, because that is what decides whether the next scan may change it.

Detection fills a gap. It does not overrule somebody who told us what their site is.

Revision ID: 060
Revises: 059
"""
import sqlalchemy as sa
from alembic import op

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 'detected' | 'chosen'. Every existing row is 'detected', which is true: until now a
    # scan was the only thing that could set a type.
    op.add_column("sites", sa.Column("type_source", sa.String(20), nullable=False,
                                     server_default="detected"))


def downgrade() -> None:
    op.drop_column("sites", "type_source")
