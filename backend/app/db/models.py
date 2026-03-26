import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ──────────────────────────────────────────────────────────────────────


class InvoiceStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    expired = "expired"
    partially_paid = "partially_paid"
    overpaid = "overpaid"
    late_paid = "late_paid"
    cancelled = "cancelled"


class PaymentStatus(str, enum.Enum):
    detected = "detected"
    confirmed = "confirmed"
    orphaned = "orphaned"


class SubscriptionStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    past_due = "past_due"
    cancelled = "cancelled"
    expired = "expired"


class WebhookStatus(str, enum.Enum):
    pending = "pending"
    delivered = "delivered"
    failed = "failed"


# ── Models ─────────────────────────────────────────────────────────────────────


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    monero_address: Mapped[str] = mapped_column(String(128), nullable=False)
    view_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    environment: Mapped[str] = mapped_column(
        String(10), nullable=False, default="test"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="merchant")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="merchant")
    customers: Mapped[list["Customer"]] = relationship(back_populates="merchant")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="merchant")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    amount_atomic: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_xmr: Mapped[Decimal] = mapped_column(Numeric(18, 12), nullable=False)
    fiat_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    fiat_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    fiat_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status"),
        nullable=False,
        default=InvoiceStatus.pending,
    )
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="invoices")
    address: Mapped["InvoiceAddress | None"] = relationship(
        back_populates="invoice", uselist=False
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="invoice")

    __table_args__ = (
        Index("ix_invoices_status_expires", "status", "expires_at", postgresql_where=(status == InvoiceStatus.pending)),
        Index("ix_invoices_merchant_created", "merchant_id", "created_at"),
    )


class InvoiceAddress(Base):
    __tablename__ = "invoice_addresses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), unique=True, nullable=False
    )
    address: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    address_index: Mapped[int] = mapped_column(Integer, nullable=False)
    account_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="address")

    __table_args__ = (
        Index("ix_invoice_addresses_index", "account_index", "address_index"),
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False
    )
    tx_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_atomic: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_xmr: Mapped[Decimal] = mapped_column(Numeric(18, 12), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"),
        nullable=False,
        default=PaymentStatus.detected,
    )
    confirmations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    block_height: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    invoice: Mapped["Invoice"] = relationship(back_populates="payments")

    __table_args__ = (
        Index("ix_payments_tx_hash", "tx_hash"),
        Index("ix_payments_invoice_status", "invoice_id", "status"),
    )


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="customers")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="customer")

    __table_args__ = (
        Index("ix_customers_merchant_external", "merchant_id", "external_id", unique=True),
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    amount_atomic: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_xmr: Mapped[Decimal] = mapped_column(Numeric(18, 12), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"),
        nullable=False,
        default=SubscriptionStatus.active,
    )
    grace_days_soft: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    grace_days_hard: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    next_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Phase 6A: billing anchor (deterministic renewal, no drift)
    billing_anchor_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Phase 6A: pending changes (applied at next renewal)
    pending_amount_atomic: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pending_amount_xmr: Mapped[Decimal | None] = mapped_column(Numeric(18, 12), nullable=True)
    pending_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_grace_soft: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pending_grace_hard: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="subscriptions")
    customer: Mapped["Customer"] = relationship(back_populates="subscriptions")
    payments: Mapped[list["SubscriptionPayment"]] = relationship(
        back_populates="subscription"
    )


class SubscriptionPayment(Base):
    __tablename__ = "subscription_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    subscription: Mapped["Subscription"] = relationship(back_populates="payments")
    invoice: Mapped["Invoice"] = relationship()


class WalletShard(Base):
    __tablename__ = "wallet_shards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    account_index: Mapped[int] = mapped_column(Integer, nullable=False)
    next_address_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_wallet_shards_merchant_account", "merchant_id", "account_index", unique=True),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    environment: Mapped[str] = mapped_column(
        String(10), nullable=False, default="test"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    merchant: Mapped["Merchant"] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("ix_api_keys_prefix", "key_prefix"),
        Index("ix_api_keys_merchant", "merchant_id"),
    )


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[WebhookStatus] = mapped_column(
        Enum(WebhookStatus, name="webhook_status"),
        nullable=False,
        default=WebhookStatus.pending,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "ix_webhook_deliveries_retry",
            "next_retry_at",
            postgresql_where=(status == WebhookStatus.pending),
        ),
        Index("ix_webhook_deliveries_merchant", "merchant_id"),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_audit_log_merchant_created", "merchant_id", "created_at"),
        Index("ix_audit_log_action", "action"),
    )
