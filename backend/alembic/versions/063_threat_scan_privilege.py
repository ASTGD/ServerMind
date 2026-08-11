"""Record what the malware scan was actually able to read.

A scan that could not read the site folders used to report "No threats found" — a false
all-clear on the most safety-critical feature we ship. It now returns `unknown` and names the
checks it could not run, and those two facts have to survive into the history, or the Security
page can only say "not scanned" about a scan that plainly did run.

`privilege` is stored; the sentence shown to the customer is derived from it by
`privilege.explain`, so the wording lives in one place and cannot drift.

Revision ID: 063
Revises: 062
"""
import sqlalchemy as sa
from alembic import op

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Older rows predate the check. They are left NULL rather than back-filled with "root":
    # claiming a past scan had full access is exactly the kind of comfortable guess this
    # whole change exists to stop.
    op.add_column("threat_scans", sa.Column("privilege", sa.String(10), nullable=True))
    op.add_column("threat_scans", sa.Column("skipped", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("threat_scans", "skipped")
    op.drop_column("threat_scans", "privilege")
