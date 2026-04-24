"""
Customer business logic — create, update, get, list.

Merchant isolation enforced on every operation.
external_id uniqueness scoped per merchant.
"""

import logging
import re
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Customer

logger = logging.getLogger(__name__)

# ── Sentinel for PATCH (distinguish 'not provided' from 'set to None') ──────

_UNSET = object()

# ── Simple email regex (not exhaustive, just sanity check) ──────────────────

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ── Exceptions ──────────────────────────────────────────────────────────────


class CustomerError(Exception):
    """Base customer service error."""

    pass


class CustomerNotFoundError(CustomerError):
    """Customer does not exist or does not belong to merchant."""

    pass


class CustomerValidationError(CustomerError):
    """Input validation failed."""

    pass


class CustomerConflictError(CustomerError):
    """Duplicate external_id for this merchant."""

    pass


# ── Service ─────────────────────────────────────────────────────────────────


class CustomerService:
    """CRUD for customers. Merchant isolation enforced on every operation."""

    @staticmethod
    def _validate_email(email: str | None) -> None:
        """Validate email format if provided."""
        if email is not None and not _EMAIL_RE.match(email):
            raise CustomerValidationError(f"Invalid email format: {email!r}")

    async def create_customer(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        external_id: str | None = None,
        email: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Customer:
        """Create new customer for merchant.

        Raises:
            CustomerValidationError: Invalid email format.
            CustomerConflictError: external_id already exists for this merchant.
        """
        self._validate_email(email)

        # Check external_id uniqueness per merchant
        if external_id is not None:
            stmt = select(Customer).where(
                Customer.merchant_id == merchant_id,
                Customer.external_id == external_id,
            )
            existing = (await db.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                raise CustomerConflictError(f"Customer with external_id '{external_id}' already exists.")

        customer = Customer(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            external_id=external_id,
            email=email,
            metadata_json=metadata,
        )
        db.add(customer)
        await db.flush()

        logger.info(
            "Customer created: %s, merchant=%s, external_id=%s",
            customer.id,
            merchant_id,
            external_id,
        )
        return customer

    async def get_customer(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        customer_id: uuid.UUID,
    ) -> Customer:
        """Get single customer. Enforces merchant_id match.

        Raises CustomerNotFoundError if not found.
        """
        stmt = select(Customer).where(
            Customer.id == customer_id,
            Customer.merchant_id == merchant_id,
        )
        customer = (await db.execute(stmt)).scalar_one_or_none()
        if customer is None:
            raise CustomerNotFoundError(f"Customer {customer_id} not found.")
        return customer

    async def list_customers(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Customer], int]:
        """List customers for merchant with pagination.

        Returns (customers_list, total_count).
        """
        limit = max(1, min(limit, 100))
        offset = max(0, offset)

        base_where = [Customer.merchant_id == merchant_id]

        count_stmt = select(func.count(Customer.id)).where(*base_where)
        total = (await db.execute(count_stmt)).scalar_one()

        data_stmt = select(Customer).where(*base_where).order_by(Customer.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(data_stmt)
        customers = list(result.scalars().all())

        return customers, total

    async def update_customer(
        self,
        db: AsyncSession,
        merchant_id: uuid.UUID,
        customer_id: uuid.UUID,
        external_id=_UNSET,
        email=_UNSET,
        metadata=_UNSET,
    ) -> Customer:
        """Partial update (PATCH semantics). Only provided fields are changed.

        Raises:
            CustomerNotFoundError: Not found or wrong merchant.
            CustomerValidationError: Invalid email format.
            CustomerConflictError: external_id already exists for this merchant.
        """
        customer = await self.get_customer(db, merchant_id, customer_id)

        if email is not _UNSET:
            self._validate_email(email)
            customer.email = email

        if external_id is not _UNSET:
            # Check uniqueness if changing
            if external_id is not None and external_id != customer.external_id:
                stmt = select(Customer).where(
                    Customer.merchant_id == merchant_id,
                    Customer.external_id == external_id,
                    Customer.id != customer_id,
                )
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if existing is not None:
                    raise CustomerConflictError(f"Customer with external_id '{external_id}' already exists.")
            customer.external_id = external_id

        if metadata is not _UNSET:
            customer.metadata_json = metadata

        await db.flush()

        logger.info("Customer updated: %s, merchant=%s", customer_id, merchant_id)
        return customer


# ── Module-level instance ───────────────────────────────────────────────────

customer_service = CustomerService()
