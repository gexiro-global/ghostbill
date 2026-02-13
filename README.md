# GhostBill

**Privacy-first billing for the Monero economy.**

Non-custodial. Tor-native. Open source.

GhostBill is a self-hosted Monero payment processor for merchants who need reliable, private, and automated billing. It detects payments in real-time, manages invoice lifecycles, and delivers webhook notifications — all without ever holding your funds.

---

## Why GhostBill?

**Non-Custodial** — GhostBill operates with your view key only. Your spend key never touches the server. Even a full server compromise cannot move a single piconero.

**Tor-Native** — API and dashboard accessible via `.onion` hidden services. All outgoing connections (webhooks, price feeds) routed through Tor. Your IP and your merchants' IPs are never exposed.

**Real-Time Detection** — Payments detected in the mempool within seconds (`pool: true`). No waiting for block confirmations to notify your system.

**7 Invoice States** — Handles the full lifecycle: pending, paid, expired, partially paid, overpaid, late paid, and cancelled. Each transition triggers a webhook.

**Webhook-Driven** — 8 event types with HMAC-SHA256 signatures, automatic retries (7 attempts over 38 hours), and a full delivery log with manual retry.

**Privacy by Default** — No IP logging, no analytics, no tracking. Log redaction strips sensitive data. Timing jitter prevents correlation attacks. Expired invoices auto-deleted after 48 hours.

---

## Features

| Feature | Description |
|---------|-------------|
| View-only wallet | Cannot spend funds — cryptographically impossible |
| Subaddress per invoice | Unique payment address, no address reuse |
| Mempool detection | Instant payment notification (`pool: true`) |
| 7 invoice statuses | Full lifecycle with automatic state transitions |
| 8 webhook events | HMAC-SHA256 signed, 7 retries, delivery log |
| Monero signature auth | Passwordless dashboard login via wallet signing |
| API key management | `gb_live_` / `gb_test_` keys, bcrypt hashed, max 10 per merchant |
| Rate limiting | 4 tiers, Redis sliding window, `X-RateLimit-*` headers |
| AES-256-GCM encryption | View keys encrypted at rest |
| Audit logging | 14 event types, async, non-blocking |
| Tor hidden services | `.onion` for API + dashboard |
| Outgoing Tor proxy | Webhooks and price feed via SOCKS5 |
| Security headers | CSP, HSTS, X-Frame-Options, Permissions-Policy, and more |
| Timing jitter | 50–200ms random delay on all responses |
| Data retention | Auto-cleanup: 48h expired invoices, 30d webhooks, 90d audit |
| CLI tool | Full merchant management from the command line |
| Dark mode dashboard | Invoice management, payment tracking, webhook logs |

---

## Quick Start

```bash
# Clone
git clone https://github.com/ghostbill/ghostbill.git
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
# {"status":"healthy","app":"GhostBill","version":"0.1.0"}
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full self-hosted setup guide.

---

## Architecture

```
Client → Tor Hidden Service → Backend (FastAPI :8013)
                                  ├── PostgreSQL :5445  (11 tables, 4 enums)
                                  ├── Redis :6391       (rate limits, sessions, cache)
                                  └── wallet-rpc :18083 (view-only, subaddress generation)
                                        └── monerod :31208 (pruned node, Tor p2p)

Dashboard → Tor Hidden Service → Frontend (Next.js :3013)
```

**Stack:** FastAPI + PostgreSQL + Redis + monero-wallet-rpc + Next.js 15 + Tailwind CSS

---

## API

**Base URL:** `http://127.0.0.1:8013` or `http://<onion>.onion`

**Authentication:** `Authorization: Bearer gb_live_<hex32>`

```bash
# Register merchant
curl -X POST http://127.0.0.1:8013/v1/merchants \
  -H "Content-Type: application/json" \
  -d '{"primary_address": "4...", "view_key": "a1b2..."}'

# Create invoice
curl -X POST http://127.0.0.1:8013/v1/invoices \
  -H "Authorization: Bearer gb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"amount_xmr": "0.5", "description": "VPN 1 month"}'

# Check price
curl http://127.0.0.1:8013/v1/price
```

21 endpoints total. See [docs/API.md](docs/API.md) for the full reference with request/response examples.

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
| **Webhook events** | 8, HMAC-signed, 7 retries | Basic notifications |
| **Privacy features** | No IP logging, timing jitter, log redaction | Standard logging |
| **Dashboard auth** | Monero signature (passwordless) | Email/password |
| **Setup complexity** | Docker Compose (5 containers) | Docker Compose (10+ containers) |
| **Recurring billing** | Planned (Phase 5) | Plugin-dependent |

GhostBill is purpose-built for Monero. BTCPay is an excellent Bitcoin processor with Monero support bolted on — but if XMR is your primary currency, GhostBill provides a more reliable and privacy-focused experience.

---

## Documentation

| Document | Description |
|----------|-------------|
| [API Reference](docs/API.md) | 21 endpoints, curl examples, authentication, error codes |
| [Webhooks](docs/WEBHOOKS.md) | 8 events, HMAC verification (Python/JS/curl), retry policy |
| [Security](docs/SECURITY.md) | 9-actor threat model, encryption, data retention |
| [Deployment](docs/DEPLOYMENT.md) | Self-hosted setup, monerod, wallet-rpc, Tor, backups |
| [Contributing](CONTRIBUTING.md) | How to contribute, code style, PR process |

---

## License

GhostBill is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

This means you can use, modify, and self-host GhostBill freely. If you modify it and offer it as a service, you must release your modifications under the same license.

---

## Security

Found a vulnerability? Please report it responsibly to **security@ghostbill.io**. See [docs/SECURITY.md](docs/SECURITY.md#responsible-disclosure) for our disclosure policy.

---

## Status

GhostBill is in **beta**. The core payment processing flow is tested and functional (60/60 tests passing), but it has not yet been battle-tested in high-volume production environments.

**What works:**
- Merchant registration and API key management
- Invoice creation with unique subaddresses
- Real-time payment detection (mempool + confirmed)
- Full invoice lifecycle (7 statuses, automatic transitions)
- Webhook delivery with HMAC signatures and retries
- Dashboard with Monero signature authentication
- Tor hidden services
- CLI tool

**Coming soon:**
- Recurring billing / subscriptions
- Multi-currency fiat conversion
- Plugin integrations (WooCommerce, WHMCS)
- Hosted dashboard (paid tier)
