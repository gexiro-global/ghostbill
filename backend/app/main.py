"""
GhostBill FastAPI application entry point.

Routers: merchants, price, invoices, payments, webhooks, api_keys, auth_signature,
         customers, subscriptions (Phase 5A), public_invoice (Phase 5C)
Middleware stack (order matters — outermost first):
  1. RateLimiterMiddleware (reject early, before any processing)
  2. SecurityHeadersMiddleware (add headers to all responses)
  3. TimingJitterMiddleware (add random delay, innermost)

CORS: enabled for .onion dashboard domain (if configured).

Lifespan: Redis, log redaction, audit table, background tasks (6), cleanup on shutdown.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.dependencies import close_redis, get_redis
from app.db.session import engine, async_session

from app.services.monero_rpc import close_monero_rpc

# Core
from app.core.log_redactor import setup_log_redaction
from app.core.audit import ensure_audit_table
from app.core.encryption import get_encryption

# Middleware
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.timing_jitter import TimingJitterMiddleware

# Routers
from app.api.routes.merchants import router as merchants_router
from app.api.routes.price import router as price_router
from app.api.routes.invoices import router as invoices_router
from app.api.routes.payments import router as payments_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.api_keys import router as api_keys_router
from app.api.routes.auth_signature import router as auth_signature_router
from app.api.routes.customers import router as customers_router
from app.api.routes.subscriptions import router as subscriptions_router
from app.api.routes.public_invoice import api_router as public_api_router
from app.api.routes.public_invoice import pay_router as pay_page_router

# Background tasks
from app.tasks.price_updater import price_updater_loop
from app.tasks.invoice_expirer import run_invoice_expirer
from app.tasks.detection_engine import detection_engine_loop
from app.tasks.webhook_worker import webhook_worker_loop
from app.tasks.data_retention import data_retention_loop
from app.tasks.subscription_renewer import subscription_renewer_loop

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

# Activate log redaction (must be after basicConfig)
setup_log_redaction()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown hooks."""

    # ── Startup ──────────────────────────────────────────────────────────

    # Validate encryption key early (crash fast if missing)
    get_encryption()
    logger.info("Encryption key validated")

    # Redis connection
    redis = await get_redis()
    await redis.ping()
    logger.info("Redis connected")

    # Store Redis in app state (for middleware access)
    app.state.redis = redis

    # Ensure audit_log table exists
    async with async_session() as db:
        await ensure_audit_table(db)

    # Start background tasks (6 total)
    price_task = asyncio.create_task(price_updater_loop(redis))
    expirer_task = asyncio.create_task(run_invoice_expirer())
    detection_task = asyncio.create_task(detection_engine_loop())
    webhook_task = asyncio.create_task(webhook_worker_loop())
    retention_task = asyncio.create_task(data_retention_loop())
    renewer_task = asyncio.create_task(subscription_renewer_loop())

    logger.info(
        "Background tasks started: price_updater, invoice_expirer, "
        "detection_engine, webhook_worker, data_retention, subscription_renewer"
    )

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────

    tasks = [
        price_task, expirer_task, detection_task,
        webhook_task, retention_task, renewer_task,
    ]
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

# ── CORS for .onion dashboard ────────────────────────────────────────────────
# Allow requests from the .onion dashboard to the .onion API.

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

# ── Middleware stack ─────────────────────────────────────────────────────────
# Order: last added = outermost (executed first on request)
# Request flow:  RateLimiter → SecurityHeaders → TimingJitter → route handler
# Response flow: route handler → TimingJitter → SecurityHeaders → RateLimiter

app.add_middleware(TimingJitterMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimiterMiddleware)

# ── Register routers ─────────────────────────────────────────────────────────

# Authenticated API routes (all under /v1 prefix)
app.include_router(merchants_router, prefix=settings.api_prefix)
app.include_router(price_router, prefix=settings.api_prefix)
app.include_router(invoices_router, prefix=settings.api_prefix)
app.include_router(payments_router, prefix=settings.api_prefix)
app.include_router(webhooks_router, prefix=settings.api_prefix)
app.include_router(api_keys_router, prefix=settings.api_prefix)
app.include_router(auth_signature_router, prefix=settings.api_prefix)
app.include_router(customers_router, prefix=settings.api_prefix)
app.include_router(subscriptions_router, prefix=settings.api_prefix)

# Public API routes (no auth required)
app.include_router(public_api_router, prefix=settings.api_prefix)  # GET /v1/invoices/{id}/public
app.include_router(pay_page_router)  # GET /pay/{id} (root level, no prefix)


# ── Health check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return JSONResponse(
        content={
            "status": "healthy",
            "app": settings.app_name,
            "version": settings.app_version,
        }
    )
