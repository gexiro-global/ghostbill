"""Subscription update logic — pending changes for next renewal cycle.

Phase 6A: PATCH semantics with pending_* fields.
    - Financial fields → pending_* (applied at renewal)
    - metadata → immediate (non-financial)
    - value=None → clear pending change
    - Terminal states → blocked (409)
    - Paused → allowed
"""

import logging
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Subscription
from app.services.monero_rpc import xmr_to_atomic
from app.services.subscription_exceptions import (
    SubscriptionNotFoundError,
    SubscriptionStateError,
    SubscriptionValidationError,
    TERMINAL_STATUSES,
)

logger = logging.getLogger(__name__)

_UNSET = object()


async def update_subscription(
    db: AsyncSession, sub: Subscription,
    amount_xmr=_UNSET, interval_days=_UNSET,
    grace_days_soft=_UNSET, grace_days_hard=_UNSET,
    metadata=_UNSET,
) -> Subscription:
    """Update subscription with pending changes."""
    if sub.status in TERMINAL_STATUSES:
        raise SubscriptionStateError(f"Cannot update {sub.status.value} subscription.")

    # Amount
    if amount_xmr is not _UNSET:
        if amount_xmr is None:
            sub.pending_amount_atomic = None
            sub.pending_amount_xmr = None
        else:
            try:
                val = Decimal(str(amount_xmr))
            except (InvalidOperation, ValueError, TypeError):
                raise SubscriptionValidationError(f"Invalid amount_xmr: {amount_xmr!r}")
            if val <= 0:
                raise SubscriptionValidationError("amount_xmr must be > 0.")
            sub.pending_amount_atomic = xmr_to_atomic(val)
            sub.pending_amount_xmr = val

    # Interval
    if interval_days is not _UNSET:
        if interval_days is None:
            sub.pending_interval_days = None
        else:
            if not isinstance(interval_days, int) or interval_days < 1:
                raise SubscriptionValidationError("interval_days must be >= 1.")
            sub.pending_interval_days = interval_days

    # Grace soft
    if grace_days_soft is not _UNSET:
        if grace_days_soft is None:
            sub.pending_grace_soft = None
        else:
            if grace_days_soft < 0:
                raise SubscriptionValidationError("grace_days_soft cannot be negative.")
            sub.pending_grace_soft = grace_days_soft

    # Grace hard
    if grace_days_hard is not _UNSET:
        if grace_days_hard is None:
            sub.pending_grace_hard = None
        else:
            if grace_days_hard < 0:
                raise SubscriptionValidationError("grace_days_hard cannot be negative.")
            sub.pending_grace_hard = grace_days_hard

    # Cross-validate: effective hard >= effective soft
    eff_soft = sub.pending_grace_soft if sub.pending_grace_soft is not None else sub.grace_days_soft
    eff_hard = sub.pending_grace_hard if sub.pending_grace_hard is not None else sub.grace_days_hard
    if eff_hard < eff_soft:
        raise SubscriptionValidationError("grace_days_hard must be >= grace_days_soft.")

    # Metadata — immediate
    if metadata is not _UNSET:
        sub.metadata_json = metadata

    await db.flush()
    logger.info("Subscription updated: %s", sub.id)
    return sub
