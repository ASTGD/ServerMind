"""add totp_recovery_codes to users (2FA recovery / backup codes)

Revision ID: 012
Revises: 011
Create Date: 2026-06-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Stores a JSON array of SHA-256 hashes of one-time recovery codes (never plaintext).
    op.add_column("users", sa.Column("totp_recovery_codes", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "totp_recovery_codes")
