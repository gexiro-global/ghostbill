# GhostBill Troubleshooting Guide

**Version:** v1.3-rc3
**Audience:** merchants integrating GhostBill, and operators self-hosting an instance.
**Scope:** diagnosing common issues and safely recovering. For sensitive disclosures (security bugs that should not be public) follow [`SECURITY.md`](./SECURITY.md) instead of this guide.

All examples use placeholders. Replace before running:

* API keys: `gb_live_xxx...` / `gb_test_xxx...`
* Base URL: `https://your-ghostbill.example`
* Webhook URL: `https://merchant.example/webhooks/ghostbill`
* IDs: `invoice_xxx`, `customer_xxx`, `ORDER-1001`

Never paste production secrets, wallet seeds, customer data, or full bearer tokens into issues, logs, or screenshots.

---

## Table of contents

1. [Fast triage checklist](#1-fast-triage-checklist)
2. [Health checks](#2-health-checks)
3. [API authentication problems](#3-api-authentication-problems)
4. [Invoice and payment problems](#4-invoice-and-payment-problems)
5. [Monero node and wallet-rpc problems](#5-monero-node-and-wallet-rpc-problems)
6. [Webhook delivery problems](#6-webhook-delivery-problems)
7. [Subscription problems](#7-subscription-problems)
8. [Startup, database and migration problems](#8-startup-database-and-migration-problems)
9. [Common curl recipes](#9-common-curl-recipes)
10. [Error to action table](#10-error-to-action-table)
11. [What not to share publicly](#11-what-not-to-share-publicly)
12. [Escalation checklist](#12-escalation-checklist)

---

## 1. Fast triage checklist

Before diving deep, run through this list. It eliminates the most common causes in under a minute.

1. **Is the app reachable?** `curl -s https://your-ghostbill.example/health` returns JSON with `status: "healthy"`.
2. **Is the API auth valid?** A simple authenticated `GET /v1/merchants/me` returns `200` with your merchant data.
3. **Is the Monero daemon synced?** `/health` `detection.blocks_behind` is `0` or close to it.
4. **Is wallet-rpc internal-only?** It must be reachable from the backend container but **never** from the public internet (see § 5).
5. **Are webhooks reaching your endpoint?** `GET /v1/webhooks` shows recent deliveries; non-2xx attempts mean a problem on the merchant side or wrong URL.
6. **What is the invoice status?** Read it via `GET /v1/invoices/{id}` and cross-check against § 4.
7. **Are logs safe to share?** Redact `Authorization`, `X-GhostBill-Signature`, wallet addresses, customer email, and IDs before posting anywhere.

If any check fails, jump to the matching section below.

---

## 2. Health checks

GhostBill exposes two health endpoints.

### 2.1. Public `/health`

Available without authentication.

```bash
curl -s https://your-ghostbill.example/health | jq .
```

Expected fields:

* `status` — `"healthy"` when the app started successfully.
* `app` — application name.
* `version` — e.g. `"1.3-rc3"`. Mismatch between this and the version you deployed often indicates a stale container or a missing env var.
* `detection.last_scanned_height` — last block GhostBill scanned.
* `detection.last_sweep_at` — ISO timestamp of the last detection sweep.
* `detection.blocks_behind` — difference between daemon height and last scanned. Should be `0` in steady state.

If `blocks_behind` is large and growing, see § 5.

### 2.2. Operator `/v1/admin/health`

For instance operators with the admin merchant credentials. Returns detailed status of database, Redis, wallet-rpc, background tasks, detection state, and counts of pending webhook deliveries plus unresolved DLQ entries.

```bash
curl -s https://your-ghostbill.example/v1/admin/health \
  -H "Authorization: Bearer gb_live_xxx..." | jq .
```

A non-`healthy` status in any of `database`, `redis`, or `wallet_rpc` is a strong signal where to start.

### 2.3. Docker-level checks (operator only)

If you self-host:

```bash
# All GhostBill containers and their health
docker compose ps

# Recent backend logs (last 200 lines)
docker compose logs --tail 200 backend

# Streaming wallet-rpc logs
docker compose logs -f walletrpc
```

Do not paste raw logs into public issues. Redact addresses, headers, customer data, and any tokens.

---

## 3. API authentication problems

### Symptoms

* `401 Unauthorized` with `"Invalid API key."` — the key prefix exists but the bcrypt check failed, the key is unknown, or it was rotated.
* `401 Unauthorized` with `"Missing or malformed Authorization header. Expected: Bearer <token>"` — your client didn't send the right header.
* `401 Unauthorized` with `"Merchant account is inactive."` — the merchant was disabled by the instance operator.
* `429 Too Many Requests` with `"error": "rate_limit_exceeded"` or `"merchant_rate_limit_exceeded"` — too many requests per IP or per merchant.

### Checks

* Verify header shape exactly: `Authorization: Bearer gb_live_<hex>` or `gb_test_<hex>`.
* Verify environment: a `gb_test_` key cannot read `gb_live_` data, and vice versa.
* Confirm the key wasn't deleted: `GET /v1/api-keys` lists active keys (auth with another valid key).
* For `429`: back off exponentially. Default limits live in [`.env.example`](../.env.example) under `RATE_LIMIT_*`.

### Safe test request

```bash
curl -i https://your-ghostbill.example/v1/merchants/me \
  -H "Authorization: Bearer gb_live_xxx..."
```

If this returns `200`, your auth is fine and the issue is elsewhere.

### Recovery

* If a key is leaked or lost, create a new one via `POST /v1/api-keys` and delete the compromised one via `DELETE /v1/api-keys/{id}`.
* Do not paste the leaked key into any debug message. Rotate first.

---

## 4. Invoice and payment problems

The authoritative state machines are in `backend/app/db/models.py`.

### Invoice statuses (7)

| Status | What it means | Common reason if unexpected |
|---|---|---|
| `pending` | No payment yet | Customer hasn't paid; or detection is behind (§ 5) |
| `partially_paid` | Some XMR received, less than `amount_atomic` | Customer rounded down, or sent in multiple transactions |
| `paid` | Full amount received and confirmed | — |
| `overpaid` | Customer sent more than required | Customer mistake; consider refund per your policy |
| `late_paid` | Paid after `expires_at` | Customer paid after expiry; your policy decides whether to fulfill |
| `expired` | Past `expires_at`, not fully paid | Customer abandoned, or detection delay caused late payment to land as `late_paid` instead |
| `cancelled` | Cancelled via `POST /v1/invoices/{id}/cancel` | Manual action |

### Payment statuses (3)

| Status | What it means |
|---|---|
| `detected` | Transaction observed; confirmations below threshold (default 10) |
| `confirmed` | At or above the confirmation threshold |
| `orphaned` | Transaction disappeared from the chain (reorg or replaced); invoice status is recalculated |

### Common problems

**“Invoice not found”**

* Wrong environment: a `gb_test_` key cannot read `gb_live_` invoices.
* Wrong ID: invoice IDs are UUIDs; copy/paste truncation breaks lookups.
* `GET /v1/invoices?limit=10` lists recent invoices for your merchant.

**Invoice stays `pending` even though the customer paid**

1. Check `/health` `detection.blocks_behind`. If non-zero and growing, see § 5.
2. Check the wallet address used. The customer must pay the **subaddress** returned in the invoice (`address` field), not the merchant primary address.
3. Check the amount. Payments below `DUST_THRESHOLD_ATOMIC` (default `100000000` piconero = `0.0001 XMR`) are ignored.
4. Read `GET /v1/invoices/{id}` and inspect the embedded `payments[]`. If a `detected` payment exists, just wait for confirmations.

**Customer paid, invoice is `partially_paid`**

* Customer paid less than `amount_atomic`. They may need to send the remainder to the same subaddress.
* Some wallets deduct fees from the sent amount. The customer must select “subtract fees from amount” carefully or send slightly more.

**`payment.detected` arrived but `payment.confirmed` never did**

* The transaction may still be in mempool. Wait for confirmations.
* If the transaction drops from the chain (double-spend attempt, reorg), expect a `payment.orphaned` webhook and a recalculated invoice status.
* Confirmation threshold defaults to `10` and is set by `CONFIRMATION_THRESHOLD` in `.env`.

**Invoice transitioned to `overpaid` or `late_paid`**

* These are settled statuses. Treat as paid unless your business rules say otherwise.
* For `overpaid`, the embedded `payments[]` shows the actual amount; difference is your decision (refund, credit, keep).

**Invoice reverted (`invoice.reverted`) or exception payment (`invoice.exception_payment`)**

* These webhook events fire when a previously-paid invoice's status is reversed by a chain reorg, or when a payment lands on a cancelled invoice.
* Handle defensively: if you already fulfilled the order, run your reconciliation/refund process.

---

## 5. Monero node and wallet-rpc problems

### Symptoms

* `/health` `detection.blocks_behind` is large or growing.
* `/v1/admin/health` shows `wallet_rpc` not healthy.
* New invoices generate but no `payment.detected` events arrive even after the customer pays.
* `walletrpc` container restarts in a loop.

### Wallet-rpc connection (operator)

`wallet-rpc` needs to reach `monerod` on the host. If monerod binds to `127.0.0.1`, `wallet-rpc` must share the host network namespace or otherwise reach the host's loopback. Inspect logs:

```bash
docker compose logs --tail 200 walletrpc | grep -Ei 'daemon|connect|listening|height'
```

Look for:

* `no connection to daemon` — wallet-rpc cannot reach monerod. Verify the monerod port and bind address.
* `Refresh done, blocks received` — healthy operation.
* `permits inbound unencrypted external connections` warnings without `--confirm-external-bind` — wallet-rpc refused to start.

### Wallet-rpc must be private

`wallet-rpc` must not be reachable from the public internet. Recommended posture:

* Bind to the Docker bridge gateway only, not `0.0.0.0`.
* Do not expose port `18083` (or your configured port) in `docker-compose.yml`.
* If you must use host networking, restrict the bind IP and confirm a host firewall blocks external access.

If you discover wallet-rpc was reachable externally, rotate the wallet's RPC credentials and consider rotating the merchant Monero wallet itself.

### Daemon sync

* If `blocks_behind` is large after a restart, the daemon (`monerod`) is catching up. This is normal after downtime.
* If `blocks_behind` keeps growing during steady operation, the detection loop is failing. Check backend logs for errors from the detection task.

### Confirmation threshold

Default: `10`. Set in `.env` via `CONFIRMATION_THRESHOLD`. Lower threshold means faster fulfillment but more exposure to reorgs; higher means safer but slower.

### Operator checks that do not leak secrets

Safe to run and share (redact addresses if pasting):

```bash
# Detection state
curl -s https://your-ghostbill.example/health | jq '.detection'

# Admin health (DB, Redis, wallet_rpc)
curl -s https://your-ghostbill.example/v1/admin/health \
  -H "Authorization: Bearer gb_live_xxx..." | jq '{database, redis, wallet_rpc, detection}'
```

Do **not** run wallet-rpc commands that print view keys, seeds, or full balance breakdowns and paste them into issues.

---

## 6. Webhook delivery problems

Full reference: [`WEBHOOKS.md`](./WEBHOOKS.md). Signing logic and constants live in `backend/app/services/webhook_payloads.py`.

### Symptoms

* You expected a webhook and never received it.
* Your endpoint returns `5xx` and GhostBill keeps retrying.
* You receive the same event multiple times.
* Signature verification fails on your side.

### Inspect deliveries

```bash
# Recent delivery log (cursor-paginated)
curl -s https://your-ghostbill.example/v1/webhooks \
  -H "Authorization: Bearer gb_live_xxx..." | jq .

# Single delivery detail
curl -s https://your-ghostbill.example/v1/webhooks/<delivery_id> \
  -H "Authorization: Bearer gb_live_xxx..." | jq .
```

Look for `response_status`, `attempt_count`, and `next_retry_at`.

### Webhook not received

* Verify `webhook_url` is set: `GET /v1/merchants/me` returns `webhook_url`.
* Verify your endpoint is reachable from the GhostBill host (DNS, TLS, firewall).
* Verify TLS validity. GhostBill will not deliver to endpoints with broken certificates.
* Check `GET /v1/webhooks` for the delivery and its `response_status`.

### Signature verification fails on merchant side

* Signature header: `X-GhostBill-Signature` (HMAC-SHA256 hex).
* Signature version header: `X-GhostBill-Signature-Version: v2` includes a timestamp + delivery_id binding.
* The signed payload is `<timestamp>.<delivery_id>.<raw_body_bytes>`. See [`WEBHOOKS.md`](./WEBHOOKS.md) for Python/Node verification helpers.
* Always verify against the **raw body** received — not a re-serialized JSON, which may reorder keys or change whitespace.
* Use `hmac.compare_digest` (or your language's constant-time equivalent), not `==`.
* Compare lowercase hex on both sides.

### Duplicate webhook events

Duplicates are expected during retries. Deduplicate on `X-GhostBill-Delivery-Id` (also sent as `X-GhostBill-Event-ID`). If your handler is idempotent, this is harmless.

### Retry behavior and DLQ

* Max attempts: `7`.
* Delays follow `RETRY_DELAYS` in `backend/app/services/webhook_payloads.py` (roughly 1 min → 1 day with jitter).
* Delivery timeout: `10` seconds. Endpoints that take longer count as failures.
* After all retries fail, the delivery moves to the dead-letter queue.

```bash
# List DLQ entries
curl -s https://your-ghostbill.example/v1/webhooks/dead-letters \
  -H "Authorization: Bearer gb_live_xxx..." | jq .

# Retry a DLQ entry once you have fixed the merchant endpoint
curl -s -X POST https://your-ghostbill.example/v1/webhooks/dead-letters/<dlq_id>/retry \
  -H "Authorization: Bearer gb_live_xxx..."
```

A growing DLQ usually means your endpoint is rejecting valid deliveries. Fix the endpoint first, then retry from the DLQ.

### Endpoint returns non-2xx

GhostBill expects a `2xx` response within 10 seconds. Any other response is treated as failure.

* Return `2xx` as soon as you have **persisted** the event ID. Do the actual work asynchronously.
* Do not block the response on slow downstream systems.

---

## 7. Subscription problems

### Symptoms

* Subscription does not generate renewal invoices.
* Subscription stays in `past_due` even after payment.
* Webhook event for subscription not received.

### Checks

* `GET /v1/subscriptions/{id}` shows current `status`, `next_due_at`, and `grace_days_*`.
* `GET /v1/subscriptions/{id}/renewal-log` shows renewal events for this subscription.
* Subscription must reference an existing customer. Create one via `POST /v1/customers` if missing.

### Lifecycle

| Status | Meaning |
|---|---|
| `active` | Normal renewal cadence |
| `past_due` | Invoice unpaid past `grace_days_soft` |
| `expired` | Unpaid past `grace_days_hard` |
| `paused` | Manually paused via `POST /v1/subscriptions/{id}/pause` |
| `cancelled` | Manually cancelled via `POST /v1/subscriptions/{id}/cancel` (terminal) |

### Common problems

**Subscription is `past_due` after payment**

* The renewal invoice may be `partially_paid` or `late_paid` rather than `paid`. Inspect the linked invoice in the renewal log.
* Subscription recovery requires a fully settled invoice (`paid`, `overpaid`, or `late_paid` depending on policy).

**Subscription does not transition to `expired`**

* Background task that processes renewals may be lagging. Operator can check `/v1/admin/health` `background_tasks` field.

**Webhook events for subscription missing**

* See § 6. Same delivery log applies to all event types.

---

## 8. Startup, database and migration problems

### Symptoms

* `docker compose up -d` finishes but `backend` is unhealthy.
* Backend logs show `Application startup failed`.
* Database errors on first request.

### Migrations

GhostBill uses Alembic. Migrations are applied automatically by the CI compose, and should be applied manually on production deploys.

```bash
# Check current migration head inside the backend container
docker exec ghostbill_backend alembic current

# Apply pending migrations (operator only, after backup)
docker exec ghostbill_backend alembic upgrade head
```

Always back up the database before running migrations on a production instance.

### Database unavailable

* `docker compose ps` should show `postgres` healthy.
* `docker compose logs postgres` reveals startup or auth errors.
* Verify `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` in `.env` match what Postgres was initialized with. Changing these after the volume is created does not re-create the user.

### Redis unavailable

* `docker compose ps` should show `redis` healthy.
* If you added or changed `REDIS_PASSWORD`, make sure `REDIS_URL` in `.env` includes the password: `redis://:<password>@<host>:<port>/0`.
* Backend logs showing `Authentication required` from Redis usually mean a stale `.env` without password.

### Startup errors with `model_validator`

Production startup requires `SECRET_KEY` and `MASTER_ENCRYPTION_KEY` set. If you see `Production requires SECRET_KEY and MASTER_ENCRYPTION_KEY` on startup, set both in `.env` (generate with `openssl rand -hex 32`).

### Stale `.env.test` after upgrade

`scripts/ci-test.sh` only creates `.env.test` if missing. After upgrading GhostBill, if Redis auth was added or env keys changed, delete the old `.env.test` so the script regenerates it from `.env.test.example`.

---

## 9. Common curl recipes

Placeholders only. Replace before running.

```bash
# Public health
curl -s https://your-ghostbill.example/health | jq .

# Detailed admin health
curl -s https://your-ghostbill.example/v1/admin/health \
  -H "Authorization: Bearer gb_live_xxx..." | jq .

# Current merchant
curl -s https://your-ghostbill.example/v1/merchants/me \
  -H "Authorization: Bearer gb_live_xxx..." | jq .

# Read invoice
curl -s https://your-ghostbill.example/v1/invoices/<invoice_id> \
  -H "Authorization: Bearer gb_live_xxx..." | jq .

# Recent invoices
curl -s 'https://your-ghostbill.example/v1/invoices?limit=10' \
  -H "Authorization: Bearer gb_live_xxx..." | jq .

# Webhook delivery log
curl -s 'https://your-ghostbill.example/v1/webhooks?limit=20' \
  -H "Authorization: Bearer gb_live_xxx..." | jq .

# DLQ
curl -s https://your-ghostbill.example/v1/webhooks/dead-letters \
  -H "Authorization: Bearer gb_live_xxx..." | jq .

# Retry DLQ entry
curl -s -X POST https://your-ghostbill.example/v1/webhooks/dead-letters/<dlq_id>/retry \
  -H "Authorization: Bearer gb_live_xxx..."
```

---

## 10. Error to action table

| Symptom | Likely cause | Safe check | Recovery |
|---|---|---|---|
| `401 Invalid API key.` | Wrong/rotated key, wrong environment | `GET /v1/merchants/me` with the key | Use the correct env key or create a new one |
| `401 Missing or malformed Authorization header` | Wrong header shape | Verify `Authorization: Bearer ...` | Fix client header |
| `401 Merchant account is inactive.` | Operator disabled the merchant | Contact instance operator | Reactivate via admin panel/API |
| `429 rate_limit_exceeded` / `merchant_rate_limit_exceeded` | Too many requests | Back off | Exponential backoff, batch where possible |
| `404` on invoice/customer/subscription | Wrong env, wrong ID | List recent items via the corresponding list endpoint | Use correct ID and environment |
| `5xx` from GhostBill | Backend/DB/Redis problem | `/health` and `/v1/admin/health` | Operator: inspect logs of failing container |
| Invoice stuck `pending` with payment in wallet | Detection lag or wrong address | `/health` `blocks_behind`; inspect `address` of invoice | Wait for detection; verify customer paid the subaddress |
| `payment.detected` but no `payment.confirmed` | Awaiting confirmations or tx reorged | Inspect `payments[]` in invoice detail | Wait; handle `payment.orphaned` if it arrives |
| Webhook never arrives | Bad URL, TLS, firewall, or merchant 5xx | `GET /v1/webhooks` for delivery log | Fix endpoint, retry from DLQ |
| Webhook signature mismatch | Re-serialized body, wrong header parsing | Reproduce against raw body | Use raw body and `compare_digest`; see [`WEBHOOKS.md`](./WEBHOOKS.md) |
| Duplicate webhook events | Normal retries | Check `X-GhostBill-Delivery-Id` | Deduplicate by delivery ID |
| Backend won't start | Missing env, migrations pending | `docker compose logs backend` | Set required env vars; back up DB; run `alembic upgrade head` |
| Redis `Authentication required` in logs | Password set in compose, missing in `REDIS_URL` | Inspect `.env` | Update `REDIS_URL` with password |

---

## 11. What not to share publicly

Never paste any of the following into issues, chat rooms, screenshots, or commit history:

* Monero seed phrases or mnemonics
* Spend keys (private keys)
* Wallet files or wallet backups
* Full `.env` contents
* `SECRET_KEY` or `MASTER_ENCRYPTION_KEY`
* API keys (`gb_live_...` or `gb_test_...`)
* Webhook signing secrets
* Raw production logs containing `Authorization`, `X-GhostBill-Signature`, addresses, or customer data
* Customer PII (emails, addresses)
* Screenshots showing admin panels, secrets, or session tokens

GhostBill maintainers will **never** ask you for any of these. See § 12 and [`SECURITY.md`](./SECURITY.md) for the right channel.

---

## 12. Escalation checklist

Before opening a GitHub issue, gather:

* GhostBill version (`/health` `version`).
* Deployment method (Docker Compose, Tor hidden service, clearnet reverse proxy).
* Sanitized error message or excerpt.
* Endpoint path only (e.g. `POST /v1/invoices`), not the full URL with query strings that could contain tokens.
* Invoice/customer/subscription ID **prefix only** or a placeholder.
* Webhook `X-GhostBill-Delivery-Id` if the issue is about delivery.
* `/health` `blocks_behind` value if the issue is about detection.
* Redacted log excerpts.

File the issue at <https://github.com/gexiro-global/ghostbill/issues>. Every new issue receives an automated reply with the project's official statement and anti-scam reminder.

For security issues that must not be public, follow [`SECURITY.md`](./SECURITY.md) instead.
