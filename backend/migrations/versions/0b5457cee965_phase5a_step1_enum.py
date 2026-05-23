"""Phase 5A step 1: add past_due to subscription_status enum

Revision ID: 0b5457cee965
Revises: ff232ea503f4
Create Date: 2026-02-13 11:15:00.000000

Note: ALTER TYPE ADD VALUE must be committed before the new value
can be used in indexes or queries. This is split into a separate
migration for that reason.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0b5457cee965"
down_revision: Union[str, None] = "ff232ea503f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE subscription_status ADD VALUE IF NOT EXISTS 'past_due' BEFORE 'cancelled'")


def downgrade() -> None:
    # Cannot remove enum value in PostgreSQL
    pass
