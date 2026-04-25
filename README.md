# GhostBill

**Privacy-first billing for the Monero economy.**

Non-custodial. Tor-native. Open source.

GhostBill is a self-hosted Monero payment processor for merchants who need reliable, private, and automated billing — including recurring subscriptions. It detects payments in real-time, manages invoice lifecycles, handles subscription renewals with grace periods, and delivers webhook notifications — all without ever holding your funds.

---

## Why GhostBill?

**Non-Custodial** — GhostBill operates with your view key only. Your spend key never touches the server. Even a full server compromise cannot move a single piconero.

**Tor-Native** — API and dashboard accessible via `.onion` hidden services. All outgoing connections (webhooks, price feeds) routed through Tor. Your IP and your merchants' IPs are never exposed.

**Real-Time Detection** — Payments detected in the mempool within seconds (`pool: true`). No waiting for block confirmations to notify your system.

**Full Subscription Lifecycle** — Recurring billing with configurable intervals, grace periods, trial periods (1–365 days), pre-payment with discounts, and pending changes applied at next renewal.

**20 Webhook Events** — HMAC-SHA256 signed, 7 automatic retries over 38 hours, Dead Letter Queue for failed deliveries, and manual retry via API.

**Privacy by Default** — No IP logging, no analytics, no tracking. Log redaction strips sensitive data. Timing jitter prevents correlation attacks. Expired invoices auto-deleted after 48 hours.

---

## Features

| Feature | Description |
|---------|-------------|
| View-only wallet | Cannot spend funds — cryptographically impossible |
| Subaddress per invoice | Unique payment address, no address reuse |
| Mempool detection | Instant payment notification (`pool: true`) |
| 7 invoice statuses | pending, paid, expired, partially_paid, overpaid, late_paid, cancelled |
| 6 subscription statuses | active, paused, past_due, cancelled, expired, trialing |
| 20 webhook events | HMAC-SHA256 signed, 7 retries, Dead Letter Queue |
| Trial periods | 1–365 days, auto-activate to first invoice on expiry |
| Pre-payment | Pay 1–36 periods upfront with configurable merchant discounts |
| Pending changes | Update subscription amount/interval, applied at next renewal |
| Billing anchor | Deterministic renewal dates, no drift over time |
| Analytics dashboard | Revenue charts, invoice stats, subscription metrics (Redis-cached) |
| SSE real-time | Server-Sent Events on payment pages with polling fallback |
| Cursor pagination | Stripe-compatible (`starting_after`, `ending_before`, `has_more`) on all list endpoints |
| Monero signature auth | Passwordless dashboard login via wallet signing |
| API key management | `gb_live_` / `gb_test_` keys, bcrypt hashed, max 10 per merchant |
| Rate limiting | IP-based sliding window + per-merchant limits (120 write, 300 read per minute) |
| AES-256-GCM encryption | View keys encrypted at rest |
| Audit logging | 14 event types, async, non-blocking |
| Tor hidden services | `.onion` for API + dashboard |
| Outgoing Tor proxy | Webhooks and price feed via SOCKS5 |
| Security headers | CSP, HSTS, X-Frame-Options, Permissions-Policy |
| Timing jitter | 50–200ms random delay on all responses |
| Data retention | Auto-cleanup: 48h expired invoices, 30d webhooks, 90d audit |
| Admin panel | Instance operator dashboard with health monitoring, DLQ management, merchant toggle |
| Dark mode dashboard | Invoice management, payment tracking, subscription control, webhook logs |

---

## Quick Start

```bash
# Clone
git clone https://github.com/nicknull/ghostbill.git
cd ghostbill

# Configure
cp .env.example .env
# Generate secrets on server: openssl rand -hex 32
# Edit .env with your values

# Start
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d

# Verify
curl http://127.0.0.1:8013/health
# {"status":"healthy","app":"GhostBill","version":"0.1.0","detection":{...}}
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full self-hosted setup guide.

---

## Architecture

```
Client → Tor Hidden Service → Backend (FastAPI :8013)
                                  ├── PostgreSQL :5445  (14 tables, 4 enums)
                                  ├── Redis :6391       (rate limits, sessions, analytics cache)
                                  └── wallet-rpc :18083 (view-only, subaddress generation)
                                        └── monerod      (pruned node, Tor p2p)

Dashboard → Tor Hidden Service → Frontend (Next.js :3013)

Landing → Cloudflare → ghostbill.org (Vite + React SPA, 8 languages)
```

**Stack:** FastAPI + PostgreSQL + Redis + monero-wallet-rpc + Next.js 15 + Tailwind CSS

**Docker Compose:** 5 containers — postgres, redis, backend, frontend, walletrpc. All ports bound to `127.0.0.1`.

---

## API

**Base URL:** `http://127.0.0.1:8013` or `http://<onion>.onion`

**Authentication:** `Authorization: Bearer gb_live_<hex32>`

**51 endpoints** across 13 route modules:

| Resource | Endpoints | Description |
|----------|-----------|-------------|
| Merchants | 4 | Register, get/update profile, regenerate webhook secret |
| Invoices | 4 | Create, list, get, cancel |
| Payments | 2 | List, get |
| Customers | 4 | Create, list, get, update |
| Subscriptions | 9 | Create, list, get, update (pending changes), pause, resume, cancel, prepay, renewal log |
| Webhooks | 5 | List deliveries, get detail, retry, Dead Letter Queue list, DLQ retry |
| API Keys | 3 | List, create, revoke |
| Analytics | 3 | Revenue over time, invoice status breakdown, subscription metrics |
| Auth | 3 | Nonce, verify (Monero signature), logout |
| Price | 1 | Current XMR/USD/EUR rate |
| Public | 3 | Public invoice view, SSE real-time events, payment page (HTML) |
| Admin | 8 | Operator dashboard: stats, health, merchants, toggle, DLQ, trigger renewal |
| Internal | 2 | Health check, trigger renewal sweep |

```bash
# Create invoice
curl -X POST http://127.0.0.1:8013/v1/invoices \
  -H "Authorization: Bearer gb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"amount_xmr": "0.5", "description": "VPN 1 month"}'

# Create subscription with 14-day trial
curl -X POST http://127.0.0.1:8013/v1/subscriptions \
  -H "Authorization: Bearer gb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "...", "amount_xmr": "0.1", "interval_days": 30, "trial_days": 14}'

# Check price
curl http://127.0.0.1:8013/v1/price
```

All list endpoints use cursor-based pagination (Stripe-compatible: `starting_after`, `ending_before`, `has_more`).

See [docs/API.md](docs/API.md) for the full reference.

---

## Webhook Events

20 event types covering the full payment and subscription lifecycle:

**Payment events (3):** `payment.detected`, `payment.confirmed`, `payment.orphaned`

**Invoice events (5):** `invoice.paid`, `invoice.expired`, `invoice.partially_paid`, `invoice.overpaid`, `invoice.late_paid`

**Subscription events (12):** `subscription.created`, `subscription.renewed`, `subscription.past_due`, `subscription.cancelled`, `subscription.payment_confirmed`, `subscription.updated`, `subscription.paused`, `subscription.resumed`, `subscription.expired`, `subscription.trial_started`, `subscription.trial_ended`, `subscription.prepaid`

All webhooks are signed with HMAC-SHA256 (`X-GhostBill-Signature` header) and retried up to 7 times over 38 hours with exponential backoff. Failed deliveries move to the Dead Letter Queue for manual inspection and retry.

See [docs/WEBHOOKS.md](docs/WEBHOOKS.md) for verification examples and payload formats.

---

## Clearnet Deployment

GhostBill is Tor-native by default. For merchants who choose clearnet access, we provide Docker Compose override files and an nginx reverse proxy configuration.

```bash
docker compose -f docker-compose.yml -f docker-compose.clearnet.yml up -d
```

See [docs/clearnet-setup.md](docs/clearnet-setup.md) for the full guide including SSL, Cloudflare integration, and security hardening.

> **Note:** The decision to expose your GhostBill instance on clearnet is yours. Our reference deployment runs 100% over Tor.

---

## GhostBill vs BTCPay Server

| | GhostBill | BTCPay Server |
|---|-----------|---------------|
| **Primary currency** | Monero (native) | Bitcoin (Monero = plugin) |
| **Monero reliability** | Built for XMR from day one | Community plugin, sync issues reported |
| **Custodial model** | View-only (non-custodial) | View-only (non-custodial) |
| **Tor integration** | Native `.onion`, outgoing Tor proxy | Optional, manual setup |
| **Mempool detection** | Yes (`pool: true`) | Varies by plugin |
| **Invoice states** | 7 (including late_paid, overpaid) | 3–4 |
| **Subscription states** | 6 (with trials + pre-payment) | Plugin-dependent |
| **Webhook events** | 20, HMAC-signed, 7 retries + DLQ | Basic notifications |
| **Privacy features** | No IP logging, timing jitter, log redaction | Standard logging |
| **Dashboard auth** | Monero signature (passwordless) | Email/password |
| **Setup complexity** | Docker Compose (5 containers) | Docker Compose (10+ containers) |
| **Recurring billing** | Built-in (trials, prepay, grace periods) | Plugin-dependent |

GhostBill is purpose-built for Monero. BTCPay is an excellent Bitcoin processor with Monero support bolted on — but if XMR is your primary currency, GhostBill provides a more reliable and privacy-focused experience.

---

## Documentation

| Document | Description |
|----------|-------------|
| [API Reference](docs/API.md) | 51 endpoints, curl examples, authentication, error codes |
| [Webhooks](docs/WEBHOOKS.md) | 20 events, HMAC verification (Python/JS/curl), retry policy, DLQ |
| [Security](docs/SECURITY.md) | 9-actor threat model, encryption, data retention |
| [Deployment](docs/DEPLOYMENT.md) | Self-hosted setup, monerod, wallet-rpc, Tor, backups |
| [Clearnet Setup](docs/clearnet-setup.md) | Optional clearnet guide with nginx, SSL, Cloudflare |
| [Contributing](CONTRIBUTING.md) | How to contribute, code style, PR process |

---

## Database

14 tables across 4 enums:

**Core:** merchants, invoices, invoice_addresses, payments, customers

**Subscriptions:** subscriptions, subscription_payments, subscription_renewal_events

**Infrastructure:** wallet_shards, api_keys, webhook_deliveries, webhook_dead_letters, audit_log

**Migration system:** alembic_version (8 migrations, linear chain)

---

## Testing

```bash
cd /root/ghostbill
python3 -m pytest tests/ -v --tb=short
```

111 tests across 7 test files covering: end-to-end payment flow, subscription state machine, stress testing, analytics/SSE/trials/prepay (Phase 7–8), and coverage gap tests for webhooks, DLQ, admin, auth, and public invoice endpoints.

**Code quality:** Ruff linting + formatting enforced via pre-commit hook on every commit.

---

## License

GhostBill is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

This means you can use, modify, and self-host GhostBill freely. If you modify it and offer it as a service, you must release your modifications under the same license.

---

## Security

Found a vulnerability? Please report it responsibly to **contact@ghostbill.org**. See [docs/SECURITY.md](docs/SECURITY.md#responsible-disclosure) for our disclosure policy.

---

## Status

GhostBill is in **beta** (`v1.1-beta`). The core payment processing and subscription lifecycle are tested and functional (111/111 tests passing), but it has not yet been battle-tested in high-volume production environments.

**What works:**
- Merchant registration and API key management
- Invoice creation with unique subaddresses
- Real-time payment detection (mempool + confirmed)
- Full invoice lifecycle (7 statuses, automatic transitions)
- Recurring subscriptions with grace periods and billing anchors
- Trial periods (1–365 days) with auto-activation
- Pre-payment (1–36 periods) with configurable discounts
- Webhook delivery with HMAC signatures, retries, and Dead Letter Queue
- Dashboard with Monero signature authentication
- Analytics dashboard with revenue charts
- SSE real-time updates on payment pages
- Admin panel for instance operators
- Tor hidden services
- Cursor-based pagination on all list endpoints

**Coming soon:**
- Python SDK (`pip install ghostbill`)
- CI/CD pipeline with structured logging
- Plugin integrations (WooCommerce, WHMCS)

---

**Built by [Gexiro Enterprises Ltd](https://gexiro.com), Gibraltar.**
