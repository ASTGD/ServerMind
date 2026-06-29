"""encrypt secret-named values in playbook_runs.variables_used

Backfills existing install records so credentials the user typed (DB_PASS,
ADMIN_PASSWORD, …) are encrypted at rest with the same AES-256-GCM used for SSH creds.
Idempotent (skips already-encrypted values).

Revision ID: 017
Revises: 016
"""
from __future__ import annotations

import json
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.secret_vars import encrypt_variables, is_secret

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, variables_used FROM playbook_runs WHERE variables_used IS NOT NULL")
    ).fetchall()
    for row in rows:
        rid, vars_used = row[0], row[1]
        if isinstance(vars_used, str):
            try:
                vars_used = json.loads(vars_used)
            except (ValueError, TypeError):
                continue
        if not isinstance(vars_used, dict) or not any(is_secret(k) for k in vars_used):
            continue
        enc = encrypt_variables(vars_used)  # idempotent — leaves already-encrypted values
        conn.execute(
            sa.text("UPDATE playbook_runs SET variables_used = CAST(:v AS jsonb) WHERE id = :id"),
            {"v": json.dumps(enc), "id": str(rid)},
        )


def downgrade() -> None:
    # No safe automatic downgrade — leaving secrets encrypted is the secure default.
    pass
