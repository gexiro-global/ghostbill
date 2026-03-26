"""Invoice Pydantic schemas — request and response models.

Extracted from invoices.py for maintainability (Phase 6B).
"""

from pydantic import BaseModel, Field


# ─── Request schemas ─────────────────────────────────────────────────────


class InvoiceCreateRequest(BaseModel):
    """Create invoice request."""

    amount_xmr: str = Field(
        ...,
        description="XMR amount as string for precision (e.g. '0.5')",
        examples=["0.5", "1.25"],
    )
    description: str | None = Field(
        default=None,
        max_length=1024,
        description="Invoice description",
    )
    expires_in: int | None = Field(
        default=None,
        ge=600,
        le=86400,
        description="Seconds until expiry (600–86400, default 3600)",
    )
    metadata: dict | None = Field(
        default=None,
        description="Merchant-defined metadata (JSONB)",
    )


# ─── Response schemas ────────────────────────────────────────────────────


class InvoiceResponse(BaseModel):
    id: str
    merchant_id: str
    amount_xmr: str
    amount_atomic: int
    fiat_currency: str | None
    fiat_amount: str | None
    fiat_rate: str | None
    status: str
    description: str | None
    metadata: dict | None
    address: str | None
    address_index: int | None
    expires_at: str
    paid_at: str | None
    created_at: str
    updated_at: str


class InvoiceCursorResponse(BaseModel):
    data: list[InvoiceResponse]
    has_more: bool
