"""Wave 5 fixtures.

These tests create setup state directly, then exercise production services for behavior.
Direct DB helpers in this file are SETUP-ONLY or cleanup-only.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.core.security import generate_api_key, hash_api_key
from app.db.models import (
    ApiKey,
    AuditLog,
    Customer,
    Invoice,
    InvoiceAddress,
    InvoiceStatus,
    Merchant,
    Payment,
    Subscription,
    SubscriptionPayment,
    SubscriptionRenewalEvent,
    SubscriptionStatus,
    WalletShard,
    WebhookDeadLetter,
    WebhookDelivery,
)
from app.services.payment_service import payment_service
from app.services.webhook_service import webhook_service

# NullPool: each test gets fresh connections, no stale event-loop references
_test_engine = create_async_engine(settings.database_url, echo=False, poolclass=NullPool)

BASE_URL = os.getenv("GHOSTBILL_TEST_URL", "http://127.0.0.1:8000")
PICONERO = 10**12

_test_session_factory = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Fresh SQLAlchemy session for service-level tests."""
    async with _test_session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client for Wave 5 integration tests."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as c:
        yield c


def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def fake_tx_hash() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


def atomic_to_decimal(amount_atomic: int) -> Decimal:
    return Decimal(amount_atomic) / Decimal(PICONERO)


def wallet_tx(
    *,
    account_index: int,
    address_index: int,
    tx_hash: str | None = None,
    amount_atomic: int,
    confirmations: int,
    block_height: int | None = 100,
) -> dict[str, Any]:
    return {
        "txid": tx_hash or fake_tx_hash(),
        "amount": amount_atomic,
        "subaddr_index": {"major": account_index, "minor": address_index},
        "confirmations": confirmations,
        "height": block_height or 0,
        "type": "pool" if confirmations == 0 else "in",
    }


async def process_transfer_and_dispatch(
    db: AsyncSession,
    *,
    account_index: int,
    address_index: int,
    amount_atomic: int,
    confirmations: int,
    tx_hash: str | None = None,
    block_height: int | None = 100,
):
    """Exercise the production detection path: PaymentService plus webhook event decision/queue."""
    tx = wallet_tx(
        account_index=account_index,
        address_index=address_index,
        tx_hash=tx_hash,
        amount_atomic=amount_atomic,
        confirmations=confirmations,
        block_height=block_height,
    )
    invoice = await payment_service.find_invoice_by_subaddress_index(db, account_index, address_index)
    old_invoice_status = invoice.status if invoice is not None else None
    existing = await payment_service.find_payment_by_tx_hash(db, tx["txid"])
    old_payment_status = existing.status if existing is not None else None

    payment = await payment_service.process_transfer(db, tx, tx["type"] == "pool")
    if payment is not None and invoice is not None:
        await db.refresh(invoice)
        events = payment_service.determine_webhook_events(
            payment=payment,
            invoice=invoice,
            old_invoice_status=old_invoice_status,
            old_payment_status=old_payment_status,
        )
        if events:
            merchant = await db.get(Merchant, invoice.merchant_id)
            if merchant is not None:
                await webhook_service.dispatch_events(db, events, merchant, invoice, payment)
    await db.flush()
    return payment


async def handle_reorg_and_dispatch(db: AsyncSession, payment: Payment) -> None:
    invoice = await db.get(Invoice, payment.invoice_id)
    old_invoice_status = invoice.status if invoice is not None else InvoiceStatus.pending
    old_payment_status = payment.status
    await payment_service.handle_reorg(db, payment)
    if invoice is not None:
        await db.refresh(invoice)
        events = payment_service.determine_webhook_events(payment, invoice, old_invoice_status, old_payment_status)
        if events:
            merchant = await db.get(Merchant, invoice.merchant_id)
            if merchant is not None:
                await webhook_service.dispatch_events(db, events, merchant, invoice, payment)
    await db.flush()


async def create_test_merchant(db: AsyncSession, *, webhook_url: str | None = "https://example.com/webhook") -> dict:
    """SETUP-ONLY: create an isolated merchant, API key, and wallet shard."""
    merchant_id = uuid.uuid4()
    raw_key = generate_api_key("live")
    merchant = Merchant(
        id=merchant_id,
        name=f"Wave5_{uuid.uuid4().hex[:8]}",
        email="wave5@ghostbill.local",
        monero_address="4" + uuid.uuid4().hex + uuid.uuid4().hex + uuid.uuid4().hex[:30],
        view_key_encrypted="test_encrypted_view_key",
        webhook_url=webhook_url,
        webhook_secret=f"whsec_{uuid.uuid4().hex}",
        environment="test",
    )
    db.add(merchant)
    db.add(
        ApiKey(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            key_hash=hash_api_key(raw_key),
            key_prefix=raw_key[:16],
            label="wave5",
            environment="live",
        )
    )
    db.add(WalletShard(id=uuid.uuid4(), merchant_id=merchant_id, account_index=0, next_address_index=1))
    await db.commit()
    return {
        "merchant": merchant,
        "merchant_id": merchant_id,
        "api_key": raw_key,
        "webhook_secret": merchant.webhook_secret,
        "account_index": 0,
    }


@pytest_asyncio.fixture
async def service_merchant(db_session: AsyncSession) -> AsyncIterator[dict]:
    merchant = await create_test_merchant(db_session)
    try:
        yield merchant
    finally:
        await cleanup_merchant(db_session, merchant["merchant_id"])


async def create_test_invoice(
    db: AsyncSession,
    merchant_id: uuid.UUID,
    amount_atomic: int = PICONERO,
    *,
    status: InvoiceStatus = InvoiceStatus.pending,
    expires_at: datetime | None = None,
    address_index: int | None = None,
    metadata: dict | None = None,
) -> Invoice:
    """SETUP-ONLY: create invoice/address rows without wallet RPC."""
    invoice_id = uuid.uuid4()
    idx = address_index if address_index is not None else int(uuid.uuid4().int % 1_000_000_000) + 10_000
    invoice = Invoice(
        id=invoice_id,
        merchant_id=merchant_id,
        amount_atomic=amount_atomic,
        amount_xmr=atomic_to_decimal(amount_atomic),
        status=status,
        description="Wave 5 service invoice",
        metadata_json=metadata,
        expires_at=expires_at or datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(invoice)
    db.add(
        InvoiceAddress(
            id=uuid.uuid4(),
            invoice_id=invoice_id,
            account_index=0,
            address_index=idx,
            address="8" + uuid.uuid4().hex + uuid.uuid4().hex + uuid.uuid4().hex[:30],
        )
    )
    await db.commit()
    await db.refresh(invoice, attribute_names=["address"])
    # Cache for async-safe access (avoids MissingGreenlet on lazy load)
    invoice._test_addr_idx = idx
    return invoice


async def create_test_subscription(
    db: AsyncSession,
    merchant_id: uuid.UUID,
    *,
    status: SubscriptionStatus = SubscriptionStatus.active,
    next_due_at: datetime | None = None,
) -> tuple[Customer, Subscription]:
    """SETUP-ONLY: create customer/subscription rows for subscription service tests."""
    customer = Customer(id=uuid.uuid4(), merchant_id=merchant_id, email=f"{uuid.uuid4().hex}@example.test")
    now = datetime.now(timezone.utc)
    sub = Subscription(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        customer_id=customer.id,
        amount_atomic=PICONERO,
        amount_xmr=Decimal("1"),
        interval_days=30,
        status=status,
        grace_days_soft=3,
        grace_days_hard=7,
        next_due_at=next_due_at or now + timedelta(days=30),
        billing_anchor_at=now,
    )
    db.add_all([customer, sub])
    await db.commit()
    return customer, sub


async def attach_subscription_payment(
    db: AsyncSession,
    subscription: Subscription,
    invoice: Invoice,
    *,
    period_start: datetime | None = None,
) -> SubscriptionPayment:
    """SETUP-ONLY: bind an invoice to a subscription period."""
    start = period_start or datetime.now(timezone.utc)
    sp = SubscriptionPayment(
        id=uuid.uuid4(),
        subscription_id=subscription.id,
        invoice_id=invoice.id,
        period_start=start,
        period_end=start + timedelta(days=subscription.interval_days),
    )
    db.add(sp)
    await db.commit()
    return sp


async def set_invoice_status(db: AsyncSession, invoice_id: uuid.UUID, status: InvoiceStatus) -> None:
    """SETUP-ONLY: put fixture invoice in a desired precondition state."""
    values: dict[str, Any] = {"status": status}
    if status in (InvoiceStatus.paid, InvoiceStatus.overpaid, InvoiceStatus.late_paid):
        values["paid_at"] = datetime.now(timezone.utc)
    await db.execute(update(Invoice).where(Invoice.id == invoice_id).values(**values))
    await db.commit()


async def cleanup_merchant(db: AsyncSession, merchant_id: uuid.UUID) -> None:
    """Cleanup-only delete in FK-safe order."""
    invoice_ids = list((await db.execute(select(Invoice.id).where(Invoice.merchant_id == merchant_id))).scalars())
    sub_ids = list((await db.execute(select(Subscription.id).where(Subscription.merchant_id == merchant_id))).scalars())
    delivery_ids = list(
        (await db.execute(select(WebhookDelivery.id).where(WebhookDelivery.merchant_id == merchant_id))).scalars()
    )
    if delivery_ids:
        await db.execute(delete(WebhookDeadLetter).where(WebhookDeadLetter.delivery_id.in_(delivery_ids)))
    await db.execute(delete(WebhookDelivery).where(WebhookDelivery.merchant_id == merchant_id))
    if sub_ids:
        await db.execute(delete(SubscriptionRenewalEvent).where(SubscriptionRenewalEvent.subscription_id.in_(sub_ids)))
        await db.execute(delete(SubscriptionPayment).where(SubscriptionPayment.subscription_id.in_(sub_ids)))
    await db.execute(delete(Subscription).where(Subscription.merchant_id == merchant_id))
    await db.execute(delete(Customer).where(Customer.merchant_id == merchant_id))
    if invoice_ids:
        await db.execute(delete(Payment).where(Payment.invoice_id.in_(invoice_ids)))
        await db.execute(delete(InvoiceAddress).where(InvoiceAddress.invoice_id.in_(invoice_ids)))
    await db.execute(delete(Invoice).where(Invoice.merchant_id == merchant_id))
    await db.execute(delete(WalletShard).where(WalletShard.merchant_id == merchant_id))
    await db.execute(delete(ApiKey).where(ApiKey.merchant_id == merchant_id))
    await db.execute(delete(AuditLog).where(AuditLog.merchant_id == merchant_id))
    await db.execute(delete(Merchant).where(Merchant.id == merchant_id))
    await db.commit()


async def payment_count(db: AsyncSession, invoice_id: uuid.UUID) -> int:
    return int((await db.execute(select(func.count(Payment.id)).where(Payment.invoice_id == invoice_id))).scalar_one())


async def webhook_events(db: AsyncSession, invoice_id: uuid.UUID) -> list[str]:
    rows = (
        await db.execute(
            select(WebhookDelivery.event_type)
            .where(WebhookDelivery.invoice_id == invoice_id)
            .order_by(WebhookDelivery.created_at)
        )
    ).scalars()
    return list(rows)


def internal_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.internal_secret or 'wave5-test-secret'}"}
