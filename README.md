# GhostBill

**Self-hostable Monero payment processor with recurring billing.**

Non-custodial. Privacy-first. Open source.

GhostBill is a self-hosted Monero payment processor for merchants who need reliable, private, and automated billing — including recurring subscriptions. It detects payments in real time, manages invoice lifecycles, handles subscription renewals with grace periods, and delivers webhook notifications — all without ever holding your funds.

> **Status:** Audited release candidate (`v1.3-rc1`). Core payment processing and subscription lifecycle are tested across 5 security audit waves (82/99 findings closed). CI verifies clean install, migrations, lint/format, and the service-level release gate. Not yet battle-tested in high-volume production environments.

---

## Quick Start (Test / CI)

Verify GhostBill builds and passes tests from a clean checkout:

```bash
git clone https://github.com/gexiro-global/ghostbill.git
cd ghostbill
cp .env.test.example .env.test
./scripts/ci-test.sh
```

This builds containers from scratch, runs `alembic upgrade head` on a fresh PostgreSQL, checks lint/format, and executes the service-level test suite. No wallet-rpc, no Tor, no production secrets required.

For self-hosted production deployment, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## Why GhostBill?

**Non-custodial** — Operates with your view key only. Your spend key never touches the server. Even a full server compromise cannot move funds.

**Privacy-first** — No IP logging, no analytics, no tracking. Log redaction strips sensitive data. Timing jitter on responses. Tor hidden services supported for API and dashboard.

**Real-time detection** — Payments detected in the mempool within seconds. Confirmed-only settlement (10 confirmations) prevents double-spend risk.

**Full subscription lifecycle** — Recurring billing with configurable intervals, soft/hard grace periods, trial periods, pre-payment with discounts, and pending changes applied at next renewal.

**Webhook delivery** — 22 event types, HMAC-SHA256 signed, 7 automatic retries over 38 hours, Dead Letter Queue for failed deliveries.

---

## Features

| Feature | Description |
|---------|-------------|
| View-only wallet | Server holds view keys only; spend keys remain outside the server |
| Subaddress per invoice | Unique payment address, no address reuse |
| Confirmed-only settlement | 10-confirmation threshold before marking paid |
| Reorg protection | Automatic reversal if confirmed payment is orphaned |
| 7 invoice statuses | pending, paid, expired, partially_paid, overpaid, late_paid, cancelled |
| 6 subscription statuses | active, paused, past_due, cancelled, expired, trialing |
| 22 webhook events | HMAC-SHA256 signed, 7 retries, Dead Letter Queue |
| Trial periods | 1–365 days, auto-activate on expiry |
| Pre-payment | 1–36 periods upfront with configurable discounts |
| Cursor pagination | Stripe-compatible (`starting_after`, `ending_before`, `has_more`) |
| Monero signature auth | Passwordless dashboard login via wallet signing |
| API key management | `gb_live_` / `gb_test_` keys, bcrypt hashed |
| Rate limiting | IP-based sliding window + per-merchant limits |
| AES-256-GCM encryption | View keys encrypted at rest |
| Audit logging | Async, non-blocking |
| SSE real-time | Server-Sent Events on payment pages |
| Admin panel | Instance operator dashboard with health monitoring |

---

## Architecture

```
Client → Backend (FastAPI)
             ├── PostgreSQL  (14 tables, 4 enums, 15 migrations)
             ├── Redis       (rate limits, sessions, analytics cache)
             └── wallet-rpc  (view-only, subaddress generation)
                   └── monerod

Dashboard → Frontend (Next.js 15)
```

**Stack:** FastAPI + PostgreSQL + Redis + monero-wallet-rpc + Next.js 15 + Tailwind CSS

**Docker Compose:** 4 service containers (postgres, redis, backend, walletrpc) + optional frontend.

---

## API

53 endpoints across 14 route modules. Authentication via `Authorization: Bearer gb_live_<hex>`.

| Resource | Endpoints | Description |
|----------|-----------|-------------|
| Merchants | 4 | Register, profile, webhook secret |
| Invoices | 4 | Create, list, get, cancel |
| Payments | 2 | List, get |
| Customers | 4 | Create, list, get, update |
| Subscriptions | 9 | Full lifecycle, prepay, pending changes |
| Webhooks | 5 | Deliveries, retry, DLQ |
| API Keys | 3 | List, create, revoke |
| Analytics | 3 | Revenue, invoice stats, subscription metrics |
| Auth | 3 | Nonce, verify (Monero signature), logout |
| Licenses | 4 | Admin CRUD, public verify |
| Price | 1 | Current XMR rate |
| Public | 3 | Public invoice view, SSE, payment page |
| Admin | 8 | Operator dashboard, health, DLQ management |

See [docs/API.md](docs/API.md) for the full reference with curl examples.

---

## Webhook Events

22 event types covering the full payment and subscription lifecycle:

- **Payment (3):** `payment.detected`, `payment.confirmed`, `payment.orphaned`
- **Invoice (7):** `invoice.paid`, `invoice.expired`, `invoice.partially_paid`, `invoice.overpaid`, `invoice.late_paid`, `invoice.exception_payment`, `invoice.reverted`
- **Subscription (12):** `subscription.created`, `subscription.renewed`, `subscription.past_due`, `subscription.cancelled`, `subscription.payment_confirmed`, `subscription.updated`, `subscription.paused`, `subscription.resumed`, `subscription.expired`, `subscription.trial_started`, `subscription.trial_ended`, `subscription.prepaid`

All webhooks are signed with HMAC-SHA256 (`X-GhostBill-Signature` header) and retried up to 7 times with exponential backoff. Failed deliveries move to the Dead Letter Queue.

See [docs/WEBHOOKS.md](docs/WEBHOOKS.md) for verification examples and payload formats.

---

## Security Model

- View-only wallet architecture — spend key never on server
- AES-256-GCM encryption for view keys at rest
- bcrypt-hashed API keys with timing-safe comparison
- HMAC-SHA256 webhook signatures with replay protection
- Redis distributed leases on all background task loops
- Confirmed-only settlement (10-confirmation threshold)
- Automatic reorg reversal for orphaned payments
- Rate limiting, CORS, security headers, log redaction
- 5-wave security audit: 82 of 99 findings closed

See [docs/SECURITY.md](docs/SECURITY.md) for the full threat model.

---

## Testing

CI verifies clean install, migrations, lint/format, and the service-level test suite:

```bash
# Local CI (mirrors GitHub Actions)
./scripts/ci-test.sh

# Run tests manually inside backend container
docker compose exec backend python3 -m pytest tests/wave5 -v --tb=short
```

The Wave 5 test suite includes 59 service-level tests covering payment processing, reorg handling, idempotency, concurrency, webhook dispatch, subscription lifecycle, authorization, analytics, and test isolation. Tests call production service methods (e.g. `PaymentService.process_transfer()`) against a real database — not mocked.

---

## Documentation

| Document | Description |
|----------|-------------|
| [API Reference](docs/API.md) | 53 endpoints, curl examples, authentication, error codes |
| [Webhooks](docs/WEBHOOKS.md) | 22 events, HMAC verification, retry policy, DLQ |
| [Security Model](docs/SECURITY.md) | Threat model, encryption, data retention |
| [Deployment](docs/DEPLOYMENT.md) | Self-hosted setup: monerod, wallet-rpc, Tor, backups |
| [Clearnet Setup](docs/clearnet-setup.md) | Optional clearnet guide with nginx, SSL, Cloudflare |
| [Changelog](CHANGELOG.md) | Version history and audit wave details |

---

## License

GhostBill is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

You can use, modify, and self-host GhostBill freely. If you modify it and offer it as a service, you must release your modifications under the same license.

---

## Security

Found a vulnerability? Please report it responsibly to **security@ghostbill.org**. Do not open a public issue for security vulnerabilities.

See [SECURITY.md](SECURITY.md) for our disclosure policy.

---

## Roadmap

- [ ] Python SDK (`pip install ghostbill`)
- [ ] Plugin integrations (WooCommerce, WHMCS)
- [ ] Expanded CI coverage (wave1–4 tests)

---

**Built by [Gexiro Enterprises Ltd](https://gexiro.com), Gibraltar.**
