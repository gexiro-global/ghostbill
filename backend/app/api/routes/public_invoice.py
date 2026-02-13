"""
Public invoice API routes (no authentication required).

GET /v1/invoices/{id}/public  — Public invoice data for payment page (api_router)
GET /pay/{id}                 — Serve pay.html payment page (pay_router)

Security:
- Rate limited via PUBLIC_API tier (300/min per IP)
- Filtered response — ONLY safe fields exposed
- NEVER exposes: merchant_id, metadata, webhook_url, customer_id,
  subscription_id, fiat_rate, subaddress_index, api_key
- Security headers: CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy
- UUID validation (404 for invalid format)
- QR code generated server-side (segno library, SVG output)
"""

import io
import logging
import uuid
from pathlib import Path

import segno
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import Invoice, InvoiceAddress, Payment, PaymentStatus
from app.db.session import async_session

logger = logging.getLogger(__name__)

# api_router: registered with /v1 prefix in main.py
api_router = APIRouter(tags=["public"])

# pay_router: registered at root level in main.py (no prefix)
pay_router = APIRouter(tags=["public"])

# Confirmations required for payment to be considered final
CONFIRMATIONS_REQUIRED = 10

# Security headers for all public responses
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store, no-cache, must-revalidate",
}

# Path to pay.html
# In Docker: /app/app/api/routes/public_invoice.py → need 4x parent to reach /app/
# /app/app/api/routes/ → /app/app/api/ → /app/app/ → /app/ → /app/static/pay.html
PAY_HTML_PATH = Path(__file__).resolve().parent.parent.parent.parent / "static" / "pay.html"


def _validate_uuid(invoice_id: str) -> uuid.UUID:
    """Validate and parse UUID string. Raises 404 on invalid format."""
    try:
        return uuid.UUID(invoice_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )


def _build_monero_uri(address: str, amount_xmr: str) -> str:
    """Build Monero URI for wallet QR scanning.

    Format: monero:<address>?tx_amount=<xmr>
    No tx_description for privacy.
    Compatible with Cake Wallet, Monerujo, Feather.
    """
    return f"monero:{address}?tx_amount={amount_xmr}"


def _generate_qr_svg(data: str) -> str:
    """Generate QR code as SVG string using segno.

    Returns SVG markup ready for inline embedding.
    Error correction level M, scale 4, no border.
    """
    try:
        qr = segno.make(data, error="m")
        buffer = io.BytesIO()
        qr.save(buffer, kind="svg", scale=4, border=0, dark="#000000", light="#ffffff")
        svg_bytes = buffer.getvalue()
        return svg_bytes.decode("utf-8")
    except Exception as e:
        logger.error(f"QR generation failed: {e}")
        return ""


# ─── Public Invoice Data ─────────────────────────────────────────────────────


@api_router.get("/invoices/{invoice_id}/public")
async def get_public_invoice(invoice_id: str):
    """Get limited invoice data for public payment page.

    No authentication required. Invoice UUID serves as access token
    (2^128 space makes enumeration infeasible).

    Returns ONLY: id, amount_xmr, amount_atomic, fiat_amount, fiat_currency,
    description, address, status, expires_at, created_at, confirmations,
    confirmations_required, paid_amount_atomic, monero_uri, qr_svg.
    """
    parsed_id = _validate_uuid(invoice_id)

    async with async_session() as db:
        # Fetch invoice with address eagerly loaded
        result = await db.execute(
            select(Invoice)
            .options(selectinload(Invoice.address))
            .where(Invoice.id == parsed_id)
        )
        invoice = result.scalar_one_or_none()

        if invoice is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found.",
            )

        # Get address
        address = invoice.address.address if invoice.address else None
        address_str = address or ""

        # Aggregate payment data: total paid + max confirmations
        payment_result = await db.execute(
            select(
                func.coalesce(func.sum(Payment.amount_atomic), 0).label("paid_total"),
                func.coalesce(func.max(Payment.confirmations), 0).label("max_confirmations"),
            )
            .where(
                Payment.invoice_id == parsed_id,
                Payment.status.in_([PaymentStatus.detected, PaymentStatus.confirmed]),
            )
        )
        payment_row = payment_result.one()
        paid_amount_atomic = int(payment_row.paid_total)
        confirmations = int(payment_row.max_confirmations)

        # Build monero URI and QR (only for pending invoices with address)
        monero_uri = None
        qr_svg = ""
        if address_str and invoice.status.value == "pending":
            monero_uri = _build_monero_uri(address_str, str(invoice.amount_xmr))
            qr_svg = _generate_qr_svg(monero_uri)

        # Build filtered response — ONLY allowed fields
        response_data = {
            "id": str(invoice.id),
            "amount_xmr": str(invoice.amount_xmr),
            "amount_atomic": invoice.amount_atomic,
            "fiat_amount": str(invoice.fiat_amount) if invoice.fiat_amount is not None else None,
            "fiat_currency": invoice.fiat_currency,
            "description": invoice.description,
            "address": address_str,
            "status": invoice.status.value,
            "expires_at": invoice.expires_at.isoformat(),
            "created_at": invoice.created_at.isoformat(),
            "confirmations": confirmations,
            "confirmations_required": CONFIRMATIONS_REQUIRED,
            "paid_amount_atomic": paid_amount_atomic,
            "monero_uri": monero_uri,
            "qr_svg": qr_svg,
        }

    response = JSONResponse(content=response_data)
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    return response


# ─── Serve Payment Page ──────────────────────────────────────────────────────


@pay_router.get("/pay/{invoice_id}", include_in_schema=False)
async def serve_payment_page(invoice_id: str):
    """Serve standalone payment HTML page.

    Validates UUID format, then returns static pay.html.
    The page fetches invoice data via JS polling.
    """
    _validate_uuid(invoice_id)

    if not PAY_HTML_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment page not available.",
        )

    response = FileResponse(
        path=str(PAY_HTML_PATH),
        media_type="text/html",
    )
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    return response
