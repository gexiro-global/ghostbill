"""Payment Detection Engine — background task polling wallet-rpc.

Two modes:
    1. Regular scan (every 30s): poll get_transfers from last_scanned_height
    2. Deep scan (every 1h): scan last 100 blocks (catch edge cases)

Phase 6C changes:
    - Reorg buffer increased from 1 to 10 blocks
    - Health metrics saved to Redis (last_sweep_at, blocks_behind)
    - Code split: helpers/confirmations extracted to separate modules

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

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.services.monero_rpc import (
    MoneroRPCConnectionError,
    MoneroRPCError,
    get_monero_rpc,
)
from app.services.payment_service import payment_service
from app.services.webhook_service import webhook_service
from app.tasks.detection_confirmations import update_unconfirmed
from app.tasks.detection_helpers import (
    DEEP_SCAN_BLOCKS,
    DEEP_SCAN_INTERVAL,
    REORG_BUFFER,
    SCAN_INTERVAL,
    get_last_scanned_height,
    load_invoice_with_payments,
    load_merchant,
    save_health_metrics,
    save_last_scanned_height,
)

logger = logging.getLogger(__name__)


# ── Core Scan Logic ────────────────────────────────────────────────────────

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
            is_mempool = tx.get("type") == "pool" or tx.get("height", 0) == 0

            minor_index = tx.get("subaddr_index", {}).get("minor")
            if minor_index is None:
                continue

            invoice = await payment_service.find_invoice_by_subaddress_index(
                db, tx["subaddr_index"]["major"], minor_index
            )
            old_invoice_status = invoice.status if invoice else None

            existing_payment = await payment_service.find_payment_by_tx_hash(
                db, tx["txid"]
            )
            old_payment_status = existing_payment.status if existing_payment else None

            payment = await payment_service.process_transfer(db, tx, is_mempool)

            if payment is None:
                continue

            processed += 1

            if invoice is not None:
                await db.refresh(invoice)

                events = payment_service.determine_webhook_events(
                    payment=payment,
                    invoice=invoice,
                    old_invoice_status=old_invoice_status,
                    old_payment_status=old_payment_status,
                )

                if events:
                    merchant = await load_merchant(db, invoice.merchant_id)
                    if merchant:
                        await webhook_service.dispatch_events(
                            db=db, events=events,
                            merchant=merchant, invoice=invoice,
                            payment=payment,
                        )

        except Exception:
            logger.exception(
                "Error processing transfer txid=%s", tx.get("txid", "?")[:16]
            )

    return processed


# ── Background Task ────────────────────────────────────────────────────────

async def detection_engine_loop() -> None:
    """Main detection engine background loop.

    Regular scan: every 30s — fetch new blocks + mempool
    Deep scan: every 1h — re-scan last 100 blocks
    Confirmation update: every cycle — poll unconfirmed payments
    Phase 6C: reorg buffer 10 blocks, health metrics to Redis
    """
    logger.info(
        "Detection engine started: scan=%ds, deep_scan=%ds, deep_blocks=%d, reorg_buffer=%d",
        SCAN_INTERVAL, DEEP_SCAN_INTERVAL, DEEP_SCAN_BLOCKS, REORG_BUFFER,
    )

    last_deep_scan = datetime.now(timezone.utc)

    while True:
        try:
            rpc = get_monero_rpc()

            try:
                current_height = await rpc.get_height()
            except (MoneroRPCConnectionError, MoneroRPCError) as exc:
                logger.warning("Detection engine: cannot get height: %s", exc)
                await asyncio.sleep(SCAN_INTERVAL)
                continue

            last_scanned = await get_last_scanned_height()

            async with async_session() as db:
                # ── Regular scan ───────────────────────────────────────
                if current_height > last_scanned:
                    # Phase 6C: reorg buffer 10 blocks (was 1)
                    scan_from = max(last_scanned - REORG_BUFFER, 0)
                    processed = await _scan_transfers(
                        db,
                        min_height=scan_from,
                        max_height=current_height,
                        label="regular",
                    )

                    if processed > 0:
                        logger.info(
                            "Regular scan: %d payments, height %d→%d (buffer: %d)",
                            processed, last_scanned, current_height, REORG_BUFFER,
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
                            "Deep scan: %d payments, height %d→%d",
                            processed, deep_from, current_height,
                        )

                    last_deep_scan = now

                # ── Update confirmations ─────────────────────────────
                confirmed = await update_unconfirmed(db)
                if confirmed > 0:
                    logger.info(
                        "Confirmation update: %d payments confirmed", confirmed
                    )

                await db.commit()

            # Phase 6C: save health metrics after successful cycle
            await save_health_metrics(current_height, last_scanned)

        except asyncio.CancelledError:
            logger.info("Detection engine shutting down")
            raise

        except Exception:
            logger.exception("Detection engine cycle error")

        await asyncio.sleep(SCAN_INTERVAL)
