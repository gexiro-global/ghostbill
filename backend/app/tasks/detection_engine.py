"""
Payment Detection Engine — background task polling wallet-rpc.

Two modes:
    1. Regular scan (every 30s): poll get_transfers from last_scanned_height
    2. Deep scan (every 1h): scan last 100 blocks (catch edge cases)

Flow per cycle:
    1. Get current blockchain height from wallet-rpc
    2. If height increased → fetch transfers (confirmed + mempool)
    3. For each transfer → payment_service.process_transfer()
    4. Update confirmations for all unconfirmed (detected) payments
    5. Reorg check: verify detected payments still exist
    6. Dispatch webhook events for any state changes
    7. Save last_scanned_height to Redis

CRITICAL:
    - pool=True for mempool visibility
    - match by subaddr_index.minor → invoice_addresses.address_index
    - Dust filter: ignore < DUST_THRESHOLD_ATOMIC
    - Reorg: TX disappears → payment orphaned → invoice recalculated
    - Own DB session per cycle (no shared state)
"""

import asyncio
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models import (
    Invoice,
    InvoiceStatus,
    Merchant,
    Payment,
    PaymentStatus,
)
from app.db.session import async_session
from app.services.monero_rpc import (
    MoneroRPCConnectionError,
    MoneroRPCError,
    get_monero_rpc,
)
from app.services.payment_service import payment_service
from app.services.webhook_service import webhook_service

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────────────────────────

SCAN_INTERVAL: int = 30          # seconds between regular scans
DEEP_SCAN_INTERVAL: int = 3600   # seconds between deep scans (1 hour)
DEEP_SCAN_BLOCKS: int = 100      # how far back deep scan goes

REDIS_HEIGHT_KEY: str = "ghostbill:last_scanned_height"


# ─── Redis Helpers ───────────────────────────────────────────────────────────

async def _get_redis() -> aioredis.Redis:
    """Get Redis connection."""
    return aioredis.from_url(
        f"redis://{settings.redis_host}:{settings.redis_port}",
        decode_responses=True,
    )


async def get_last_scanned_height() -> int:
    """Read last scanned height from Redis."""
    try:
        r = await _get_redis()
        val = await r.get(REDIS_HEIGHT_KEY)
        await r.aclose()
        return int(val) if val else 0
    except Exception:
        logger.warning("Failed to read last_scanned_height from Redis, starting from 0")
        return 0


async def save_last_scanned_height(height: int) -> None:
    """Save last scanned height to Redis."""
    try:
        r = await _get_redis()
        await r.set(REDIS_HEIGHT_KEY, str(height))
        await r.aclose()
    except Exception:
        logger.warning("Failed to save last_scanned_height to Redis")


# ─── Core Scan Logic ────────────────────────────────────────────────────────

async def _scan_transfers(
    db: AsyncSession,
    min_height: int,
    max_height: int,
    label: str = "regular",
) -> int:
    """Fetch and process transfers in a height range.

    Returns number of payments processed.
    """
    rpc = get_monero_rpc()

    try:
        transfers = await rpc.get_transfers(
            account_index=0,
            min_height=min_height,
            max_height=max_height,
            pool=True,
            in_=True,
            filter_by_height=True,
        )
    except MoneroRPCConnectionError as exc:
        logger.error("Detection engine RPC connection error (%s): %s", label, exc)
        return 0
    except MoneroRPCError as exc:
        logger.error("Detection engine RPC error (%s): %s", label, exc)
        return 0

    if not transfers:
        return 0

    processed = 0

    for tx in transfers:
        try:
            # Determine if mempool based on tx type or height
            is_mempool = tx.get("type") == "pool" or tx.get("height", 0) == 0

            # Snapshot invoice status before processing
            minor_index = tx.get("subaddr_index", {}).get("minor")
            if minor_index is None:
                continue

            # Find invoice for pre-processing snapshot
            invoice = await payment_service.find_invoice_by_subaddress_index(
                db, tx["subaddr_index"]["major"], minor_index
            )
            old_invoice_status = invoice.status if invoice else None

            # Find existing payment for snapshot
            existing_payment = await payment_service.find_payment_by_tx_hash(
                db, tx["txid"]
            )
            old_payment_status = existing_payment.status if existing_payment else None

            # Process the transfer
            payment = await payment_service.process_transfer(db, tx, is_mempool)

            if payment is None:
                continue

            processed += 1

            # Reload invoice for current status
            if invoice is not None:
                await db.refresh(invoice)

                # Determine webhook events
                events = payment_service.determine_webhook_events(
                    payment=payment,
                    invoice=invoice,
                    old_invoice_status=old_invoice_status,
                    old_payment_status=old_payment_status,
                )

                # Dispatch webhooks
                if events:
                    merchant = await _load_merchant(db, invoice.merchant_id)
                    if merchant:
                        await webhook_service.dispatch_events(
                            db=db,
                            events=events,
                            merchant=merchant,
                            invoice=invoice,
                            payment=payment,
                        )

        except Exception:
            logger.exception(
                "Error processing transfer txid=%s", tx.get("txid", "?")[:16]
            )

    return processed


async def _update_unconfirmed(db: AsyncSession) -> int:
    """Update confirmations for all detected (unconfirmed) payments.

    Polls wallet-rpc get_transfer_by_txid for each unconfirmed payment.
    Returns number of payments that transitioned to confirmed.
    """
    rpc = get_monero_rpc()
    payments = await payment_service.get_unconfirmed_payments(db)

    if not payments:
        return 0

    confirmed_count = 0

    for payment in payments:
        try:
            # Snapshot
            old_payment_status = payment.status

            tx = await rpc.get_transfer_by_txid(payment.tx_hash)

            if tx is None:
                # TX disappeared — possible reorg
                await payment_service.handle_reorg(db, payment)

                # Dispatch orphaned webhook
                invoice = await _load_invoice_with_merchant(db, payment.invoice_id)
                if invoice:
                    merchant = await _load_merchant(db, invoice.merchant_id)
                    if merchant:
                        events = payment_service.determine_webhook_events(
                            payment=payment,
                            invoice=invoice,
                            old_invoice_status=invoice.status,
                            old_payment_status=old_payment_status,
                        )
                        if events:
                            await webhook_service.dispatch_events(
                                db=db,
                                events=events,
                                merchant=merchant,
                                invoice=invoice,
                                payment=payment,
                            )
                continue

            confirmations = int(tx.get("confirmations", 0))
            block_height = int(tx["height"]) if tx.get("height", 0) > 0 else None

            # Update confirmations (may trigger detected → confirmed)
            from app.services.payment_service import CONFIRMATION_THRESHOLD

            payment.confirmations = confirmations
            if block_height and payment.block_height is None:
                payment.block_height = block_height

            if (
                payment.status == PaymentStatus.detected
                and confirmations >= CONFIRMATION_THRESHOLD
            ):
                payment.status = PaymentStatus.confirmed
                payment.confirmed_at = datetime.now(timezone.utc)
                confirmed_count += 1

                # Recalculate invoice status
                invoice = await _load_invoice_with_merchant(db, payment.invoice_id)
                if invoice:
                    old_invoice_status = invoice.status
                    await payment_service._recalculate_invoice_status(db, invoice)
                    await db.refresh(invoice)

                    # Dispatch webhooks
                    events = payment_service.determine_webhook_events(
                        payment=payment,
                        invoice=invoice,
                        old_invoice_status=old_invoice_status,
                        old_payment_status=old_payment_status,
                    )
                    if events:
                        merchant = await _load_merchant(db, invoice.merchant_id)
                        if merchant:
                            await webhook_service.dispatch_events(
                                db=db,
                                events=events,
                                merchant=merchant,
                                invoice=invoice,
                                payment=payment,
                            )

            await db.flush()

        except MoneroRPCError as exc:
            logger.warning(
                "RPC error checking tx %s: %s", payment.tx_hash[:16], exc
            )
        except Exception:
            logger.exception(
                "Error updating confirmations for tx %s", payment.tx_hash[:16]
            )

    return confirmed_count


# ─── Helper Loaders ──────────────────────────────────────────────────────────

async def _load_merchant(
    db: AsyncSession, merchant_id
) -> Merchant | None:
    """Load merchant by ID."""
    stmt = select(Merchant).where(Merchant.id == merchant_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _load_invoice_with_merchant(
    db: AsyncSession, invoice_id
) -> Invoice | None:
    """Load invoice with payments."""
    stmt = (
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .options(selectinload(Invoice.payments))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ─── Background Task ────────────────────────────────────────────────────────

async def detection_engine_loop() -> None:
    """Main detection engine background loop.

    Regular scan: every 30s — fetch new blocks + mempool
    Deep scan: every 1h — re-scan last 100 blocks
    Confirmation update: every cycle — poll unconfirmed payments
    """
    logger.info(
        "Detection engine started: scan=%ds, deep_scan=%ds, deep_blocks=%d",
        SCAN_INTERVAL,
        DEEP_SCAN_INTERVAL,
        DEEP_SCAN_BLOCKS,
    )

    last_deep_scan = datetime.now(timezone.utc)

    while True:
        try:
            rpc = get_monero_rpc()

            # Get current height
            try:
                current_height = await rpc.get_height()
            except (MoneroRPCConnectionError, MoneroRPCError) as exc:
                logger.warning("Detection engine: cannot get height: %s", exc)
                await asyncio.sleep(SCAN_INTERVAL)
                continue

            last_scanned = await get_last_scanned_height()

            async with async_session() as db:
                # ── Regular scan ─────────────────────────────────────
                if current_height > last_scanned:
                    processed = await _scan_transfers(
                        db,
                        min_height=max(last_scanned - 1, 0),  # overlap 1 block for safety
                        max_height=current_height,
                        label="regular",
                    )

                    if processed > 0:
                        logger.info(
                            "Regular scan: %d payments processed, height %d→%d",
                            processed,
                            last_scanned,
                            current_height,
                        )

                    await save_last_scanned_height(current_height)

                # ── Deep scan (every 1h) ─────────────────────────────
                now = datetime.now(timezone.utc)
                elapsed = (now - last_deep_scan).total_seconds()

                if elapsed >= DEEP_SCAN_INTERVAL:
                    deep_from = max(current_height - DEEP_SCAN_BLOCKS, 0)
                    processed = await _scan_transfers(
                        db,
                        min_height=deep_from,
                        max_height=current_height,
                        label="deep",
                    )

                    if processed > 0:
                        logger.info(
                            "Deep scan: %d payments processed, height %d→%d",
                            processed,
                            deep_from,
                            current_height,
                        )

                    last_deep_scan = now

                # ── Update confirmations ─────────────────────────────
                confirmed = await _update_unconfirmed(db)
                if confirmed > 0:
                    logger.info(
                        "Confirmation update: %d payments confirmed", confirmed
                    )

                await db.commit()

        except asyncio.CancelledError:
            logger.info("Detection engine shutting down")
            raise

        except Exception:
            logger.exception("Detection engine cycle error")

        await asyncio.sleep(SCAN_INTERVAL)
