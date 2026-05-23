"""Phase 8B: Pre-payment model.

Add prepay_plans to merchants, prepaid_until + prepay_invoice_id to subscriptions.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merchants: prepay plan configuration
    op.add_column(
        "merchants",
        sa.Column("prepay_plans", JSONB, nullable=True),
    )

    # Subscriptions: prepay tracking
    op.add_column(
        "subscriptions",
        sa.Column("prepaid_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "subscriptions",
        sa.Column(
            "prepay_invoice_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("subscriptions", "prepay_invoice_id")
    op.drop_column("subscriptions", "prepaid_until")
    op.drop_column("merchants", "prepay_plans")
