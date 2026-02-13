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
- [Endpoints](#endpoints)
  - [Health](#health)
  - [Merchants](#merchants)
  - [Invoices](#invoices)
  - [Payments](#payments)
  - [Webhooks](#webhooks)
  - [API Keys](#api-keys)
  - [Dashboard Auth (Monero Signature)](#dashboard-auth-monero-signature)
  - [Price](#price)

---

## Authentication

GhostBill uses **Bearer token** authentication with API keys.

**Header format:**

```
Authorization: Bearer <api_key>
```

**API key format:**

| Environment | Format | Example |
|-------------|--------|---------|
| Live | `gb_live_<hex32>` | `gb_live_5d347e8b575d6d546f7f8af504461ce7` |
| Test | `gb_test_<hex32>` | `gb_test_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6` |

**Key storage:**
- Keys are shown **once** at creation — store them securely
- Keys are hashed with **bcrypt (cost ≥ 12)** before storage
- Only the prefix (`gb_live_` / `gb_test_`) is stored in plaintext for identification
- Max **10 active keys** per merchant

**Dashboard authentication** uses a separate Monero signature flow (see [Dashboard Auth](#dashboard-auth-monero-signature)). Session tokens use the format `gbs_<hex64>` with 24-hour TTL.

**Example:**

```bash
curl -X GET http://127.0.0.1:8013/v1/merchants/me \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Unauthenticated endpoints:** `GET /health`, `GET /v1/price`

---

## Amounts & Precision

GhostBill uses **two representations** for Monero amounts:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `amount_xmr` | `string` | Human-readable XMR amount (display only) | `"0.500000000000"` |
| `amount_atomic` | `integer` (BIGINT) | Piconero — **source of truth** | `500000000000` |

**Conversion:** `1 XMR = 10^12 piconero (atomic units)`

Always use `amount_atomic` for calculations and comparisons. The `amount_xmr` field is provided for display convenience and should never be used for arithmetic.

**Dust threshold:** Payments below `100000000` atomic (0.0001 XMR) are ignored by the detection engine.

---

## Rate Limiting

All authenticated endpoints are rate-limited. Limits are returned in response headers:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Max requests per window |
| `X-RateLimit-Remaining` | Remaining requests |
| `X-RateLimit-Reset` | Unix timestamp when window resets |
| `Retry-After` | Seconds until next allowed request (only on 429) |

**Tiers:**

| Tier | Endpoints | Limit |
|------|-----------|-------|
| Strict | `POST /v1/merchants` | 5/hour |
| Write | `POST /v1/invoices`, `POST /v1/api-keys` | 60/min |
| Read | `GET /v1/invoices`, `GET /v1/payments`, etc. | 120/min |
| Public | `GET /health`, `GET /v1/price` | 300/min |

**429 response:**

```json
{
  "detail": "Rate limit exceeded. Retry after 42 seconds."
}
```

---

## Error Handling

GhostBill returns standard HTTP status codes with JSON error bodies.

**Error format:**

```json
{
  "detail": "Human-readable error message"
}
```

**Validation error format (422):**

```json
{
  "detail": [
    {
      "loc": ["body", "amount_xmr"],
      "msg": "field required",
      "type": "missing"
    }
  ]
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

## Endpoints

### Health

#### `GET /health`

Health check. No authentication required.

```bash
curl http://127.0.0.1:8013/health
```

**Response 200:**

```json
{
  "status": "healthy",
  "app": "GhostBill",
  "version": "0.1.0"
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
    "primary_address": "4AdUndXHHZ6cfufTMvppY6JwXNouMBzSkbLYfpAV5Usx3skxNgYeYTRJ5UptMnMVf...",
    "view_key": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    "name": "My Store",
    "email": "merchant@example.com",
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

**Response 201:**

```json
{
  "merchant_id": "efbfeade-1234-5678-abcd-1234567890ab",
  "name": "My Store",
  "environment": "live",
  "api_keys": {
    "live": "gb_live_5d347e8b575d6d546f7f8af504461ce7",
    "test": "gb_test_a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
  },
  "webhook_secret": "whsec_7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c",
  "message": "Store your API keys securely. They will NOT be shown again."
}
```

> ⚠️ **The API keys and webhook secret are shown ONCE.** Store them immediately in a secure location.

**Security note:** The `view_key` is encrypted with AES-256-GCM before storage. GhostBill operates in **view-only mode** — it cannot spend your funds.

---

#### `GET /v1/merchants/me` — Get Merchant Profile

Get current authenticated merchant profile.

```bash
curl http://127.0.0.1:8013/v1/merchants/me \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Response 200:**

```json
{
  "id": "efbfeade-1234-5678-abcd-1234567890ab",
  "name": "My Store",
  "email": "merchant@example.com",
  "monero_address": "4AdUndXHHZ6cfufTMvppY6JwXNouMBzSkbLYfpAV5Usx...",
  "webhook_url": "https://mystore.com/webhooks/ghostbill",
  "environment": "live",
  "is_active": true,
  "created_at": "2026-02-13T01:00:00Z",
  "updated_at": "2026-02-13T01:00:00Z"
}
```

---

#### `PATCH /v1/merchants/me` — Update Merchant Profile

Update name, email, or webhook URL.

```bash
curl -X PATCH http://127.0.0.1:8013/v1/merchants/me \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Store Name",
    "webhook_url": "https://newdomain.com/webhooks"
  }'
```

**Request body (all fields optional):**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | New display name (max 255) |
| `email` | string | New contact email (max 255) |
| `webhook_url` | string | New webhook URL (max 2048) |

**Response 200:**

```json
{
  "id": "efbfeade-1234-5678-abcd-1234567890ab",
  "name": "Updated Store Name",
  "email": "merchant@example.com",
  "webhook_url": "https://newdomain.com/webhooks",
  "updated_at": "2026-02-13T02:00:00Z",
  "message": "Merchant updated successfully."
}
```

---

#### `POST /v1/merchants/me/webhook-secret` — Regenerate Webhook Secret

Generate a new webhook signing secret. The old secret is immediately invalidated.

```bash
curl -X POST http://127.0.0.1:8013/v1/merchants/me/webhook-secret \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Response 200:**

```json
{
  "webhook_secret": "whsec_9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d",
  "message": "New webhook secret generated. Update your integration."
}
```

> ⚠️ **The new secret is shown ONCE.** Update your webhook verification code immediately.

---

### Invoices

#### `POST /v1/invoices` — Create Invoice

Create a new invoice with a unique Monero subaddress for payment.

```bash
curl -X POST http://127.0.0.1:8013/v1/invoices \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7" \
  -H "Content-Type: application/json" \
  -d '{
    "amount_xmr": "0.5",
    "description": "Order #12345",
    "expires_in": 3600,
    "metadata": {"order_id": "12345", "customer": "alice"}
  }'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `amount_xmr` | string | ✅ | XMR amount as string (e.g., `"0.5"`, `"1.25"`) |
| `description` | string | | Invoice description (max 1024) |
| `expires_in` | integer | | Seconds until expiry: 600–86400 (default: 3600) |
| `metadata` | object | | Arbitrary JSON metadata |

**Response 201:**

```json
{
  "id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "merchant_id": "efbfeade-1234-5678-abcd-1234567890ab",
  "amount_xmr": "0.500000000000",
  "amount_atomic": 500000000000,
  "fiat_currency": "USD",
  "fiat_amount": "72.50",
  "fiat_rate": "145.00",
  "status": "pending",
  "description": "Order #12345",
  "metadata": {"order_id": "12345", "customer": "alice"},
  "address": "8BxyzSubaddressForThisInvoice...",
  "address_index": 42,
  "expires_at": "2026-02-13T05:00:00Z",
  "paid_at": null,
  "created_at": "2026-02-13T04:00:00Z",
  "updated_at": "2026-02-13T04:00:00Z"
}
```

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

List invoices for the authenticated merchant with optional filtering and pagination.

```bash
# List all invoices
curl http://127.0.0.1:8013/v1/invoices \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"

# Filter by status with pagination
curl "http://127.0.0.1:8013/v1/invoices?status=pending&limit=10&offset=0" \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | | Filter by invoice status |
| `limit` | integer | 50 | Results per page (1–100) |
| `offset` | integer | 0 | Pagination offset |

**Response 200:**

```json
{
  "invoices": [
    {
      "id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
      "merchant_id": "efbfeade-...",
      "amount_xmr": "0.500000000000",
      "amount_atomic": 500000000000,
      "status": "pending",
      "address": "8Bxyz...",
      "expires_at": "2026-02-13T05:00:00Z",
      "..."
    }
  ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

---

#### `GET /v1/invoices/{invoice_id}` — Get Invoice

Get a single invoice by UUID.

```bash
curl http://127.0.0.1:8013/v1/invoices/a1b2c3d4-5678-90ab-cdef-1234567890ab \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Response 200:** Same as `InvoiceResponse` above.

**Response 404:**

```json
{
  "detail": "Invoice not found"
}
```

---

#### `POST /v1/invoices/{invoice_id}/cancel` — Cancel Invoice

Cancel a pending invoice. **Only invoices with status `pending` and zero payments can be cancelled.**

```bash
curl -X POST http://127.0.0.1:8013/v1/invoices/a1b2c3d4-5678-90ab-cdef-1234567890ab/cancel \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Response 200:** Returns the invoice with `"status": "cancelled"`.

**Response 400:**

```json
{
  "detail": "Only pending invoices with no payments can be cancelled"
}
```

---

### Payments

Payments are **read-only** — they are created automatically by the detection engine when Monero transactions are detected on an invoice's subaddress.

#### `GET /v1/payments` — List Payments

```bash
# List all payments
curl http://127.0.0.1:8013/v1/payments \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"

# Filter by invoice
curl "http://127.0.0.1:8013/v1/payments?invoice_id=a1b2c3d4-5678-90ab-cdef-1234567890ab" \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"

# Filter by status
curl "http://127.0.0.1:8013/v1/payments?status=confirmed&limit=20" \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `invoice_id` | string | | Filter by invoice UUID |
| `status` | string | | Filter: `detected`, `confirmed`, `orphaned` |
| `limit` | integer | 50 | Results per page (1–100) |
| `offset` | integer | 0 | Pagination offset |

**Response 200:**

```json
{
  "payments": [
    {
      "id": "pay-uuid-here",
      "invoice_id": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
      "tx_hash": "7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e",
      "amount_atomic": 500000000000,
      "amount_xmr": "0.500000000000",
      "status": "confirmed",
      "confirmations": 12,
      "block_height": 3608850,
      "detected_at": "2026-02-13T04:15:00Z",
      "confirmed_at": "2026-02-13T04:35:00Z",
      "created_at": "2026-02-13T04:15:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

**Payment statuses:**

| Status | Description |
|--------|-------------|
| `detected` | Transaction seen in mempool (`pool: true`) |
| `confirmed` | Transaction has ≥ 10 confirmations |
| `orphaned` | Transaction disappeared from mempool/chain (double-spend or reorg) |

---

#### `GET /v1/payments/{payment_id}` — Get Payment

```bash
curl http://127.0.0.1:8013/v1/payments/pay-uuid-here \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Response 200:** Same as `PaymentResponse` above.

---

### Webhooks

#### `GET /v1/webhooks` — List Webhook Deliveries

```bash
# List all deliveries
curl http://127.0.0.1:8013/v1/webhooks \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"

# Filter by invoice and status
curl "http://127.0.0.1:8013/v1/webhooks?invoice_id=a1b2c3d4-...&status=failed" \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `invoice_id` | string | | Filter by invoice UUID |
| `status` | string | | Filter: `pending`, `delivered`, `failed` |
| `limit` | integer | 50 | Results per page (1–100) |
| `offset` | integer | 0 | Pagination offset |

**Response 200:**

```json
{
  "deliveries": [
    {
      "id": "wh-delivery-uuid",
      "merchant_id": "efbfeade-...",
      "invoice_id": "a1b2c3d4-...",
      "event_type": "payment.confirmed",
      "payload": { "...": "..." },
      "url": "https://mystore.com/webhooks/ghostbill",
      "status": "delivered",
      "attempts": 1,
      "max_attempts": 7,
      "last_attempt_at": "2026-02-13T04:36:00Z",
      "next_retry_at": null,
      "response_code": 200,
      "response_body": "OK",
      "created_at": "2026-02-13T04:35:00Z"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

---

#### `GET /v1/webhooks/{delivery_id}` — Get Webhook Delivery

Get a single webhook delivery with full payload and response details.

```bash
curl http://127.0.0.1:8013/v1/webhooks/wh-delivery-uuid \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Response 200:** Same as `WebhookDeliveryResponse` above.

---

#### `POST /v1/webhooks/{delivery_id}/retry` — Retry Webhook

Manually retry a failed webhook delivery. Only deliveries with `status=failed` can be retried. Resets attempt counter and schedules immediate delivery.

```bash
curl -X POST http://127.0.0.1:8013/v1/webhooks/wh-delivery-uuid/retry \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Response 200:** Returns the delivery with reset `attempts` and `status=pending`.

**Response 400:**

```json
{
  "detail": "Only failed deliveries can be retried"
}
```

---

### API Keys

#### `GET /v1/api-keys` — List API Keys

List all API keys for the authenticated merchant. Keys are masked — only prefix, label, and metadata shown.

```bash
curl http://127.0.0.1:8013/v1/api-keys \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Response 200:**

```json
{
  "api_keys": [
    {
      "id": "key-uuid-1",
      "key_prefix": "gb_live_5d34...",
      "label": "Production Server",
      "environment": "live",
      "is_active": true,
      "last_used_at": "2026-02-13T04:00:00Z",
      "created_at": "2026-02-13T01:00:00Z"
    },
    {
      "id": "key-uuid-2",
      "key_prefix": "gb_test_a1b2...",
      "label": null,
      "environment": "test",
      "is_active": true,
      "last_used_at": null,
      "created_at": "2026-02-13T01:00:00Z"
    }
  ],
  "total": 2
}
```

---

#### `POST /v1/api-keys` — Create API Key

Create a new API key. The full plaintext key is returned **once** in the response. Max 10 active keys per merchant.

```bash
curl -X POST http://127.0.0.1:8013/v1/api-keys \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "Staging Server",
    "environment": "test"
  }'
```

**Request body:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `label` | string | `null` | Human-readable label (max 255) |
| `environment` | string | `"live"` | `live` or `test` |

**Response 201:**

```json
{
  "id": "key-uuid-new",
  "key": "gb_test_f1e2d3c4b5a6978869504132fabcde01",
  "key_prefix": "gb_test_f1e2...",
  "label": "Staging Server",
  "environment": "test"
}
```

> ⚠️ **The `key` field is shown ONCE.** It cannot be retrieved again.

---

#### `DELETE /v1/api-keys/{key_id}` — Revoke API Key

Revoke (deactivate) an API key. This is a **soft delete** — the key hash remains in the database for audit purposes. You cannot revoke the key currently being used for authentication.

```bash
curl -X DELETE http://127.0.0.1:8013/v1/api-keys/key-uuid-1 \
  -H "Authorization: Bearer gb_live_5d347e8b575d6d546f7f8af504461ce7"
```

**Response 200:**

```json
{
  "message": "API key revoked"
}
```

**Response 400:**

```json
{
  "detail": "Cannot revoke the key currently in use"
}
```

---

### Dashboard Auth (Monero Signature)

The dashboard uses a **passwordless authentication flow** based on Monero message signing. This is separate from API key authentication and is used exclusively by the web dashboard.

**Flow:**
1. Request a nonce for your Monero address
2. Sign the nonce with `monero-wallet-cli sign`
3. Submit the signature to get a session token (`gbs_<hex64>`)
4. Use the session token for dashboard requests

---

#### `POST /v1/auth/nonce` — Request Nonce

Request a one-time nonce bound to a Monero address. Expires in 5 minutes.

```bash
curl -X POST http://127.0.0.1:8013/v1/auth/nonce \
  -H "Content-Type: application/json" \
  -d '{"address": "4AdUndXHHZ6cfufTMvppY6JwXNouMBzSkbLYfpAV5Usx3skxNgYeYTRJ5..."}'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `address` | string | ✅ | Monero primary address (95 chars, starts with `4`) |

**Response 200:**

```json
{
  "nonce": "ghostbill_auth_a1b2c3d4e5f6a7b8...",
  "expires_in": 300
}
```

---

#### `POST /v1/auth/verify` — Verify Signature

Verify the Monero signature and receive a session token. The nonce is consumed (single-use) regardless of verification result.

```bash
curl -X POST http://127.0.0.1:8013/v1/auth/verify \
  -H "Content-Type: application/json" \
  -d '{
    "address": "4AdUndXHHZ6cfufTMvppY6JwXNouMBzSkbLYfpAV5Usx3skxNgYeYTRJ5...",
    "nonce": "ghostbill_auth_a1b2c3d4e5f6a7b8...",
    "signature": "SigV2..."
  }'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `address` | string | ✅ | Monero primary address |
| `nonce` | string | ✅ | Nonce from `/auth/nonce` response |
| `signature` | string | ✅ | Signature from `monero-wallet-cli sign` |

**Response 200:**

```json
{
  "session_token": "gbs_a1b2c3d4e5f6...64hexchars...",
  "expires_in": 86400,
  "merchant_id": "efbfeade-1234-5678-abcd-1234567890ab"
}
```

---

#### `POST /v1/auth/logout` — Logout

Revoke a session token.

```bash
curl -X POST http://127.0.0.1:8013/v1/auth/logout \
  -H "Content-Type: application/json" \
  -d '{"session_token": "gbs_a1b2c3d4e5f6...64hexchars..."}'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_token` | string | ✅ | Session token (`gbs_...`) to revoke |

**Response 200:**

```json
{
  "revoked": true
}
```

---

### Price

#### `GET /v1/price` — Get XMR Price

Get current XMR price in USD and EUR. No authentication required. Data is cached in Redis and updated every 60 seconds by a background task.

```bash
curl http://127.0.0.1:8013/v1/price
```

**Response 200:**

```json
{
  "xmr_usd": "145.00",
  "xmr_eur": "133.50",
  "source": "coingecko",
  "updated_at": "2026-02-13T04:00:00Z",
  "stale": false
}
```

The `stale` field is `true` if the price data is older than 10 minutes, indicating potential issues with the price feed.

---

## Pagination

All list endpoints support offset-based pagination:

```
GET /v1/invoices?limit=10&offset=20
```

The response includes `total`, `limit`, and `offset` fields to help navigate pages:

```json
{
  "invoices": [...],
  "total": 142,
  "limit": 10,
  "offset": 20
}
```

---

## Environments

GhostBill supports `live` and `test` environments:

| Environment | Key prefix | Description |
|-------------|-----------|-------------|
| Live | `gb_live_` | Real Monero transactions |
| Test | `gb_test_` | Testing and development |

Each merchant receives both a live and test API key on registration. Keys are scoped to their environment — a `gb_test_` key can only access test resources.
