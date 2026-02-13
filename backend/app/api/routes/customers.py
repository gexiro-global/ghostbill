"""
Customer API routes.

POST  /v1/customers         — Create customer (auth required)
GET   /v1/customers         — List customers (auth required)
GET   /v1/customers/{id}    — Get customer detail (auth required)
PATCH /v1/customers/{id}    — Update customer (auth required)
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_merchant
from app.db.models import Merchant
from app.db.session import get_db
from app.services.customer_service import (
    CustomerConflictError,
    CustomerNotFoundError,
    CustomerValidationError,
    customer_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customers", tags=["customers"])


# ─── Request / Response schemas ──────────────────────────────────────────────


class CustomerCreateRequest(BaseModel):
    external_id: str | None = Field(
        default=None, max_length=255, description="Your system's customer ID"
    )
    email: str | None = Field(
        default=None, max_length=255, description="Customer email"
    )
    metadata: dict | None = Field(
        default=None, description="Arbitrary metadata (JSONB)"
    )


class CustomerUpdateRequest(BaseModel):
    external_id: str | None = Field(
        default=None, max_length=255, description="Your system's customer ID"
    )
    email: str | None = Field(
        default=None, max_length=255, description="Customer email"
    )
    metadata: dict | None = Field(
        default=None, description="Arbitrary metadata (JSONB)"
    )


class CustomerResponse(BaseModel):
    id: str
    merchant_id: str
    external_id: str | None
    email: str | None
    metadata: dict | None
    created_at: str


class CustomerListResponse(BaseModel):
    customers: list[CustomerResponse]
    total: int
    limit: int
    offset: int


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _customer_to_response(customer) -> CustomerResponse:
    return CustomerResponse(
        id=str(customer.id),
        merchant_id=str(customer.merchant_id),
        external_id=customer.external_id,
        email=customer.email,
        metadata=customer.metadata_json,
        created_at=customer.created_at.isoformat(),
    )


# ─── Routes ──────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer(
    body: CustomerCreateRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new customer for the authenticated merchant."""
    try:
        customer = await customer_service.create_customer(
            db=db,
            merchant_id=merchant.id,
            external_id=body.external_id,
            email=body.email,
            metadata=body.metadata,
        )
        await db.commit()
    except CustomerValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except CustomerConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return _customer_to_response(customer)


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List customers for the authenticated merchant."""
    customers, total = await customer_service.list_customers(
        db=db,
        merchant_id=merchant.id,
        limit=limit,
        offset=offset,
    )
    return CustomerListResponse(
        customers=[_customer_to_response(c) for c in customers],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: uuid.UUID,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Get a single customer by ID."""
    try:
        customer = await customer_service.get_customer(
            db=db, merchant_id=merchant.id, customer_id=customer_id
        )
    except CustomerNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )
    return _customer_to_response(customer)


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: uuid.UUID,
    body: CustomerUpdateRequest,
    merchant: Merchant = Depends(get_current_merchant),
    db: AsyncSession = Depends(get_db),
):
    """Update a customer (PATCH — only provided fields are changed)."""
    # Build kwargs: only include fields that were explicitly sent
    kwargs = {}
    raw = body.model_dump(exclude_unset=True)
    if "external_id" in raw:
        kwargs["external_id"] = body.external_id
    if "email" in raw:
        kwargs["email"] = body.email
    if "metadata" in raw:
        kwargs["metadata"] = body.metadata

    if not kwargs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update.",
        )

    try:
        customer = await customer_service.update_customer(
            db=db,
            merchant_id=merchant.id,
            customer_id=customer_id,
            **kwargs,
        )
        await db.commit()
    except CustomerNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )
    except CustomerValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except CustomerConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    return _customer_to_response(customer)
