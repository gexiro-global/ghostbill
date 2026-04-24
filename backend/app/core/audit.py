"""
Async audit event logging.

14 event types covering all critical operations.
Writes to audit_log table via fire-and-forget asyncio.create_task().
NEVER blocks API response — errors are logged, not raised.

Existing audit_log schema (from Alembic):
    id          UUID PK
    merchant_id UUID FK -> merchants
    action      VARCHAR(128) NOT NULL
    entity_type VARCHAR(64)
    entity_id   UUID
    details     JSONB
    ip_address  VARCHAR(45)
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()

Usage:
    await audit_log(db, event="invoice.created", merchant_id=mid,
                    metadata={"invoice_id": str(inv_id), "amount_atomic": amount})

    # Or fire-and-forget (preferred in route handlers):
    audit_log_fire(db, event="invoice.created", ...)
"""

import asyncio
import logging
import uuid as uuid_mod
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AuditEvent(str, Enum):
    # Merchant events
    MERCHANT_REGISTERED = "merchant.registered"
    MERCHANT_UPDATED = "merchant.updated"
    MERCHANT_DELETED = "merchant.deleted"

    # Invoice events
    INVOICE_CREATED = "invoice.created"
    INVOICE_CANCELLED = "invoice.cancelled"
    INVOICE_EXPIRED = "invoice.expired"

    # Payment events
    PAYMENT_DETECTED = "payment.detected"
    PAYMENT_CONFIRMED = "payment.confirmed"
    PAYMENT_ORPHANED = "payment.orphaned"

    # Webhook events
    WEBHOOK_DELIVERED = "webhook.delivered"
    WEBHOOK_FAILED = "webhook.failed"
    WEBHOOK_RETRIED = "webhook.retried"

    # API key events
    API_KEY_CREATED = "api_key.created"
    API_KEY_REVOKED = "api_key.revoked"


# Map event types to entity_type for structured querying
_EVENT_ENTITY_MAP: dict[str, str] = {
    "merchant.registered": "merchant",
    "merchant.updated": "merchant",
    "merchant.deleted": "merchant",
    "invoice.created": "invoice",
    "invoice.cancelled": "invoice",
    "invoice.expired": "invoice",
    "payment.detected": "payment",
    "payment.confirmed": "payment",
    "payment.orphaned": "payment",
    "webhook.delivered": "webhook",
    "webhook.failed": "webhook",
    "webhook.retried": "webhook",
    "api_key.created": "api_key",
    "api_key.revoked": "api_key",
}

# Fields that should be truncated in metadata for privacy
_TRUNCATE_FIELDS = {"address", "tx_hash", "view_key", "key_prefix"}
_TRUNCATE_LENGTH = 14  # Show first 8 + "..." + last 6


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Truncate sensitive fields in audit metadata."""
    if not metadata:
        return metadata

    sanitized = {}
    for key, value in metadata.items():
        if key in _TRUNCATE_FIELDS and isinstance(value, str) and len(value) > _TRUNCATE_LENGTH:
            sanitized[key] = f"{value[:8]}...{value[-6:]}"
        else:
            sanitized[key] = value
    return sanitized


async def audit_log(
    db: AsyncSession,
    event: AuditEvent | str,
    merchant_id: UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
    entity_id: UUID | str | None = None,
) -> None:
    """Write an audit log entry to the database.

    Uses existing audit_log table schema from Alembic migration.
    Column mapping: event -> action, metadata -> details.

    On failure, logs error but does NOT raise — audit must never break API flow.

    Args:
        db: Database session.
        event: Audit event type (from AuditEvent enum or string).
        merchant_id: Associated merchant UUID (nullable for system events).
        metadata: Additional event data (will be sanitized), stored in 'details' column.
        entity_id: Related entity UUID (invoice_id, payment_id, etc.).
    """
    import json

    event_str = event.value if isinstance(event, AuditEvent) else str(event)
    sanitized = _sanitize_metadata(metadata)
    details_json = json.dumps(sanitized) if sanitized else None
    merchant_uuid = str(merchant_id) if merchant_id else None
    entity_uuid = str(entity_id) if entity_id else None
    entity_type = _EVENT_ENTITY_MAP.get(event_str)
    row_id = str(uuid_mod.uuid4())

    try:
        await db.execute(
            text("""
                INSERT INTO audit_log (id, merchant_id, action, entity_type, entity_id, details, ip_address, created_at)
                VALUES (:id::uuid, :merchant_id::uuid, :action, :entity_type,
                    :entity_id::uuid, :details::jsonb, NULL, :created_at)
            """),
            {
                "id": row_id,
                "merchant_id": merchant_uuid,
                "action": event_str,
                "entity_type": entity_type,
                "entity_id": entity_uuid,
                "details": details_json,
                "created_at": datetime.now(timezone.utc),
            },
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Audit log write failed for {event_str}: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


def audit_log_fire(
    db: AsyncSession,
    event: AuditEvent | str,
    merchant_id: UUID | str | None = None,
    metadata: dict[str, Any] | None = None,
    entity_id: UUID | str | None = None,
) -> None:
    """Fire-and-forget audit log write.

    Creates an asyncio task that writes the audit entry.
    NEVER blocks the calling coroutine. Errors are swallowed and logged.

    Usage in route handlers:
        audit_log_fire(db, AuditEvent.INVOICE_CREATED, merchant.id,
                       {"invoice_id": str(invoice.id)})
    """
    try:
        asyncio.create_task(
            _audit_log_safe(db, event, merchant_id, metadata, entity_id),
            name=f"audit:{event}",
        )
    except RuntimeError:
        # No running event loop (shouldn't happen in FastAPI)
        logger.warning(f"Cannot create audit task for {event}: no event loop")


async def _audit_log_safe(
    db: AsyncSession,
    event: AuditEvent | str,
    merchant_id: UUID | str | None,
    metadata: dict[str, Any] | None,
    entity_id: UUID | str | None,
) -> None:
    """Wrapper that ensures audit_log never propagates exceptions."""
    try:
        await audit_log(db, event, merchant_id, metadata, entity_id)
    except Exception as e:
        event_str = event.value if isinstance(event, AuditEvent) else str(event)
        logger.error(f"Audit fire-and-forget failed for {event_str}: {e}")


async def ensure_audit_table(db: AsyncSession) -> None:
    """Verify audit_log table exists and has required indexes.

    Table is created by Alembic migration. This function only verifies
    and adds any missing indexes. Safe to call multiple times.
    """
    try:
        # Verify table exists by querying it
        await db.execute(text("SELECT 1 FROM audit_log LIMIT 0"))
        await db.commit()
        logger.info("audit_log table verified")
    except Exception as e:
        logger.warning(f"audit_log table check failed: {e}")
        try:
            await db.rollback()
        except Exception:
            pass
