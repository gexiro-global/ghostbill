# GhostBill API Reference

**Version:** 0.1.0  
**Base URL:** `http://127.0.0.1:8013` (clearnet) or `http://<onion>.onion` (Tor)  
**Content-Type:** `application/json`

---

## Table of Contents

- [Authentication](#authentication)
- [Amounts & Precision](#amounts--precision)
- [Rate Limiting](#rate-limiting)
- [Error Handling](#error-handling)
- [Pagination](#pagination)
- [Endpoints](#endpoints)
  - [Health](#health)
  - [Merchants](#merchants)
  - [Invoices](#invoices)
  - [Payments](#payments)
  - [Customers](#customers)
  - [Subscriptions](#subscriptions)
  - [Webhooks & Dead Letter Queue](#webhooks--dead-letter-queue)
  - [API Keys](#api-keys)
  - [Analytics](#analytics)
  - [Dashboard Auth (Monero Signature)](#dashboard-auth-monero-signature)
  - [Price](#price)
  - [Public Endpoints](#public-endpoints)
  - [Admin (Operator)](#admin-operator)
- [Environments](#environments)

---

## Authentication

GhostBill uses **Bearer token** authentication with API keys.

**Header format:**

```
Authorization: Bearer <api_key>
```

**API key format:**

| Environment | Format | Example |
|-------------|--------|--------|
| Live | `gb_live_<hex32>` | `gb_live_aaaa1111bbbb2222cccc3333dddd4444` |
| Test | `gb_test_<hex32>` | `gb_test_eeee5555ffff6666aaaa7777bbbb8888` |

**Key storage:**
- Keys are shown **once** at creation — store them securely
- Keys are hashed with **bcrypt (cost ≥ 12)** before storage
- Only the prefix (`gb_live_` / `gb_test_`) is stored in plaintext for identification
- Max **10 active keys** per merchant

**Dashboard authentication** uses a separate Monero signature flow (see [Dashboard Auth](#dashboard-auth-monero-signature)). Session tokens use the format `gbs_<hex64>` with 24-hour TTL.

**Unauthenticated endpoints:** `GET /health`, `GET /v1/price`, `GET /v1/invoices/{id}/public`, `GET /v1/invoices/{id}/events`, `GET /pay/{id}`

---

## Amounts & Precision

GhostBill uses **two representations** for Monero amounts:

| Field | Type | Description | Example |
|-------|------|-------------|--------|
| `amount_xmr` | `string` | Human-readable XMR amount (display only) | `"0.500000000000"` |
| `amount_atomic` | `integer` (BIGINT) | Piconero — **source of truth** | `500000000000` |

**Conversion:** `1 XMR = 10^12 piconero (atomic units)`

Always use `amount_atomic` for calculations and comparisons. The `amount_xmr` field is provided for display convenience and should never be used for arithmetic.

---

## Rate Limiting

All authenticated endpoints are rate-limited. Limits are returned in response headers:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Max requests per window |
| `X-RateLimit-Remaining` | Remaining requests |
| `X-RateLimit-Reset` | Unix timestamp when window resets |
| `Retry-After` | Seconds until next allowed request (only on 429) |

**IP-based tiers:**

| Tier | Endpoints | Limit |
|------|-----------|-------|
| Strict | `POST /v1/merchants` | 5/hour |
| Write | `POST /v1/invoices`, `POST /v1/api-keys`, etc. | 60/min |
| Read | `GET /v1/invoices`, `GET /v1/payments`, etc. | 120/min |
| Public | `GET /health`, `GET /v1/price` | 300/min |

**Per-merchant limits (Phase 6C):**

| Type | Limit |
|------|-------|
| Write operations | 120/min per merchant |
| Read operations | 300/min per merchant |

---

## Error Handling

GhostBill returns standard HTTP status codes with JSON error bodies.

**Error format:**

```json
{
  "detail": "Human-readable error message"
}
```

**Status codes:**

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad request (invalid input) |
| 401 | Unauthorized (missing or invalid API key) |
| 403 | Forbidden (key doesn't have access) |
| 404 | Resource not found |
| 409 | Conflict (e.g., duplicate registration) |
| 422 | Validation error |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

---

## Pagination

All list endpoints use **cursor-based pagination** (Stripe-compatible).

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Results per page (1–100, default 50) |
| `starting_after` | UUID | Return results after this ID (next page) |
| `ending_before` | UUID | Return results before this ID (previous page) |

**Response format:**

```json
{
  "data": [...],
  "has_more": true
}
```

**Example — paginating through invoices:**

```bash
# First page
curl "http://127.0.0.1:8013/v1/invoices?limit=10" \
  -H "Authorization: Bearer gb_live_..."

# Next page (use last item's ID)
curl "http://127.0.0.1:8013/v1/invoices?limit=10&starting_after=a1b2c3d4-..." \
  -H "Authorization: Bearer gb_live_..."
```

---

## Endpoints

### Health

#### `GET /health`

Health check with detection engine metrics. No authentication required.

```bash
curl http://127.0.0.1:8013/health
```

**Response 200:**

```json
{
  "status": "healthy",
  "app": "GhostBill",
  "version": "0.1.0",
  "detection": {
    "last_scan_at": "2026-04-25T10:00:00Z",
    "blocks_behind": 0,
    "height": 3650000
  }
}
```

---

### Merchants

#### `POST /v1/merchants` — Register Merchant

Register a new merchant. Returns live + test API keys (**shown once**).

**This is the only endpoint that does not require authentication.** Rate limited to 5/hour.

```bash
curl -X POST http://127.0.0.1:8013/v1/merchants \
  -H "Content-Type: application/json" \
  -d '{
    "primary_address": "4AdUndXHHZ6cfufTMvppY6JwXNouMBzSkbLYfpAV5Usx...",
    "view_key": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    "name": "My Store",
    "webhook_url": "https://mystore.com/webhooks/ghostbill"
  }'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `primary_address` | string | ✅ | Monero primary address (95–106 chars, starts with `4`) |
| `view_key` | string | ✅ | Secret view key (64 hex chars) |
| `name` | string | | Merchant display name (default: `"My Store"`) |
| `email` | string | | Contact email |
| `webhook_url` | string | | Webhook delivery URL |

**Response 201:** Returns merchant_id, API keys (live + test), and webhook_secret.

> ⚠️ **The API keys and webhook secret are shown ONCE.** Store them immediately.

---

#### `GET /v1/merchants/me` — Get Merchant Profile

```bash
curl http://127.0.0.1:8013/v1/merchants/me \
  -H "Authorization: Bearer gb_live_..."
```

**Response 200:**

```json
{
  "id": "efbfeade-1234-5678-abcd-1234567890ab",
  "name": "My Store",
  "email": "merchant@example.com",
  "monero_address": "4AdUndXHHZ6...",
  "webhook_url": "https://mystore.com/webhooks/ghostbill",
  "prepay_plans": [{"periods": 3, "discount_pct": 5}],
  "environment": "live",
  "is_active": true,
  "created_at": "2026-02-13T01:00:00Z",
  "updated_at": "2026-02-13T01:00:00Z"
}
```

---

#### `PATCH /v1/merchants/me` — Update Merchant Profile

Update name, email, webhook URL, or prepay plans configuration.

**Request body (all fields optional):**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | New display name (max 255) |
| `email` | string | New contact email (max 255) |
| `webhook_url` | string | New webhook URL (max 2048) |
| `prepay_plans` | array | Pre-payment plan configurations |

**Prepay plans format:**

```json
{
  "prepay_plans": [
    {"periods": 3, "discount_pct": 5},
    {"periods": 6, "discount_pct": 10},
    {"periods": 12, "discount_pct": 15}
  ]
}
```

---

#### `POST /v1/merchants/me/webhook-secret` — Regenerate Webhook Secret

Generate a new webhook signing secret. The old secret is immediately invalidated.

**Response 200:** Returns new `webhook_secret` (shown once).

---

### Invoices

#### `POST /v1/invoices` — Create Invoice

Create a new invoice with a unique Monero subaddress for payment.

```bash
curl -X POST http://127.0.0.1:8013/v1/invoices \
  -H "Authorization: Bearer gb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"amount_xmr": "0.5", "description": "Order #12345", "expires_in": 3600}'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `amount_xmr` | string | ✅ | XMR amount as string (e.g., `"0.5"`) |
| `description` | string | | Invoice description (max 1024) |
| `expires_in` | integer | | Seconds until expiry: 600–86400 (default: 3600) |
| `metadata` | object | | Arbitrary JSON metadata |

**Response 201:** Returns `InvoiceResponse` with status `pending`, generated subaddress, and fiat conversion.

**Invoice statuses:**

| Status | Description |
|--------|-------------|
| `pending` | Awaiting payment |
| `paid` | Full amount confirmed (≥ 10 confirmations) |
| `expired` | Expiry time reached with no payment |
| `partially_paid` | Confirmed amount < invoice amount |
| `overpaid` | Confirmed amount > invoice amount |
| `late_paid` | Payment confirmed after invoice expired |
| `cancelled` | Manually cancelled (only pending with no payments) |

---

#### `GET /v1/invoices` — List Invoices

```bash
curl "http://127.0.0.1:8013/v1/invoices?status=pending&limit=10" \
  -H "Authorization: Bearer gb_live_..."
```

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by invoice status |
| `limit` | integer | Results per page (1–100, default 50) |
| `starting_after` | UUID | Cursor for next page |
| `ending_before` | UUID | Cursor for previous page |

**Response 200:**

```json
{
  "data": [{"id": "...", "status": "pending", "amount_xmr": "0.5", "...": "..."}],
  "has_more": true
}
```

---

#### `GET /v1/invoices/{invoice_id}` — Get Invoice Detail

Get a single invoice with payment details and paid amount.

**Response 200:** Returns `InvoiceDetailResponse` — includes all `InvoiceResponse` fields plus:

| Field | Type | Description |
|-------|------|-------------|
| `paid_atomic` | integer | Total piconero received (excluding orphaned) |
| `paid_xmr` | string | Total XMR received |
| `payments` | array | List of payments with tx_hash, amount, status, confirmations |

---

#### `POST /v1/invoices/{invoice_id}/cancel` — Cancel Invoice

Cancel a pending invoice. Only invoices with `status=pending` and zero payments can be cancelled.

---

### Payments

Payments are **read-only** — created automatically by the detection engine when Monero transactions are detected.

#### `GET /v1/payments` — List Payments

```bash
curl "http://127.0.0.1:8013/v1/payments?status=confirmed&limit=20" \
  -H "Authorization: Bearer gb_live_..."
```

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `invoice_id` | UUID | Filter by invoice |
| `status` | string | Filter: `detected`, `confirmed`, `orphaned` |
| `limit` | integer | Results per page (1–100) |
| `starting_after` / `ending_before` | UUID | Cursor pagination |

**Payment statuses:**

| Status | Description |
|--------|-------------|
| `detected` | Transaction seen in mempool |
| `confirmed` | Transaction has ≥ 10 confirmations |
| `orphaned` | Transaction disappeared (double-spend or reorg) |

---

#### `GET /v1/payments/{payment_id}` — Get Payment

Get a single payment with full details including tx_hash, block_height, and confirmation count.

---

### Customers

#### `POST /v1/customers` — Create Customer

Create a new customer for the authenticated merchant. Required for creating subscriptions.

```bash
curl -X POST http://127.0.0.1:8013/v1/customers \
  -H "Authorization: Bearer gb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"external_id": "user_123", "email": "alice@example.com", "metadata": {"plan": "pro"}}'
```

**Request body (all fields optional):**

| Field | Type | Description |
|-------|------|-------------|
| `external_id` | string | Your system's customer ID (max 255, unique per merchant) |
| `email` | string | Customer email (max 255) |
| `metadata` | object | Arbitrary JSON metadata |

**Response 201:**

```json
{
  "id": "cust-uuid-here",
  "merchant_id": "efbfeade-...",
  "external_id": "user_123",
  "email": "alice@example.com",
  "metadata": {"plan": "pro"},
  "created_at": "2026-04-25T10:00:00Z"
}
```

**Response 409:** `external_id` already exists for this merchant.

---

#### `GET /v1/customers` — List Customers

Cursor-paginated list. Query params: `limit`, `starting_after`, `ending_before`.

---

#### `GET /v1/customers/{customer_id}` — Get Customer

---

#### `PATCH /v1/customers/{customer_id}` — Update Customer

Update `external_id`, `email`, or `metadata`. Only provided fields are changed.

---

### Subscriptions

#### `POST /v1/subscriptions` — Create Subscription

Create a recurring billing subscription for a customer.

```bash
curl -X POST http://127.0.0.1:8013/v1/subscriptions \
  -H "Authorization: Bearer gb_live_..." \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "cust-uuid-here",
    "amount_xmr": "0.1",
    "interval_days": 30,
    "grace_days_soft": 3,
    "grace_days_hard": 7,
    "trial_days": 14
  }'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `customer_id` | string | ✅ | Customer UUID |
| `amount_xmr` | string | ✅ | XMR amount per billing period |
| `interval_days` | integer | ✅ | Billing interval in days (≥ 1) |
| `grace_days_soft` | integer | | Days before `past_due` (default: 3) |
| `grace_days_hard` | integer | | Days before `expired` (default: 7) |
| `start_at` | string | | ISO datetime for first billing (default: now) |
| `trial_days` | integer | | Trial period 1–365 days (no invoice until trial ends) |
| `metadata` | object | | Arbitrary JSON metadata |

**Response 201:** Returns `SubscriptionDetailResponse` with status `active` (or `trialing` if trial_days set).

**Subscription statuses:**

| Status | Description |
|--------|-------------|
| `active` | Subscription is active, invoices are generated |
| `trialing` | Trial period active, no invoices yet |
| `paused` | Paused by merchant, no renewals |
| `past_due` | Renewal invoice unpaid past soft grace |
| `cancelled` | Cancelled, no further renewals |
| `expired` | Hard grace period exceeded |

---

#### `GET /v1/subscriptions` — List Subscriptions

```bash
curl "http://127.0.0.1:8013/v1/subscriptions?status=active&limit=20" \
  -H "Authorization: Bearer gb_live_..."
```

**Query parameters:** `status`, `customer_id`, `limit`, `starting_after`, `ending_before`.

---

#### `GET /v1/subscriptions/{subscription_id}` — Get Subscription Detail

Returns full subscription with customer info, payment history, and pending changes.

---

#### `GET /v1/subscriptions/{subscription_id}/renewal-log` — Renewal Event Log

Cursor-paginated audit trail of every renewal attempt (success, skip, failure, grace).

```bash
curl "http://127.0.0.1:8013/v1/subscriptions/sub-uuid/renewal-log?limit=20" \
  -H "Authorization: Bearer gb_live_..."
```

**Response 200:**

```json
{
  "data": [
    {
      "id": "event-uuid",
      "subscription_id": "sub-uuid",
      "result": "renewed",
      "invoice_id": "inv-uuid",
      "error_message": null,
      "details": {},
      "created_at": "2026-04-25T00:00:00Z"
    }
  ],
  "has_more": false
}
```

**Renewal result types:** `renewed`, `skipped_not_due`, `skipped_pending_invoice`, `grace_soft`, `grace_hard_expired`, `wallet_error`, `creation_error`, `trial_activated`, `prepay_active`, `prepay_cleared`.

---

#### `PATCH /v1/subscriptions/{subscription_id}` — Update Subscription

Queue pending changes to be applied at next renewal. Metadata updates are immediate.

```bash
curl -X PATCH http://127.0.0.1:8013/v1/subscriptions/sub-uuid \
  -H "Authorization: Bearer gb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"amount_xmr": "0.2", "interval_days": 14}'
```

**Request body (all optional):**

| Field | Type | Description |
|-------|------|-------------|
| `amount_xmr` | string | New XMR amount (applied at next renewal) |
| `interval_days` | integer | New billing interval (applied at next renewal) |
| `grace_days_soft` | integer | New soft grace (applied at next renewal) |
| `grace_days_hard` | integer | New hard grace (applied at next renewal) |
| `metadata` | object | Updated metadata (applied immediately) |

Pending changes are visible in the `pending_changes` field and `has_pending_changes: true`.

---

#### `POST /v1/subscriptions/{subscription_id}/pause` — Pause

Pause an active subscription. No renewals are generated until resumed.

---

#### `POST /v1/subscriptions/{subscription_id}/resume` — Resume

Resume a paused subscription. Next renewal is rescheduled.

---

#### `POST /v1/subscriptions/{subscription_id}/cancel` — Cancel

Cancel a subscription. No further renewals. Cannot be undone.

---

#### `POST /v1/subscriptions/{subscription_id}/prepay` — Pre-Pay

Pre-pay multiple billing periods with an optional discount.

```bash
curl -X POST http://127.0.0.1:8013/v1/subscriptions/sub-uuid/prepay \
  -H "Authorization: Bearer gb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"periods": 6}'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `periods` | integer | ✅ | Number of periods to prepay (1–36) |

The discount is determined by the merchant's `prepay_plans` configuration. If no matching plan exists, the request is rejected.

**Response 201:**

```json
{
  "subscription_id": "sub-uuid",
  "invoice_id": "inv-uuid",
  "periods": 6,
  "discount_pct": 10,
  "per_period_xmr": "0.100000000000",
  "total_xmr": "0.540000000000",
  "total_atomic": 540000000000,
  "prepaid_until": "2026-10-25T00:00:00Z",
  "invoice_expires_at": "2026-04-25T11:00:00Z"
}
```

---

### Webhooks & Dead Letter Queue

#### `GET /v1/webhooks` — List Webhook Deliveries

```bash
curl "http://127.0.0.1:8013/v1/webhooks?status=failed&limit=10" \
  -H "Authorization: Bearer gb_live_..."
```

**Query parameters:** `invoice_id`, `status` (`pending`, `delivered`, `failed`, `dead_lettered`), `limit`, `starting_after`, `ending_before`.

**Webhook delivery statuses:**

| Status | Description |
|--------|-------------|
| `pending` | Delivery queued or awaiting retry |
| `delivered` | Endpoint returned HTTP `2xx` |
| `failed` | Delivery failed but retries not exhausted |
| `dead_lettered` | All 7 retries exhausted, moved to DLQ |

---

#### `GET /v1/webhooks/{delivery_id}` — Get Webhook Delivery

Full details including payload, response_code, response_body, attempt count, next_retry_at.

---

#### `POST /v1/webhooks/{delivery_id}/retry` — Retry Webhook

Manually retry a failed delivery. Resets attempt counter. Only `status=failed` can be retried.

---

#### `GET /v1/webhooks/dead-letters` — List Dead Letter Queue

List webhook deliveries that exhausted all 7 retry attempts.

```bash
curl "http://127.0.0.1:8013/v1/webhooks/dead-letters?resolved=false" \
  -H "Authorization: Bearer gb_live_..."
```

**Query parameters:** `resolved` (bool), `limit`, `starting_after`, `ending_before`.

**Response 200:**

```json
{
  "data": [
    {
      "id": "dlq-uuid",
      "delivery_id": "wh-delivery-uuid",
      "merchant_id": "efbfeade-...",
      "event_type": "invoice.paid",
      "payload": {},
      "original_created_at": "2026-04-20T10:00:00Z",
      "dead_lettered_at": "2026-04-22T00:00:00Z",
      "last_error": "Connection refused",
      "retry_count": 0,
      "resolved": false
    }
  ],
  "has_more": false
}
```

---

#### `POST /v1/webhooks/dead-letters/{dlq_id}/retry` — Retry from DLQ

Create a new webhook delivery with the original payload. Resets the retry counter.

---

### API Keys

#### `GET /v1/api-keys` — List API Keys

List all API keys for the authenticated merchant (masked — prefix only).

---

#### `POST /v1/api-keys` — Create API Key

```bash
curl -X POST http://127.0.0.1:8013/v1/api-keys \
  -H "Authorization: Bearer gb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"label": "Staging Server", "environment": "test"}'
```

**Request body:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `label` | string | `null` | Human-readable label (max 255) |
| `environment` | string | `"live"` | `live` or `test` |

**Response 201:** Returns full plaintext key (shown once), key_prefix, label, environment.

> ⚠️ **The `key` field is shown ONCE.** It cannot be retrieved again.

---

#### `DELETE /v1/api-keys/{key_id}` — Revoke API Key

Soft-delete an API key. You cannot revoke the key currently being used for authentication.

---

### Analytics

All analytics endpoints require merchant authentication. Results are cached in Redis (5-minute TTL).

#### `GET /v1/analytics/revenue` — Revenue Over Time

```bash
curl "http://127.0.0.1:8013/v1/analytics/revenue?period=30d" \
  -H "Authorization: Bearer gb_live_..."
```

**Query parameters:**

| Parameter | Type | Values | Default |
|-----------|------|--------|---------|
| `period` | string | `7d`, `30d`, `90d`, `1y` | `30d` |

**Response 200:**

```json
{
  "period": "30d",
  "data": [
    {"date": "2026-04-01", "count": 5, "amount_atomic": 2500000000000, "amount_xmr": "2.500000000000"},
    {"date": "2026-04-02", "count": 3, "amount_atomic": 1500000000000, "amount_xmr": "1.500000000000"}
  ],
  "total_atomic": 4000000000000,
  "total_xmr": "4.000000000000",
  "total_payments": 8
}
```

---

#### `GET /v1/analytics/invoices` — Invoice Status Breakdown

```bash
curl "http://127.0.0.1:8013/v1/analytics/invoices?period_days=30" \
  -H "Authorization: Bearer gb_live_..."
```

**Query parameters:** `period_days` (1–365, default 30).

**Response 200:**

```json
{
  "total": 42,
  "data": [
    {"status": "paid", "count": 30},
    {"status": "expired", "count": 8},
    {"status": "pending", "count": 4}
  ],
  "period_days": 30
}
```

---

#### `GET /v1/analytics/subscriptions` — Subscription Metrics

```bash
curl http://127.0.0.1:8013/v1/analytics/subscriptions \
  -H "Authorization: Bearer gb_live_..."
```

**Response 200:**

```json
{
  "active": 85,
  "paused": 3,
  "past_due": 5,
  "cancelled": 12,
  "expired": 8,
  "total": 113,
  "mrr_atomic": 8500000000000,
  "mrr_xmr": "8.500000000000",
  "churn_30d": 4,
  "new_30d": 15
}
```

---

### Dashboard Auth (Monero Signature)

Passwordless authentication flow based on Monero message signing. Used by the web dashboard.

**Flow:**
1. Request a nonce for your Monero address
2. Sign the nonce with `monero-wallet-cli sign`
3. Submit the signature to get a session token (`gbs_<hex64>`)
4. Use the session token for dashboard requests

---

#### `POST /v1/auth/nonce` — Request Nonce

Request a one-time nonce bound to a Monero address. Expires in 5 minutes.

**Request body:** `{"address": "4AdUndXHHZ6..."}`

**Response 200:** `{"nonce": "ghostbill_auth_a1b2c3d4...", "expires_in": 300}`

---

#### `POST /v1/auth/verify` — Verify Signature

Verify the Monero signature and receive a session token.

**Request body:** `{"address": "...", "nonce": "...", "signature": "SigV2..."}`

**Response 200:** `{"session_token": "gbs_...", "expires_in": 86400, "merchant_id": "..."}`

---

#### `POST /v1/auth/logout` — Logout

Revoke a session token.

**Request body:** `{"session_token": "gbs_..."}`

**Response 200:** `{"revoked": true}`

---

### Price

#### `GET /v1/price` — Get XMR Price

Current XMR price in USD and EUR. No authentication required. Cached in Redis, updated every 60 seconds.

```bash
curl http://127.0.0.1:8013/v1/price
```

**Response 200:**

```json
{
  "xmr_usd": "145.00",
  "xmr_eur": "133.50",
  "source": "coingecko",
  "updated_at": "2026-04-25T10:00:00Z",
  "stale": false
}
```

The `stale` field is `true` if the price data is older than 10 minutes.

---

### Public Endpoints

These endpoints require **no authentication**. They are rate-limited via the public tier (300/min per IP).

#### `GET /v1/invoices/{invoice_id}/public` — Public Invoice Data

Get limited invoice data for the payment page. Response is filtered — never exposes merchant_id, metadata, webhook_url, or API keys.

```bash
curl http://127.0.0.1:8013/v1/invoices/inv-uuid/public
```

**Response 200:**

```json
{
  "id": "inv-uuid",
  "amount_xmr": "0.500000000000",
  "amount_atomic": 500000000000,
  "fiat_amount": "72.50",
  "fiat_currency": "USD",
  "description": "Order #12345",
  "address": "8BxyzSubaddress...",
  "status": "pending",
  "expires_at": "2026-04-25T11:00:00Z",
  "created_at": "2026-04-25T10:00:00Z",
  "confirmations": 0,
  "confirmations_required": 10,
  "paid_amount_atomic": 0,
  "monero_uri": "monero:8Bxyz...?tx_amount=0.500000000000",
  "qr_svg": "<svg>...</svg>"
}
```

---

#### `GET /v1/invoices/{invoice_id}/events` — SSE Real-Time Updates

Server-Sent Events stream for real-time invoice status updates. No authentication — UUID serves as access token.

Polls DB every 3 seconds server-side, pushes only on changes. Auto-closes on terminal status (paid/expired/cancelled) or after 30 minutes.

```javascript
const es = new EventSource('/v1/invoices/<id>/events');
es.addEventListener('update', (e) => render(JSON.parse(e.data)));
es.addEventListener('close', () => es.close());
```

**Events:** `update` (full invoice data), `close` (terminal state or timeout).

---

#### `GET /pay/{invoice_id}` — Payment Page

Serve standalone HTML payment page. Not included in OpenAPI schema.

---

### Admin (Operator)

Admin endpoints are available only to the instance operator. The admin merchant is configured via `ADMIN_MERCHANT_ID` in `.env`. All endpoints require standard merchant authentication — the admin guard checks `merchant.id == ADMIN_MERCHANT_ID`.

#### `GET /v1/admin/me` — Check Admin Status

Soft check (returns bool, no 403). Used by the dashboard sidebar to conditionally show the Admin link.

**Response 200:** `{"is_admin": true}`

---

#### `GET /v1/admin/merchants` — List All Merchants

List all merchants with invoice and subscription counts.

---

#### `POST /v1/admin/merchants/{merchant_id}/toggle` — Toggle Merchant

Activate or deactivate a merchant.

---

#### `GET /v1/admin/stats` — Global Statistics

System-wide stats: total merchants, invoices, payments, revenue, subscriptions, DLQ entries.

---

#### `GET /v1/admin/health` — Detailed Health

Detailed system health including DB connection pool, Redis memory usage, wallet-rpc block height, and detection engine status.

---

#### `GET /v1/admin/dlq` — Global Dead Letter Queue

DLQ entries across all merchants (not scoped to admin's merchant).

---

#### `POST /v1/admin/dlq/{dlq_id}/retry` — Admin DLQ Retry

Retry any DLQ entry regardless of merchant.

---

#### `POST /v1/admin/trigger-renewal` — Trigger Renewal Sweep

Manually trigger the subscription renewal engine. Returns count of renewed/skipped/failed.

**Response 200:** `{"renewed": 3, "skipped": 12, "failed": 0}`

---

## Environments

GhostBill supports `live` and `test` environments:

| Environment | Key prefix | Description |
|-------------|-----------|-------------|
| Live | `gb_live_` | Real Monero transactions |
| Test | `gb_test_` | Testing and development |

Each merchant receives both a live and test API key on registration. Keys are scoped to their environment.
