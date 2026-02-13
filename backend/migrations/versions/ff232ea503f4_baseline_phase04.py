"""Baseline Phase 0-4 schema

Revision ID: ff232ea503f4
Revises:
Create Date: 2026-02-12 19:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ff232ea503f4"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline: DB already has Phase 0-4 schema.
    # This file exists only to restore Alembic revision tracking.
    pass


def downgrade() -> None:
    # Cannot downgrade baseline
    pass
