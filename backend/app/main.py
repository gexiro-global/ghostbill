"""GhostBill FastAPI application entry point.

Routers: merchants, price, invoices, payments, webhooks, api_keys, auth_signature,
         customers, subscriptions, analytics, admin, public_invoice
Middleware: RateLimiter → SecurityHeaders → TimingJitter
Lifespan: Redis, background tasks (6), cleanup on shutdown.
Phase 6C: /health includes detection metrics.
Phase 7A: /v1/analytics/* endpoints.
Phase 9: /v1/admin/* endpoints (operator panel).
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.admin import router as admin_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.api_keys import router as api_keys_router
from app.api.routes.auth_signature import router as auth_signature_router
from app.api.routes.customers import router as customers_router
from app.api.routes.invoices import router as invoices_router
from app.api.routes.merchants import router as merchants_router
from app.api.routes.payments import router as payments_router
from app.api.routes.price import router as price_router
from app.api.routes.public_invoice import api_router as public_api_router
from app.api.routes.public_invoice import pay_router as pay_page_router
from app.api.routes.subscriptions import router as subscriptions_router
from app.api.routes.webhooks import router as webhooks_router
from app.config import settings
from app.core.audit import ensure_audit_table
from app.core.encryption import get_encryption
from app.core.log_redactor import setup_log_redaction
from app.db.session import async_session, engine
from app.dependencies import close_redis, get_redis
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.timing_jitter import TimingJitterMiddleware
from app.services.monero_rpc import close_monero_rpc
from app.tasks.data_retention import data_retention_loop
from app.tasks.detection_engine import detection_engine_loop
from app.tasks.invoice_expirer import run_invoice_expirer
from app.tasks.price_updater import price_updater_loop
from app.tasks.subscription_renewer import subscription_renewer_loop
from app.tasks.webhook_worker import webhook_worker_loop

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
setup_log_redaction()

_INTERNAL_IPS = {"127.0.0.1", "::1", "172.17.0.1", "172.23.0.1"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_encryption()
    logger.info("Encryption key validated")
    redis = await get_redis()
    await redis.ping()
    logger.info("Redis connected")
    app.state.redis = redis
    async with async_session() as db:
        await ensure_audit_table(db)

    tasks = [
        asyncio.create_task(price_updater_loop(redis)),
        asyncio.create_task(run_invoice_expirer()),
        asyncio.create_task(detection_engine_loop()),
        asyncio.create_task(webhook_worker_loop()),
        asyncio.create_task(data_retention_loop()),
        asyncio.create_task(subscription_renewer_loop()),
    ]
    logger.info("Background tasks started (6)")
    yield

    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    await close_monero_rpc()
    await close_redis()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan,
)

_cors_origins: list[str] = []
if settings.onion_dashboard:
    _cors_origins.append(f"http://{settings.onion_dashboard}")
if settings.debug:
    _cors_origins.extend(["http://localhost:3013", "http://127.0.0.1:3013"])
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_middleware(TimingJitterMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimiterMiddleware)

for r in [
    merchants_router,
    price_router,
    invoices_router,
    payments_router,
    webhooks_router,
    api_keys_router,
    auth_signature_router,
    customers_router,
    subscriptions_router,
    analytics_router,
    admin_router,
]:
    app.include_router(r, prefix=settings.api_prefix)
app.include_router(public_api_router, prefix=settings.api_prefix)
app.include_router(pay_page_router)


@app.get("/health")
async def health_check():
    """Health check with Phase 6C detection metrics."""
    from app.tasks.detection_helpers import get_health_metrics

    detection = await get_health_metrics()

    return JSONResponse(
        content={
            "status": "healthy",
            "app": settings.app_name,
            "version": settings.app_version,
            "detection": detection,
        }
    )


@app.post("/v1/internal/trigger-renewal")
async def trigger_renewal(request: Request, subscription_id: str | None = None):
    """Trigger renewal. Internal only."""
    client_host = request.client.host if request.client else ""
    if client_host not in _INTERNAL_IPS:
        raise HTTPException(status_code=403, detail="Internal only.")

    if subscription_id:
        from sqlalchemy import select

        from app.db.models import Merchant, Subscription, SubscriptionStatus
        from app.db.session import async_session as get_session
        from app.services.invoice_service import WalletUnavailableError
        from app.services.subscription_exceptions import SkipRenewalError
        from app.services.subscription_renewal import _create_renewal_invoice

        sub_uuid = uuid.UUID(subscription_id)
        async with get_session() as db:
            stmt = (
                select(Subscription)
                .where(Subscription.id == sub_uuid, Subscription.status == SubscriptionStatus.active)
                .with_for_update()
            )
            sub = (await db.execute(stmt)).scalar_one_or_none()
            if sub is None:
                raise HTTPException(status_code=404, detail="Subscription not found or not active.")

            merchant = (await db.execute(select(Merchant).where(Merchant.id == sub.merchant_id))).scalar_one_or_none()
            if merchant is None:
                return {"renewed": 0, "skipped": 1, "failed": 0, "reason": "merchant not found"}

            try:
                await _create_renewal_invoice(db, sub, merchant)
                await db.commit()
                return {"renewed": 1, "skipped": 0, "failed": 0}
            except SkipRenewalError as exc:
                return {"renewed": 0, "skipped": 1, "failed": 0, "reason": str(exc)}
            except (WalletUnavailableError, Exception) as exc:
                logger.error("Trigger renewal failed: %s: %s", subscription_id, exc)
                return {"renewed": 0, "skipped": 0, "failed": 1, "error": str(exc)}
    else:
        from app.tasks.subscription_renewer import run_sweep

        return await run_sweep()
