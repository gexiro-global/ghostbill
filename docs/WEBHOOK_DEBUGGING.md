# GhostBill Webhook Debugging Guide

**Applies to:** v1.3-rc3.
**Audience:** merchants and backend integrators implementing or debugging webhook receivers; operators diagnosing delivery problems.
**Scope:** delivery lifecycle, signature verification, idempotency, retries, dead-letter queue, and event-specific handling.

For the canonical event catalogue and field schemas, see [`WEBHOOKS.md`](./WEBHOOKS.md). For end-to-end integration recipes, see [`MERCHANT_COOKBOOK.md`](./MERCHANT_COOKBOOK.md). For runtime triage, see [`TROUBLESHOOTING.md`](./TROUBLESHOOTING.md).

All examples use placeholders. Replace before running:

* Webhook secret: `whsec_xxx` or `webhook_secret_xxx`
* API key: `gb_live_xxx` or `gb_test_xxx`
* Base URL: `https://your-ghostbill.example`
* Merchant endpoint: `https://merchant.example/webhooks/ghostbill`
* IDs: `invoice_xxx`, `customer_xxx`, `delivery_xxx`, `evt_xxx`, `ORDER-1001`

Never paste production secrets, full bodies, or `X-GhostBill-Signature` values into issues, screenshots, or chat logs.

---

## Table of contents

1. [Webhook model overview](#1-webhook-model-overview)
2. [Headers and signature contract](#2-headers-and-signature-contract)
3. [Golden rule: verify against raw body](#3-golden-rule-verify-against-raw-body)
4. [Signature verification examples](#4-signature-verification-examples)
5. [Receiver skeletons](#5-receiver-skeletons)
6. [Idempotency handling](#6-idempotency-handling)
7. [Delivery failures and retries](#7-delivery-failures-and-retries)
8. [Debugging signature failures](#8-debugging-signature-failures)
9. [Debugging missing webhooks](#9-debugging-missing-webhooks)
10. [Debugging duplicate webhooks](#10-debugging-duplicate-webhooks)
11. [Event-specific debugging](#11-event-specific-debugging)
12. [Curl recipes](#12-curl-recipes)
13. [Safe logging and redaction](#13-safe-logging-and-redaction)
14. [Issue checklist](#14-issue-checklist)

---

## 1. Webhook model overview

GhostBill posts JSON to your `webhook_url` for every event your merchant has subscribed to. Source of truth: `backend/app/services/webhook_payloads.py` and `backend/app/services/webhook_service.py`.

**Constants (v1.3-rc3):**

| Constant | Value | Source |
|---|---|---|
| `MAX_ATTEMPTS` | `7` | `webhook_payloads.py` |
| `DELIVERY_TIMEOUT` | `10.0` seconds | `webhook_payloads.py` |
| `RETRY_DELAYS` | `[60, 300, 1800, 7200, 43200, 86400]` seconds | `webhook_payloads.py` |
| Success criteria | HTTP `2xx` (`200`–`299`) | `webhook_service.py` |
| Content-Type | `application/json` | `webhook_service.py` |
| User-Agent | `GhostBill-Webhook/1.0` | `webhook_service.py` |

**Event registry (22 events in v1.3-rc3):**

* `payment.detected`, `payment.confirmed`, `payment.orphaned`
* `invoice.paid`, `invoice.expired`, `invoice.partially_paid`, `invoice.overpaid`, `invoice.late_paid`, `invoice.exception_payment`, `invoice.reverted`
* `subscription.created`, `subscription.renewed`, `subscription.past_due`, `subscription.cancelled`, `subscription.payment_confirmed`, `subscription.updated`, `subscription.paused`, `subscription.resumed`, `subscription.expired`, `subscription.trial_started`, `subscription.trial_ended`, `subscription.prepaid`

The full payload shape for each event lives in [`WEBHOOKS.md`](./WEBHOOKS.md).

**Delivery lifecycle:**

1. Event fires in backend (invoice paid, subscription renewed, ...).
2. GhostBill builds a payload and queues a delivery record (`webhook_deliveries` table).
3. Background worker POSTs the payload to `webhook_url`.
4. If the merchant returns `2xx`, the delivery is marked successful.
5. If non-`2xx` or timeout, the delivery is rescheduled per `RETRY_DELAYS`.
6. After `MAX_ATTEMPTS` failures, the delivery moves to the DLQ (`webhook_dead_letters`).
7. Operator can replay from DLQ via `POST /v1/webhooks/dead-letters/{dlq_id}/retry`.

The delivery log is queryable: `GET /v1/webhooks` (cursor-paginated). Single delivery detail: `GET /v1/webhooks/{delivery_id}`. Manual retry of a non-DLQ delivery: `POST /v1/webhooks/{delivery_id}/retry`.

---

## 2. Headers and signature contract

Every delivery includes these headers (exact names as sent):

| Header | Description |
|---|---|
| `X-GhostBill-Signature` | Hex-lowercase HMAC-SHA256 digest of the signed message |
| `X-GhostBill-Signature-Version` | Currently `v2` (timestamp + delivery_id bound into signed message) |
| `X-GhostBill-Timestamp` | ISO 8601 UTC timestamp included in the signed message |
| `X-GhostBill-Delivery-Id` | Per-attempt unique ID; use as idempotency key |
| `X-GhostBill-Event-ID` | Alias of `X-GhostBill-Delivery-Id` for consumers that prefer this name |
| `X-GhostBill-Event-Type` | Event name (e.g. `invoice.paid`) |
| `Content-Type` | `application/json` |
| `User-Agent` | `GhostBill-Webhook/1.0` |

**Exact signature algorithm (v2):**

```
signed_message = utf8(timestamp) + b"." + utf8(delivery_id) + b"." + raw_body_bytes
signature      = hmac_sha256_hex(secret, signed_message).lower()
```

Note the **two literal dots** separating timestamp, delivery_id, and the raw body. No whitespace.

**Legacy v1 acceptance (operator note):** the server-side `verify_signature` helper also accepts a signature computed without the timestamp/delivery_id prefix. New merchants must implement v2. Do not rely on v1 — it is kept only for backward-compatible verification of older test fixtures.

**No automatic freshness window:** the timestamp is bound into the signed message (so attackers cannot reuse a captured signature against a different timestamp), but the server does not enforce a maximum age on inbound timestamps when re-verifying. If you want replay protection on your side, reject deliveries whose `X-GhostBill-Timestamp` is older than your chosen window (e.g. 5 minutes).

---

## 3. Golden rule: verify against raw body

**Always verify against the raw request body bytes you received over the wire.** Never against a re-serialized JSON object.

Why this matters: GhostBill serializes the payload with `json.dumps(..., separators=(",", ":"), sort_keys=True)` — compact, sorted keys, no whitespace. If your framework parses JSON first and you then re-encode it with default options, key order and whitespace change, and the HMAC will not match. The fix is never “match GhostBill's serializer”; it is “verify against the bytes you received”.

Framework checklist:

* **Express (Node.js):** mount `express.raw({ type: "application/json" })` on the webhook route. Do **not** mount `express.json()` ahead of it.
* **FastAPI / Starlette (Python):** call `await request.body()` to get the raw bytes. Do not use `await request.json()` for verification.
* **Flask (Python):** use `request.get_data()` (or `request.get_data(cache=True)` if you need to re-read it). Do not use `request.get_json()` for verification.
* **PHP:** read `file_get_contents("php://input")` once, store it, then verify and parse from the same bytes.
* **Serverless platforms:** check the platform's body-handling docs. Some platforms transform or base64-encode the body before delivering it to your handler. Decode to the original raw bytes before HMAC.

If the verifier reports failures only on payloads with certain characters (Unicode, large integers, nested objects), this is almost always a body-mutation problem in the proxy or framework.

---

## 4. Signature verification examples

All examples assume:

* You have stored your merchant `webhook_secret` somewhere safe (env var, secrets manager).
* Your handler receives the raw request body bytes.
* Your framework gives you access to the relevant headers.

### 4.1. Python

```python
import hmac
import hashlib
import os
from datetime import datetime, timezone, timedelta

WEBHOOK_SECRET = os.environ["GHOSTBILL_WEBHOOK_SECRET"]  # whsec_xxx in your secrets manager
MAX_TIMESTAMP_AGE_SECONDS = 300  # your own replay window


def verify_ghostbill_signature(
    raw_body: bytes,
    signature_header: str,
    timestamp_header: str,
    delivery_id_header: str,
    secret: str = WEBHOOK_SECRET,
) -> bool:
    if not signature_header or not timestamp_header or not delivery_id_header:
        return False

    # Optional replay protection: reject stale timestamps.
    try:
        ts = datetime.fromisoformat(timestamp_header)
    except ValueError:
        return False
    if datetime.now(timezone.utc) - ts > timedelta(seconds=MAX_TIMESTAMP_AGE_SECONDS):
        return False

    signed_message = (
        f"{timestamp_header}.{delivery_id_header}.".encode("utf-8") + raw_body
    )
    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=signed_message,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected.lower(), signature_header.lower())
```

### 4.2. Node.js

```javascript
const crypto = require("crypto");

const WEBHOOK_SECRET = process.env.GHOSTBILL_WEBHOOK_SECRET;
const MAX_TIMESTAMP_AGE_MS = 5 * 60 * 1000;

function verifyGhostbillSignature(rawBody, signatureHeader, timestampHeader, deliveryIdHeader) {
  if (!signatureHeader || !timestampHeader || !deliveryIdHeader) return false;

  const ts = Date.parse(timestampHeader);
  if (Number.isNaN(ts)) return false;
  if (Date.now() - ts > MAX_TIMESTAMP_AGE_MS) return false;

  const prefix = Buffer.from(`${timestampHeader}.${deliveryIdHeader}.`, "utf8");
  const signedMessage = Buffer.concat([prefix, rawBody]);

  const expected = crypto
    .createHmac("sha256", WEBHOOK_SECRET)
    .update(signedMessage)
    .digest("hex");

  const a = Buffer.from(expected.toLowerCase(), "utf8");
  const b = Buffer.from(signatureHeader.toLowerCase(), "utf8");
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}
```

### 4.3. PHP

```php
<?php
function verify_ghostbill_signature(
    string $rawBody,
    string $signatureHeader,
    string $timestampHeader,
    string $deliveryIdHeader,
    string $secret
): bool {
    if ($signatureHeader === "" || $timestampHeader === "" || $deliveryIdHeader === "") {
        return false;
    }

    $ts = strtotime($timestampHeader);
    if ($ts === false) {
        return false;
    }
    if ((time() - $ts) > 300) {
        return false;
    }

    $signedMessage = $timestampHeader . "." . $deliveryIdHeader . "." . $rawBody;
    $expected = hash_hmac("sha256", $signedMessage, $secret);

    return hash_equals(strtolower($expected), strtolower($signatureHeader));
}
```

### 4.4. Quick OpenSSL check (operator debugging)

Useful when you have a stored body and want to confirm the signature locally:

```bash
SECRET='whsec_xxx'
TS='2026-05-24T17:00:00+00:00'
DID='delivery_xxx'
# Body must be the EXACT bytes received
BODY="$(cat /tmp/saved_body.bin)"
printf '%s.%s.%s' "$TS" "$DID" "$BODY" \
  | openssl dgst -sha256 -hmac "$SECRET" -hex \
  | awk '{print $NF}'
```

Compare with the `X-GhostBill-Signature` value you stored. Use this only for offline debugging — never paste real secrets or bodies into shared logs.

---

## 5. Receiver skeletons

Deliberately minimal. Pick your stack, harden as your platform requires, deploy as you see fit. None of these examples bind to a specific host or port — use your normal deployment runner.

### 5.1. Python — FastAPI

```python
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse

app = FastAPI()


@app.post("/webhooks/ghostbill")
async def ghostbill_webhook(request: Request):
    raw_body = await request.body()
    sig = request.headers.get("X-GhostBill-Signature", "")
    ts = request.headers.get("X-GhostBill-Timestamp", "")
    did = request.headers.get("X-GhostBill-Delivery-Id", "")
    event_type = request.headers.get("X-GhostBill-Event-Type", "")

    if not verify_ghostbill_signature(raw_body, sig, ts, did):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    # Idempotency: store delivery ID before processing.
    if already_processed(did):
        return JSONResponse({"status": "already_processed"}, status_code=200)

    record_delivery(did, event_type)
    enqueue_event_for_processing(did, event_type, raw_body)

    return JSONResponse({"status": "accepted"}, status_code=202)
```

### 5.2. Node.js — Express

```javascript
const express = require("express");
const app = express();

// IMPORTANT: raw body on the webhook route only.
app.post(
  "/webhooks/ghostbill",
  express.raw({ type: "application/json" }),
  (req, res) => {
    const sig = req.header("X-GhostBill-Signature") || "";
    const ts = req.header("X-GhostBill-Timestamp") || "";
    const did = req.header("X-GhostBill-Delivery-Id") || "";
    const eventType = req.header("X-GhostBill-Event-Type") || "";

    if (!verifyGhostbillSignature(req.body, sig, ts, did)) {
      return res.status(401).json({ error: "invalid signature" });
    }

    if (alreadyProcessed(did)) {
      return res.status(200).json({ status: "already_processed" });
    }

    recordDelivery(did, eventType);
    enqueueEventForProcessing(did, eventType, req.body);

    return res.status(202).json({ status: "accepted" });
  }
);
```

### 5.3. PHP

```php
<?php
$rawBody = file_get_contents("php://input");
$headers = getallheaders();
$sig     = $headers["X-GhostBill-Signature"]    ?? "";
$ts      = $headers["X-GhostBill-Timestamp"]    ?? "";
$did     = $headers["X-GhostBill-Delivery-Id"]  ?? "";
$event   = $headers["X-GhostBill-Event-Type"]   ?? "";

if (!verify_ghostbill_signature($rawBody, $sig, $ts, $did, $secret)) {
    http_response_code(401);
    echo json_encode(["error" => "invalid signature"]);
    exit;
}

if (already_processed($did)) {
    http_response_code(200);
    echo json_encode(["status" => "already_processed"]);
    exit;
}

record_delivery($did, $event);
enqueue_event_for_processing($did, $event, $rawBody);

http_response_code(202);
echo json_encode(["status" => "accepted"]);
```

**Never log:** the secret, the raw body, the signature header value, or any wallet/customer fields. Log only the event type, delivery ID, and sanitized status (see § 13).

---

## 6. Idempotency handling

Webhooks may arrive more than once. Causes include retries after timeouts, operator restarts, and manual DLQ replays. **Idempotency is required, not optional.**

**Recommended pattern:**

1. On receipt, verify the signature.
2. Look up `X-GhostBill-Delivery-Id` in your `processed_webhooks` table.
3. If present — return `200` immediately, do nothing else.
4. If absent — begin a transaction:
   * Insert `(delivery_id, received_at)` into `processed_webhooks` with a unique constraint.
   * Apply the business effect (mark order paid, etc).
   * Commit.
5. On commit success, return `202`.
6. On commit failure, do not return `2xx` — let GhostBill retry.

The unique constraint on `delivery_id` is what guarantees safety even under concurrent retries. If two workers race, exactly one wins the insert; the other sees a unique-violation and treats it as “already processed”.

Do **not** key idempotency on the invoice ID alone. Multiple events can fire against the same invoice (`payment.detected`, `payment.confirmed`, `invoice.paid`). Each is a distinct delivery.

---

## 7. Delivery failures and retries

**What GhostBill considers a failure:**

* Any HTTP response outside `200`–`299`.
* Connection error.
* TLS error.
* Timeout after `10` seconds.

**Retry schedule (from `webhook_payloads.py`):**

| Attempt | Delay before next try |
|---|---|
| 1 | 60 s |
| 2 | 5 min |
| 3 | 30 min |
| 4 | 2 h |
| 5 | 12 h |
| 6 | 24 h |
| 7 | DLQ |

Max attempts: `7`. After the seventh failure the delivery moves to the DLQ. Operator can replay manually.

**Inspect deliveries:**

```bash
curl -s 'https://your-ghostbill.example/v1/webhooks?limit=20' \
  -H "Authorization: Bearer gb_live_xxx" | jq .

curl -s https://your-ghostbill.example/v1/webhooks/delivery_xxx \
  -H "Authorization: Bearer gb_live_xxx" | jq .
```

**Manually retry a single (non-DLQ) delivery:**

```bash
curl -s -X POST https://your-ghostbill.example/v1/webhooks/delivery_xxx/retry \
  -H "Authorization: Bearer gb_live_xxx"
```

**Replay from DLQ:**

```bash
curl -s https://your-ghostbill.example/v1/webhooks/dead-letters \
  -H "Authorization: Bearer gb_live_xxx" | jq .

curl -s -X POST https://your-ghostbill.example/v1/webhooks/dead-letters/dlq_xxx/retry \
  -H "Authorization: Bearer gb_live_xxx"
```

A growing DLQ usually means your endpoint is rejecting valid deliveries. Fix the endpoint first, then drain.

---

## 8. Debugging signature failures

| Symptom | Likely cause | Check | Fix |
|---|---|---|---|
| Always fails | Wrong secret | Compare your stored secret with `GET /v1/merchants/me` `webhook_secret` after a fresh `POST /v1/merchants/me/webhook-secret` | Update secret in your secrets manager |
| Always fails | Verifying re-serialized JSON instead of raw body | Print bytes you hash; should equal bytes received | Switch to raw body (see § 3) |
| Fails on Unicode-heavy payloads | Framework re-encodes body | Compare `len(raw_body)` with `Content-Length` header | Read body directly, not via JSON parser |
| Fails after upgrade | Wrong signature version assumed | Inspect `X-GhostBill-Signature-Version` header | Implement v2 (timestamp + delivery_id prefix) |
| Intermittent failures | Mixing test and live secrets | Compare environment of the API key vs. the secret in use | Use the secret matching the deployment |
| Fails behind a CDN/WAF | Body modified in transit | Bypass CDN for the webhook path, replay a known delivery | Disable body inspection on the webhook route |
| Hex comparison fails despite same value | Case sensitivity | Lowercase both sides | Use `compare_digest`/`timingSafeEqual` on lowercased hex |
| Old delivery rejected after restart | Your timestamp window too tight | Inspect `X-GhostBill-Timestamp` age | Widen window or process within the window |

---

## 9. Debugging missing webhooks

| Symptom | Likely cause | Check |
|---|---|---|
| No deliveries at all | `webhook_url` not set | `GET /v1/merchants/me` |
| Delivery log shows attempts, none reach you | DNS, TLS, or firewall | Resolve and `curl` your endpoint from the GhostBill host network |
| `404`/`405` recorded on deliveries | Wrong endpoint path/method | Confirm route accepts `POST` |
| `3xx` redirects | Endpoint returns a redirect | GhostBill does not follow redirects — return `2xx` directly |
| Endpoint reachable from browser but not from GhostBill | WAF/proxy/IP allowlist | Allowlist the GhostBill host or relax WAF on `/webhooks/ghostbill` |
| Deliveries always show `5xx` | Your handler crashes after returning headers | Verify before any DB/IO work; return early on signature failure |
| You receive nothing but `GET /v1/webhooks` is empty | Event class not subscribed (if filtering is configured) or event never fired | Confirm the underlying invoice/subscription transitioned states |

Also: confirm your TLS certificate is valid. GhostBill will not deliver to endpoints with expired or self-signed certificates unless your platform is explicitly configured to allow them.

---

## 10. Debugging duplicate webhooks

Duplicates are normal during retries and after operator restarts. Causes:

* You returned `2xx` after the 10-second timeout: GhostBill recorded a timeout, retried, your second attempt processed and returned `2xx`.
* You returned non-`2xx` even though you processed the event: GhostBill retried, second attempt is a duplicate.
* Operator replayed from DLQ for a delivery you had already processed by another path.
* You restarted between persisting the side effect and persisting the idempotency key.

**Recovery:** implement idempotency per § 6. Keying on `X-GhostBill-Delivery-Id` is exactly correct — every retry attempt sends the **same** delivery ID, so deduplication is safe.

**Do not** key on event type plus invoice ID: an invoice can legitimately receive `payment.detected` and later `payment.confirmed` for the same payment.

---

## 11. Event-specific debugging

This section assumes you have read § 6 (idempotency). The most common merchant integration bugs are concentrated in a small set of events.

### Payment events

* **`payment.detected`** — transaction observed, not yet confirmed. **Do not fulfill on this event.** Use it to update UI ("payment received, awaiting confirmations").
* **`payment.confirmed`** — transaction reached confirmation threshold (default `10`). Safe to fulfill. Check the invoice status separately if you need the rolled-up `paid` decision.
* **`payment.orphaned`** — the transaction left the chain (reorg or replaced). If you had provisionally fulfilled, reverse it; the invoice status will be recalculated server-side.

### Invoice events

* **`invoice.paid`** — invoice fully paid and at least one payment confirmed. Most merchants drive fulfillment off this rather than `payment.confirmed`.
* **`invoice.partially_paid`** — some XMR received, less than the required amount. Do not fulfill; surface a status to the customer.
* **`invoice.overpaid`** — customer sent more than required. Settled. Refund policy is your decision.
* **`invoice.late_paid`** — fully paid after `expires_at`. Settled. Acceptance is your decision.
* **`invoice.expired`** — not fully paid before `expires_at`. If you provisionally fulfilled, reverse.
* **`invoice.exception_payment`** — a payment landed on a cancelled invoice. Handle defensively (refund flow).
* **`invoice.reverted`** — a previously paid invoice's status was reversed (e.g. reorg). Reverse any fulfillment.

### Subscription events

* **`subscription.created`** / **`subscription.renewed`** — lifecycle markers. Use the linked invoice ID to drive billing.
* **`subscription.payment_confirmed`** — the renewal invoice was settled. Trigger granting/extending access.
* **`subscription.past_due`** — unpaid past `grace_days_soft`. Notify the customer; do **not** cancel access yet.
* **`subscription.expired`** — unpaid past `grace_days_hard`. Terminal for this period; revoke access.
* **`subscription.paused`** / **`subscription.resumed`** — manual lifecycle actions.
* **`subscription.cancelled`** — terminal cancellation.
* **`subscription.updated`** — pending change applied (e.g. amount).
* **`subscription.trial_started`** / **`subscription.trial_ended`** — trial markers.
* **`subscription.prepaid`** — customer paid forward multiple periods.

**Avoid:** treating `subscription.past_due` as a cancellation. It is a warning state and recoverable. Cancellation is `subscription.cancelled` or `subscription.expired`.

---

## 12. Curl recipes

```bash
# Recent deliveries
curl -s 'https://your-ghostbill.example/v1/webhooks?limit=20' \
  -H "Authorization: Bearer gb_live_xxx" | jq .

# Single delivery detail
curl -s https://your-ghostbill.example/v1/webhooks/delivery_xxx \
  -H "Authorization: Bearer gb_live_xxx" | jq .

# Manually retry a non-DLQ delivery
curl -s -X POST https://your-ghostbill.example/v1/webhooks/delivery_xxx/retry \
  -H "Authorization: Bearer gb_live_xxx"

# Dead-letter queue
curl -s https://your-ghostbill.example/v1/webhooks/dead-letters \
  -H "Authorization: Bearer gb_live_xxx" | jq .

# Replay a DLQ entry
curl -s -X POST https://your-ghostbill.example/v1/webhooks/dead-letters/dlq_xxx/retry \
  -H "Authorization: Bearer gb_live_xxx"

# Look up the invoice after a webhook to confirm state
curl -s https://your-ghostbill.example/v1/invoices/invoice_xxx \
  -H "Authorization: Bearer gb_live_xxx" | jq .

# Look up the subscription after a lifecycle event
curl -s https://your-ghostbill.example/v1/subscriptions/sub_xxx \
  -H "Authorization: Bearer gb_live_xxx" | jq .

# Rotate the webhook secret (will invalidate the current one immediately)
curl -s -X POST https://your-ghostbill.example/v1/merchants/me/webhook-secret \
  -H "Authorization: Bearer gb_live_xxx" | jq .
```

---

## 13. Safe logging and redaction

Never log:

* `webhook_secret`
* API keys (`gb_live_xxx`, `gb_test_xxx`)
* Full `Authorization` headers
* Full `X-GhostBill-Signature` values
* Raw request bodies in production
* Customer email, wallet addresses, or other PII
* `.env` contents or any GhostBill master keys
* Wallet files or seed phrases

Do log (these are safe and useful):

* `X-GhostBill-Event-Type`
* `X-GhostBill-Delivery-Id` (and/or `X-GhostBill-Event-ID`)
* `X-GhostBill-Timestamp`
* Invoice ID prefix (e.g. first 8 chars) for trace correlation
* HTTP status returned to GhostBill
* `attempt_count` from the delivery log if you fetch it
* Sanitized error class/message (no payload echo)

If you must log the body for debugging, do it only in a dev/staging environment, with the body bytes stored encrypted at rest and rotated out within hours. Never share that storage.

---

## 14. Issue checklist

Before opening an issue at <https://github.com/gexiro-global/ghostbill/issues>, gather:

* GhostBill version (`/health` `version`).
* Event type and the timestamp range you expect to debug.
* `X-GhostBill-Delivery-Id` (delivery IDs are safe to share).
* Endpoint path only (e.g. `POST /webhooks/ghostbill`), not the full URL with secrets.
* HTTP status your handler returned to GhostBill.
* A sanitized excerpt of the error you logged.
* Whether your verifier uses the raw body.
* Whether you implement idempotency on the delivery ID.
* Output of `GET /v1/webhooks/{delivery_id}` if relevant (it does not include the secret).

The repository's automated reply to every new issue includes the project's anti-scam reminder. Maintainers will never ask you for your `webhook_secret`, API keys, `.env`, wallet files, or seed phrases.

For security issues that must not be public, follow [`SECURITY.md`](./SECURITY.md) instead.
