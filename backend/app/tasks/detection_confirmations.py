"""Detection confirmation checker — updates unconfirmed payments, handles reorgs.

Extracted from detection_engine.py in Phase 6C.
Polls wallet-rpc get_transfer_by_txid for each detected (unconfirmed) payment.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PaymentStatus
from app.services.monero_rpc import MoneroRPCError, get_monero_rpc
from app.services.payment_service import CONFIRMATION_THRESHOLD, payment_service
from app.services.webhook_service import webhook_service
from app.tasks.detection_helpers import load_invoice_with_payments, load_merchant

logger = logging.getLogger(__name__)


async def update_unconfirmed(db: AsyncSession) -> int:
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
            old_payment_status = payment.status

            tx = await rpc.get_transfer_by_txid(payment.tx_hash)

            if tx is None:
                # TX disappeared — possible reorg
                await payment_service.handle_reorg(db, payment)

                invoice = await load_invoice_with_payments(db, payment.invoice_id)
                if invoice:
                    merchant = await load_merchant(db, invoice.merchant_id)
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
            payment.confirmations = confirmations
            if block_height and payment.block_height is None:
                payment.block_height = block_height

            if payment.status == PaymentStatus.detected and confirmations >= CONFIRMATION_THRESHOLD:
                payment.status = PaymentStatus.confirmed
                payment.confirmed_at = datetime.now(timezone.utc)
                confirmed_count += 1

                # Recalculate invoice status
                invoice = await load_invoice_with_payments(db, payment.invoice_id)
                if invoice:
                    old_invoice_status = invoice.status
                    await payment_service._recalculate_invoice_status(db, invoice)
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
                                db=db,
                                events=events,
                                merchant=merchant,
                                invoice=invoice,
                                payment=payment,
                            )

            await db.flush()

        except MoneroRPCError as exc:
            logger.warning("RPC error checking tx %s: %s", payment.tx_hash[:16], exc)
        except Exception:
            logger.exception("Error updating confirmations for tx %s", payment.tx_hash[:16])

    return confirmed_count
