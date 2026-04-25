# GhostBill Webhooks

GhostBill sends real-time webhook notifications to your server when payment, invoice, and subscription events occur. All deliveries are signed with HMAC-SHA256 for verification.

---

## Table of Contents

- [Overview](#overview)
- [Webhook Events](#webhook-events)
  - [Payment Events](#payment-events)
  - [Invoice Events](#invoice-events)
  - [Subscription Events](#subscription-events)
- [Delivery Format](#delivery-format)
- [Signature Verification](#signature-verification)
  - [Python](#python)
  - [JavaScript (Node.js)](#javascript-nodejs)
  - [curl (testing)](#curl-testing)
- [Retry Policy](#retry-policy)
- [Dead Letter Queue](#dead-letter-queue)
- [Delivery Log API](#delivery-log-api)
- [Best Practices](#best-practices)

---

## Overview

When you register a merchant, GhostBill generates a `webhook_secret` and delivers events to your `webhook_url`. Every delivery is signed so you can verify it came from GhostBill and wasn't tampered with.

**Setup requirements:**
1. Set a `webhook_url` during registration or via `PATCH /v1/merchants/me`
2. Store your `webhook_secret` securely — it's shown once at registration
3. Your endpoint must return HTTP `2xx` within **10 seconds** to acknowledge delivery
4. If you lose your secret, regenerate it via `POST /v1/merchants/me/webhook-secret`

---

## Webhook Events

GhostBill dispatches **20 event types** across three categories:

### Payment Events

| Event | Trigger | Description |
|-------|---------|-------------|
| `payment.detected` | Transaction seen in mempool | A new payment was found on the invoice's subaddress. The transaction is unconfirmed — do not fulfill the order yet. |
| `payment.confirmed` | Transaction reached ≥ 10 confirmations | The payment is confirmed on the blockchain. Safe to fulfill the order. |
| `payment.orphaned` | Transaction disappeared from chain | The transaction was dropped (double-spend attempt or blockchain reorg). The invoice status is recalculated. |

### Invoice Events

| Event | Trigger | Description |
|-------|---------|-------------|
| `invoice.paid` | Total confirmed ≥ required amount | The invoice is fully paid. This is the primary event to trigger order fulfillment. |
| `invoice.expired` | Expiry time reached, no confirmed payment | The invoice expired without receiving sufficient payment. |
| `invoice.partially_paid` | Confirmed amount < required amount | A payment was confirmed but the total is less than the invoice amount. Customer may need to send the remaining balance. |
| `invoice.overpaid` | Confirmed amount > required amount | The customer sent more than required. You should arrange a refund for the excess. |
| `invoice.late_paid` | Payment confirmed after invoice expired | A payment arrived and was confirmed after the invoice already expired. |

### Subscription Events

| Event | Trigger | Description |
|-------|---------|-------------|
| `subscription.created` | New subscription created | A new subscription was created for a customer. If trial_days is set, the subscription starts in `trialing` status. |
| `subscription.renewed` | Renewal invoice created | A new billing period has started and a renewal invoice was generated. |
| `subscription.past_due` | Renewal invoice unpaid past soft grace | The renewal invoice was not paid within the soft grace period. The subscription is now past due. |
| `subscription.cancelled` | Merchant cancelled the subscription | The subscription was cancelled. No further renewals will be generated. |
| `subscription.payment_confirmed` | Renewal payment confirmed | A payment for a subscription renewal invoice was confirmed on-chain. |
| `subscription.updated` | Pending changes queued | The merchant updated the subscription (amount, interval, or grace periods). Changes will be applied at the next renewal. |
| `subscription.paused` | Merchant paused the subscription | The subscription was paused. No renewals will be generated until resumed. |
| `subscription.resumed` | Merchant resumed the subscription | The subscription was resumed from paused state. Next renewal is scheduled. |
| `subscription.expired` | Hard grace period exceeded | The subscription expired because the renewal invoice was not paid within the hard grace period. |
| `subscription.trial_started` | Trial period began | A subscription with trial_days was created. The trial period is active — no invoices are generated until it ends. |
| `subscription.trial_ended` | Trial period ended | The trial period has ended. The subscription transitions to `active` and the first billing invoice is created. |
| `subscription.prepaid` | Pre-payment invoice created | A pre-payment invoice was generated for multiple billing periods with an optional discount. |

**Event flow for a typical successful payment:**

```
payment.detected  →  payment.confirmed  →  invoice.paid
```

**Event flow for subscription lifecycle:**

```
subscription.created  →  subscription.renewed  →  subscription.payment_confirmed
                                                →  subscription.past_due  →  subscription.expired
```

**Event flow for trial subscription:**

```
subscription.created  →  subscription.trial_started
→  subscription.trial_ended  →  subscription.renewed  →  subscription.payment_confirmed
```

**Event flow for pre-payment:**

```
subscription.prepaid  →  payment.detected  →  payment.confirmed  →  invoice.paid
```

---

## Delivery Format

Each webhook delivery is an HTTP POST to your `webhook_url` with the following structure:

### Headers

| Header | Description | Example |
|--------|-------------|--------|
| `Content-Type` | Always `application/json` | `application/json` |
| `X-GhostBill-Signature` | HMAC-SHA256 hex digest of the request body | `a1b2c3d4e5f6...` |
| `X-GhostBill-Event` | Event type | `payment.confirmed` |
| `X-GhostBill-Event-ID` | Unique delivery ID (UUID) | `evt_a1b2c3d4-...` |
| `X-GhostBill-Timestamp` | Unix timestamp of delivery | `1707739500` |

### Payment/Invoice Payload

```json
{
  "event": "payment.confirmed",
  "event_id": "evt_a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "invoice_id": "inv-uuid-here",
  "payment_id": "pay-uuid-here",
  "amount_atomic": 500000000000,
  "amount_xmr": "0.500000000000",
  "total_received_atomic": 500000000000,
  "confirmations": 10,
  "tx_hash": "7d8e9f0a1b2c...",
  "invoice_status": "paid",
  "timestamp": "2026-02-13T04:35:00Z"
}
```

### Payment/Invoice Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `event` | string | Event type (one of the 20 events) |
| `event_id` | string | Unique identifier for this delivery |
| `invoice_id` | string (UUID) | Invoice this event relates to |
| `payment_id` | string (UUID) or null | Payment that triggered this event (null for invoice-only events) |
| `amount_atomic` | integer | Payment amount in piconero (0 for invoice-only events) |
| `amount_xmr` | string | Payment amount as human-readable XMR string |
| `total_received_atomic` | integer | Total confirmed amount received for this invoice |
| `confirmations` | integer | Current confirmation count for the payment |
| `tx_hash` | string or null | Monero transaction hash |
| `invoice_status` | string | Current invoice status after this event |
| `timestamp` | string (ISO 8601) | When the event occurred |

### Subscription Payload

```json
{
  "event": "subscription.renewed",
  "event_id": "evt_b2c3d4e5-6789-01ab-cdef-234567890abc",
  "subscription_id": "sub-uuid-here",
  "customer_id": "cust-uuid-here",
  "invoice_id": "inv-uuid-here",
  "amount_atomic": 100000000000,
  "amount_xmr": "0.100000000000",
  "interval_days": 30,
  "status": "active",
  "next_due_at": "2026-04-13T00:00:00Z",
  "timestamp": "2026-03-13T00:00:00Z"
}
```

### Subscription Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `event` | string | Event type (subscription.* event) |
| `event_id` | string | Unique identifier for this delivery |
| `subscription_id` | string (UUID) | Subscription this event relates to |
| `customer_id` | string (UUID) | Customer who owns this subscription |
| `invoice_id` | string (UUID) or null | Related invoice (for renewed, prepaid events) |
| `amount_atomic` | integer | Subscription amount in piconero |
| `amount_xmr` | string | Subscription amount as human-readable XMR string |
| `interval_days` | integer | Billing interval in days |
| `status` | string | Current subscription status after this event |
| `next_due_at` | string (ISO 8601) or null | Next renewal date |
| `trial_days` | integer or null | Trial period length (for trial events) |
| `trial_end_at` | string (ISO 8601) or null | Trial end date (for trial events) |
| `timestamp` | string (ISO 8601) | When the event occurred |

---

## Signature Verification

Every webhook delivery is signed using **HMAC-SHA256** with your `webhook_secret`. The signature is computed over the **raw request body** (the JSON payload as a byte string).

**Signature header:** `X-GhostBill-Signature`

> ⚠️ **Always verify the signature before processing any webhook.** This prevents replay attacks and ensures the payload wasn't tampered with.

### Python

```python
import hmac
import hashlib
from flask import request  # or any framework

WEBHOOK_SECRET = "whsec_your_secret_here"

@app.route("/webhooks/ghostbill", methods=["POST"])
def handle_webhook():
    # Get raw body bytes — do NOT parse JSON first
    payload = request.get_data()
    received_signature = request.headers.get("X-GhostBill-Signature", "")

    # Compute expected signature
    expected = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Constant-time comparison (prevents timing attacks)
    if not hmac.compare_digest(expected, received_signature):
        return "Invalid signature", 401

    # Signature valid — process the event
    event = request.get_json()
    event_type = event["event"]

    if event_type == "invoice.paid":
        fulfill_order(event["invoice_id"])
    elif event_type == "payment.detected":
        show_pending_status(event["invoice_id"])
    elif event_type == "payment.orphaned":
        revert_pending_status(event["invoice_id"])
    elif event_type == "subscription.renewed":
        log_renewal(event["subscription_id"], event["invoice_id"])
    elif event_type == "subscription.expired":
        deactivate_service(event["subscription_id"])
    elif event_type == "subscription.trial_ended":
        start_billing(event["subscription_id"])

    return "OK", 200
```

### JavaScript (Node.js)

```javascript
const crypto = require("crypto");
const express = require("express");
const app = express();

const WEBHOOK_SECRET = "whsec_your_secret_here";

// IMPORTANT: use raw body, not parsed JSON
app.post("/webhooks/ghostbill", express.raw({ type: "application/json" }), (req, res) => {
    const payload = req.body; // Buffer (raw bytes)
    const receivedSignature = req.headers["x-ghostbill-signature"] || "";

    // Compute expected signature
    const expected = crypto
        .createHmac("sha256", WEBHOOK_SECRET)
        .update(payload)
        .digest("hex");

    // Constant-time comparison (prevents timing attacks)
    const isValid = crypto.timingSafeEqual(
        Buffer.from(expected, "utf-8"),
        Buffer.from(receivedSignature, "utf-8")
    );

    if (!isValid) {
        return res.status(401).send("Invalid signature");
    }

    // Signature valid — process the event
    const event = JSON.parse(payload);

    switch (event.event) {
        case "invoice.paid":
            fulfillOrder(event.invoice_id);
            break;
        case "payment.detected":
            showPendingStatus(event.invoice_id);
            break;
        case "subscription.renewed":
            logRenewal(event.subscription_id, event.invoice_id);
            break;
        case "subscription.expired":
            deactivateService(event.subscription_id);
            break;
        case "subscription.trial_ended":
            startBilling(event.subscription_id);
            break;
    }

    res.status(200).send("OK");
});
```

### curl (testing)

Verify a webhook signature manually with curl and openssl:

```bash
# Your webhook secret
SECRET="whsec_your_secret_here"

# The raw JSON payload (exact bytes as received)
PAYLOAD='{"event":"payment.confirmed","event_id":"evt_abc123","invoice_id":"inv-uuid","payment_id":"pay-uuid","amount_atomic":500000000000,"amount_xmr":"0.500000000000","total_received_atomic":500000000000,"confirmations":10,"tx_hash":"7d8e...","invoice_status":"paid","timestamp":"2026-02-13T04:35:00Z"}'

# Compute HMAC-SHA256
echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET"

# Compare the output with the X-GhostBill-Signature header value
```

To simulate sending a webhook to your endpoint:

```bash
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -X POST http://localhost:4000/webhooks/ghostbill \
  -H "Content-Type: application/json" \
  -H "X-GhostBill-Signature: $SIGNATURE" \
  -H "X-GhostBill-Event: payment.confirmed" \
  -H "X-GhostBill-Event-ID: evt_test123" \
  -H "X-GhostBill-Timestamp: $(date +%s)" \
  -d "$PAYLOAD"
```

---

## Retry Policy

If your endpoint doesn't return HTTP `2xx` within 10 seconds, GhostBill retries with exponential backoff:

| Attempt | Delay after failure | Cumulative time |
|---------|-------------------|-----------------|
| 1 | Immediate | 0 |
| 2 | 1 minute | 1 min |
| 3 | 5 minutes | 6 min |
| 4 | 30 minutes | 36 min |
| 5 | 2 hours | ~2.5 hours |
| 6 | 12 hours | ~14.5 hours |
| 7 | 24 hours | ~38.5 hours |

After **7 failed attempts**, the delivery is moved to the Dead Letter Queue (DLQ) with status `dead_lettered`.

**Timeout:** 10 seconds per delivery attempt.

**Jitter:** A random delay of 50–200ms is added to each delivery for metadata protection.

**Tor routing:** All outgoing webhook deliveries are routed through Tor SOCKS5 proxy, so your endpoint's IP is never exposed to GhostBill's server.

---

## Dead Letter Queue

When a webhook delivery exhausts all 7 retry attempts, it is moved to the Dead Letter Queue (DLQ). DLQ entries preserve the original payload and error information for debugging.

### List DLQ entries

```bash
curl http://127.0.0.1:8013/v1/webhooks/dead-letters \
  -H "Authorization: Bearer gb_live_..."

# Filter by resolved status
curl "http://127.0.0.1:8013/v1/webhooks/dead-letters?resolved=false" \
  -H "Authorization: Bearer gb_live_..."
```

### Retry a DLQ entry

```bash
curl -X POST http://127.0.0.1:8013/v1/webhooks/dead-letters/{dlq_id}/retry \
  -H "Authorization: Bearer gb_live_..."
```

Retrying a DLQ entry creates a new webhook delivery with the original payload and resets the retry counter.

### DLQ fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | DLQ entry ID |
| `delivery_id` | string (UUID) | Original webhook delivery ID |
| `event_type` | string | Original event type |
| `payload` | object | Original webhook payload |
| `original_created_at` | string (ISO 8601) | When the original delivery was created |
| `dead_lettered_at` | string (ISO 8601) | When the delivery was moved to DLQ |
| `last_error` | string or null | Last error message from the final retry attempt |
| `retry_count` | integer | Number of manual retries from DLQ |
| `resolved` | boolean | Whether this entry has been resolved |

---

## Delivery Log API

You can inspect and manage webhook deliveries via the API. See the [API Reference](API.md) for full details.

### List deliveries

```bash
# All deliveries (cursor pagination)
curl http://127.0.0.1:8013/v1/webhooks \
  -H "Authorization: Bearer gb_live_..."

# Filter by status
curl "http://127.0.0.1:8013/v1/webhooks?status=failed&limit=10" \
  -H "Authorization: Bearer gb_live_..."

# Filter by invoice
curl "http://127.0.0.1:8013/v1/webhooks?invoice_id=a1b2c3d4-..." \
  -H "Authorization: Bearer gb_live_..."
```

All list endpoints use cursor-based pagination with `starting_after`, `ending_before`, and `has_more`.

### Get delivery details

```bash
curl http://127.0.0.1:8013/v1/webhooks/{delivery_id} \
  -H "Authorization: Bearer gb_live_..."
```

Returns full payload, response code, response body, attempt count, and next retry time.

### Manually retry a failed delivery

```bash
curl -X POST http://127.0.0.1:8013/v1/webhooks/{delivery_id}/retry \
  -H "Authorization: Bearer gb_live_..."
```

Resets the attempt counter and schedules immediate re-delivery. Only deliveries with `status=failed` can be retried.

### Webhook delivery statuses

| Status | Description |
|--------|-------------|
| `pending` | Delivery queued or awaiting retry |
| `delivered` | Endpoint returned HTTP `2xx` |
| `failed` | Delivery failed but retries not yet exhausted |
| `dead_lettered` | All 7 retry attempts exhausted, moved to DLQ |

---

## Best Practices

**1. Always verify signatures.** Never trust a webhook payload without checking the `X-GhostBill-Signature` header using constant-time comparison.

**2. Use the raw body for verification.** Parse JSON only after verifying the signature. If your framework automatically parses the body, make sure to also capture the raw bytes for HMAC computation.

**3. Respond quickly.** Return `200 OK` immediately, then process the event asynchronously. If your handler takes longer than 10 seconds, GhostBill will consider it a failure and retry.

**4. Handle duplicates.** Due to retries, your endpoint may receive the same event more than once. Use the `event_id` field to deduplicate — store processed event IDs and skip duplicates.

**5. Don't rely solely on `payment.detected`.** The `detected` status means the transaction is in the mempool but not yet confirmed. Wait for `payment.confirmed` or `invoice.paid` before fulfilling orders. A detected payment can become `orphaned`.

**6. Monitor the Dead Letter Queue.** Check the DLQ regularly via the dashboard or API (`GET /v1/webhooks/dead-letters`). Failed deliveries often indicate endpoint issues — fix the root cause, then retry from DLQ.

**7. Handle subscription events.** For recurring billing, implement handlers for the key subscription events: `subscription.renewed` (new billing period), `subscription.payment_confirmed` (payment received), `subscription.past_due` (payment overdue), and `subscription.expired` (service should be deactivated).

**8. Rotate secrets periodically.** Use `POST /v1/merchants/me/webhook-secret` to regenerate your webhook secret. Update your verification code immediately after rotation — the old secret is invalidated instantly.

**9. Use HTTPS (or .onion).** Always use HTTPS for your webhook endpoint to protect the payload in transit. Alternatively, use a Tor hidden service (`.onion`) endpoint for maximum privacy.

**10. Log everything.** Keep your own log of received webhooks for debugging and reconciliation. The `X-GhostBill-Event-ID` and `X-GhostBill-Timestamp` headers are useful for correlation.

**11. Test with the delivery log.** Use `GET /v1/webhooks` to inspect what GhostBill sent, including the full payload and your endpoint's response code and body.
