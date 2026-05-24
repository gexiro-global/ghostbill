# GhostBill Merchant Cookbook

**Version:** v1.3-rc3
**Audience:** merchants integrating GhostBill into checkout, billing, or e-commerce platforms.
**Status:** audited release candidate. Verify every endpoint against the deployed [API reference](./API.md) before going live.

This cookbook is task-oriented: it shows complete end-to-end flows you can copy, adapt, and run. For the full endpoint reference see [`API.md`](./API.md). For webhook event schemas and signature verification helpers see [`WEBHOOKS.md`](./WEBHOOKS.md).

All examples use placeholder values:

* API keys: `gb_live_xxx...` or `gb_test_xxx...`
* Webhook URL: `https://merchant.example/webhooks/ghostbill`
* Return URL: `https://merchant.example/orders/ORDER-1001`
* Order ID: `ORDER-1001`
* Customer ID: `CUSTOMER-1001`
* Base URL: `https://your-ghostbill.example/v1` — your own GhostBill instance, clearnet or onion.

Replace every placeholder with values from your environment. Never paste production keys, real customer data, or wallet seeds into examples, logs, or issues.

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Authentication](#2-authentication)
3. [Recipe: one-time payment](#3-recipe-one-time-payment)
4. [Recipe: subscription billing](#4-recipe-subscription-billing)
5. [Recipe: webhook integration](#5-recipe-webhook-integration)
6. [Recipe: reconciliation](#6-recipe-reconciliation)
7. [Handling invoice and payment states](#7-handling-invoice-and-payment-states)
8. [Operational checklist](#8-operational-checklist)
9. [Quick troubleshooting](#9-quick-troubleshooting)
10. [Security and anti-scam](#10-security-and-anti-scam)
11. [End-to-end example](#11-end-to-end-example)

---

## 1. Prerequisites

Before you start you need:

* A reachable GhostBill instance. Self-hosted with Docker Compose (see [`DEPLOYMENT.md`](./DEPLOYMENT.md)) or a hosted instance you control.
* A Monero primary address (starts with `4`) and the matching **secret view key** (64 hex chars). GhostBill is non-custodial — your **spend key never leaves your wallet** and is never sent to GhostBill.
* A webhook endpoint on your platform reachable from the GhostBill instance.
* `curl` and `jq` for the examples below.

GhostBill does NOT require, store, or accept:

* spend keys
* mnemonic / seed phrases
* wallet files

If any tool or person claiming to be a GhostBill maintainer asks for these, treat it as a scam attempt (see § 10).

---

## 2. Authentication

All authenticated endpoints use the `Authorization: Bearer <api_key>` header.

API keys come in two environments:

* `gb_live_<hex>` — production traffic
* `gb_test_<hex>` — test environment (separate data)

You receive both keys once when you register a merchant. They are shown a single time and stored as bcrypt hashes server-side. If you lose a key, create a new one via `POST /v1/api-keys` and rotate.

**Example authenticated request:**

```bash
curl -X GET https://your-ghostbill.example/v1/merchants/me \
  -H "Authorization: Bearer gb_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

**Never** expose API keys in:

* frontend JavaScript or single-page apps
* mobile apps shipped to end users
* client-side analytics or error trackers
* commit history, public logs, or screenshots

Keep keys on your server. Have customer browsers talk to your server, not to GhostBill directly.

Rate limits apply per IP and per merchant. Defaults are documented in [`.env.example`](../.env.example) under `RATE_LIMIT_*`. Read endpoints are more generous than write endpoints. Build in exponential backoff if you see `429`.

---

## 3. Recipe: one-time payment

**Goal:** customer places an order, GhostBill issues a payment subaddress, you fulfill on confirmation.

### 3.1. Register merchant (one-time setup)

```bash
curl -X POST https://your-ghostbill.example/v1/merchants \
  -H "Content-Type: application/json" \
  -d '{
    "primary_address": "4xxx...",
    "view_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    "name": "My Store",
    "webhook_url": "https://merchant.example/webhooks/ghostbill"
  }'
```

Response includes `merchant_id`, both `api_keys` (`live` + `test`), and a one-time `webhook_secret`. Store everything in a secrets manager, not in source.

### 3.2. Create an invoice when the customer checks out

```bash
curl -X POST https://your-ghostbill.example/v1/invoices \
  -H "Authorization: Bearer gb_live_xxx..." \
  -H "Content-Type: application/json" \
  -d '{
    "amount_xmr": "0.5",
    "description": "ORDER-1001",
    "expires_in": 3600,
    "metadata": {
      "order_id": "ORDER-1001",
      "customer_id": "CUSTOMER-1001"
    }
  }'
```

Notes:

* `amount_xmr` is a string for precision. The server also returns `amount_atomic` (piconero, BIGINT). The atomic value is the source of truth.
* `description` and `metadata` are merchant-defined. Use them to attach your order ID so you can match webhooks to orders.
* `expires_in` is in seconds, range `600`–`86400`, default `3600`.

The response includes a unique Monero `address` (subaddress) you display to the customer.

### 3.3. Show the payment instructions to the customer

From the invoice response, you have:

* `address` — the Monero subaddress to pay (unique per invoice)
* `amount_xmr` — the amount the customer must send
* `expires_at` — ISO timestamp after which an unpaid invoice expires

A QR code containing `monero:<address>?tx_amount=<amount_xmr>` works in most Monero wallets.

### 3.4. Wait for confirmation

There are two ways to be notified:

* **Webhook (recommended).** GhostBill calls your `webhook_url` for every relevant event. See § 5.
* **Polling (fallback).** `GET /v1/invoices/{invoice_id}` returns the current `status` and embedded `payments[]`.

```bash
curl -X GET https://your-ghostbill.example/v1/invoices/<invoice_id> \
  -H "Authorization: Bearer gb_live_xxx..." | jq .
```

Fulfill the order when the invoice reaches a settled status (`paid`, `overpaid`, or `late_paid`) **and** the associated payment is `confirmed`. Do not fulfill on `payment.detected` alone — see § 7.

---

## 4. Recipe: subscription billing

**Goal:** recurring charges with grace periods and automatic renewal invoices.

### 4.1. Create a customer

```bash
curl -X POST https://your-ghostbill.example/v1/customers \
  -H "Authorization: Bearer gb_live_xxx..." \
  -H "Content-Type: application/json" \
  -d '{
    "external_id": "CUSTOMER-1001",
    "email": "customer@merchant.example",
    "metadata": {"plan": "pro"}
  }'
```

All fields are optional. Email is plain-text — do not include data you cannot store in your jurisdiction.

### 4.2. Create a subscription

```bash
curl -X POST https://your-ghostbill.example/v1/subscriptions \
  -H "Authorization: Bearer gb_live_xxx..." \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "<customer_uuid>",
    "amount_xmr": "0.5",
    "interval_days": 30,
    "grace_days_soft": 3,
    "grace_days_hard": 7,
    "metadata": {"plan": "pro", "order_ref": "ORDER-1001"}
  }'
```

Lifecycle:

* `active` — normal renewal cadence
* `past_due` — invoice unpaid past `grace_days_soft`. Customer can still pay.
* `expired` — unpaid past `grace_days_hard`. Subscription ends.
* `paused` — manually paused via `POST /v1/subscriptions/{id}/pause`
* `cancelled` — manually cancelled via `POST /v1/subscriptions/{id}/cancel`

Use the webhook events to drive your platform's state machine:

* `subscription.created`
* `subscription.renewed`
* `subscription.payment_confirmed`
* `subscription.past_due`
* `subscription.expired`
* `subscription.cancelled`
* `subscription.paused`, `subscription.resumed`, `subscription.updated`
* `subscription.trial_started`, `subscription.trial_ended`, `subscription.prepaid`

See [`WEBHOOKS.md`](./WEBHOOKS.md) for full payload schemas. The exact event registry and payload builders live in `backend/app/services/webhook_payloads.py`.

### 4.3. Update or cancel

```bash
# Pause
curl -X POST https://your-ghostbill.example/v1/subscriptions/<sub_id>/pause \
  -H "Authorization: Bearer gb_live_xxx..."

# Cancel (terminal)
curl -X POST https://your-ghostbill.example/v1/subscriptions/<sub_id>/cancel \
  -H "Authorization: Bearer gb_live_xxx..."

# Patch (e.g. change amount; takes effect at next renewal)
curl -X PATCH https://your-ghostbill.example/v1/subscriptions/<sub_id> \
  -H "Authorization: Bearer gb_live_xxx..." \
  -H "Content-Type: application/json" \
  -d '{"amount_xmr": "0.6"}'
```

---

## 5. Recipe: webhook integration

GhostBill signs every webhook with HMAC-SHA256 and your merchant `webhook_secret`. The full reference and Python/Node verification helpers live in [`WEBHOOKS.md`](./WEBHOOKS.md).

### 5.1. Required handler behavior

1. **Verify the signature before parsing.** Reject mismatches with `401`.
2. **Return `2xx` within 10 seconds.** Longer responses count as failure and trigger retries.
3. **Be idempotent.** GhostBill retries up to 7 times with exponential backoff. The same event may arrive more than once.
4. **Persist the event ID.** Use `X-GhostBill-Delivery-Id` (also sent as `X-GhostBill-Event-ID`) as a unique key. If you have already processed it, return `200` without doing the work again.
5. **Do the side effect inside a database transaction** keyed on the event ID, so partial failures don't double-credit orders.

### 5.2. Headers you receive

| Header | Meaning |
|---|---|
| `X-GhostBill-Signature` | HMAC-SHA256 hex digest |
| `X-GhostBill-Signature-Version` | currently `v2` (timestamp + delivery_id bound into the signed message) |
| `X-GhostBill-Timestamp` | ISO timestamp included in the signed payload |
| `X-GhostBill-Delivery-Id` | unique per attempt; safe as idempotency key |
| `X-GhostBill-Event-Type` | e.g. `invoice.paid` |

### 5.3. Retry behavior

Webhooks are retried up to 7 times. Successive delays are documented in `backend/app/services/webhook_payloads.py` (`RETRY_DELAYS`). After all retries fail, the delivery is moved to the dead-letter queue and can be retried manually:

```bash
# List dead letters
curl -X GET https://your-ghostbill.example/v1/webhooks/dead-letters \
  -H "Authorization: Bearer gb_live_xxx..." | jq .

# Retry one
curl -X POST https://your-ghostbill.example/v1/webhooks/dead-letters/<dlq_id>/retry \
  -H "Authorization: Bearer gb_live_xxx..."
```

Monitor the DLQ in production. A growing DLQ usually means your endpoint is rejecting valid deliveries.

---

## 6. Recipe: reconciliation

GhostBill never sees your order IDs unless you tell it. Use any of these patterns:

* **`description` field on the invoice.** Free text; e.g. `"ORDER-1001"`.
* **`metadata` JSON.** Structured, e.g. `{"order_id": "ORDER-1001"}`.
* **List invoices by date range** and match by amount + timing for emergencies.

Webhook payloads always include the GhostBill `invoice.id` and the `description` and `metadata` you set. Build your matching on `metadata.order_id` first; fall back to `description`.

For missing events: the delivery log API (`GET /v1/webhooks`) lets you list past deliveries by date range. Manual retry: `POST /v1/webhooks/{delivery_id}/retry`.

---

## 7. Handling invoice and payment states

The authoritative state machines live in `backend/app/db/models.py`. Summary:

### Invoice statuses (7)

| Status | Meaning | Fulfill order? |
|---|---|---|
| `pending` | Invoice issued, no payment yet | No |
| `partially_paid` | Some XMR received, less than `amount_atomic` | No |
| `paid` | Full amount received and confirmed | Yes |
| `overpaid` | Customer sent more than required | Yes (refund difference per your policy) |
| `late_paid` | Paid after `expires_at` | Yes (per your policy) |
| `expired` | Past `expires_at` without sufficient payment | No |
| `cancelled` | Cancelled via `POST /v1/invoices/{id}/cancel` | No |

### Payment statuses (3)

| Status | Meaning |
|---|---|
| `detected` | Transaction observed; confirmations below threshold (default 10) |
| `confirmed` | At or above confirmation threshold |
| `orphaned` | Transaction disappeared from the chain (reorg or double-spend attempt). Invoice status is recalculated. |

### Rules of thumb

* **Fulfill only on `confirmed` payments.** A `detected` payment can still be orphaned by a reorg.
* **Treat `overpaid` and `late_paid` as paid** unless your business rules say otherwise.
* **Handle `payment.orphaned` events** by reversing any provisional fulfillment.
* **`exception_payment` and `invoice.reverted` events** can fire when payments land on cancelled invoices or when an invoice's paid status is reversed by a reorg. Handle defensively.

Confirmation threshold is set by `CONFIRMATION_THRESHOLD` in your `.env` (default `10`). Adjust based on risk tolerance.

---

## 8. Operational checklist

* [ ] Webhook endpoint is HTTPS and reachable from the GhostBill host.
* [ ] Webhook handler verifies HMAC signature before parsing.
* [ ] Webhook handler is idempotent on `X-GhostBill-Delivery-Id`.
* [ ] Webhook handler returns `2xx` within 10 seconds.
* [ ] API keys live only on your server, never in client code.
* [ ] Webhook secret stored in a secrets manager (not in source).
* [ ] DLQ size monitored and alerted on.
* [ ] Orders are only fulfilled on `confirmed` payments at or after the configured threshold.
* [ ] Reconciliation job re-checks invoices once per hour against `GET /v1/invoices`.
* [ ] Refund policy and human contact path documented for `overpaid` and `late_paid` cases.
* [ ] No customer-supplied data (seed phrases, spend keys) is requested or stored.
* [ ] `wallet-rpc` is on the Docker bridge network only, never on a public interface.

---

## 9. Quick troubleshooting

Full guide will live in `docs/TROUBLESHOOTING.md`. Quick table:

| Symptom | First thing to check |
|---|---|
| `401 Unauthorized` | API key prefix (`gb_live_` vs `gb_test_`), header is `Authorization: Bearer ...` |
| `403 Forbidden` | Key belongs to a different merchant or the merchant is disabled |
| `404 Not Found` on invoice | Wrong environment (`gb_test_` key reading `live` data or vice versa) |
| Invoice stays `pending` with payment in wallet | Check `/health` `blocks_behind`; if non-zero, the node is catching up |
| Webhook not received | `webhook_url` reachable from GhostBill? TLS valid? Inspect `GET /v1/webhooks` delivery log |
| `payment.detected` but no `payment.confirmed` | Wait for confirmations; check the tx is still in the chain (could be reorg) |
| Duplicate webhook event | Normal during retries; deduplicate on `X-GhostBill-Delivery-Id` |
| `5xx` from your endpoint causes DLQ | Fix endpoint, retry from `POST /v1/webhooks/dead-letters/{id}/retry` |

---

## 10. Security and anti-scam

Only two channels are official:

* This repository: <https://github.com/gexiro-global/ghostbill>
* The website: <https://ghostbill.org>

GhostBill maintainers will **never** ask for:

* Monero seed phrases or mnemonics
* Spend keys
* Wallet files
* Production `.env`, encryption keys, or API keys
* SSH or shell access to your server
* Payments "for support" or "verification"

If anyone claiming to be a GhostBill maintainer asks for any of the above, they are impersonating the project. Close the conversation and report the account. The repository's auto-reply on new issues repeats this statement for every reporter.

For security disclosures that should not be public, follow the process in [`SECURITY.md`](./SECURITY.md) instead of opening a public issue.

---

## 11. End-to-end example

A full happy path, with placeholders. Replace every `xxx` and host before running.

```bash
# 0. One-time: register merchant (returns api_keys.live, api_keys.test, webhook_secret)
curl -X POST https://your-ghostbill.example/v1/merchants \
  -H "Content-Type: application/json" \
  -d '{
    "primary_address": "4xxx...",
    "view_key": "0123...cdef",
    "name": "My Store",
    "webhook_url": "https://merchant.example/webhooks/ghostbill"
  }' | tee merchant.json

API_KEY=$(jq -r '.api_keys.live' merchant.json)

# 1. Customer checks out order ORDER-1001 for 0.5 XMR
curl -X POST https://your-ghostbill.example/v1/invoices \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "amount_xmr": "0.5",
    "description": "ORDER-1001",
    "expires_in": 3600,
    "metadata": {"order_id": "ORDER-1001"}
  }' | tee invoice.json

INVOICE_ID=$(jq -r '.id' invoice.json)
ADDRESS=$(jq -r '.address' invoice.json)

# 2. Show ADDRESS and the requested amount to the customer.
#    Customer sends 0.5 XMR to ADDRESS from their wallet.

# 3. GhostBill POSTs to https://merchant.example/webhooks/ghostbill:
#      X-GhostBill-Event-Type: payment.detected
#      X-GhostBill-Delivery-Id: <uuid>
#      X-GhostBill-Signature: <hmac sha256>
#    Your handler:
#      - verifies HMAC, returns 202
#      - records detection but does NOT fulfill

# 4. After ~10 confirmations, GhostBill POSTs again:
#      X-GhostBill-Event-Type: payment.confirmed
#    Your handler:
#      - verifies HMAC, returns 202
#      - marks ORDER-1001 paid in your DB
#      - triggers fulfillment

# 5. Optional reconcile (fallback or audit):
curl -X GET https://your-ghostbill.example/v1/invoices/$INVOICE_ID \
  -H "Authorization: Bearer $API_KEY" | jq .
```

That's the full flow. Everything else (subscriptions, prepayments, DLQ, analytics) layers on top.

When you're ready to integrate, read [`API.md`](./API.md) for the complete endpoint catalog and [`WEBHOOKS.md`](./WEBHOOKS.md) for verification snippets in Python and Node.
