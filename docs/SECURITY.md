# GhostBill Security

GhostBill is designed with a **privacy-first, non-custodial** architecture. This document describes the threat model, cryptographic protections, data handling policies, and security measures implemented across the stack.

---

## Table of Contents

- [Non-Custodial Architecture](#non-custodial-architecture)
- [Threat Model](#threat-model)
- [Cryptography](#cryptography)
- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Security Headers](#security-headers)
- [Privacy & Metadata Minimization](#privacy--metadata-minimization)
- [Data Retention Policy](#data-retention-policy)
- [Audit Logging](#audit-logging)
- [Infrastructure Hardening](#infrastructure-hardening)
- [Security Audit Checklist](#security-audit-checklist)
- [Responsible Disclosure](#responsible-disclosure)

---

## Non-Custodial Architecture

**GhostBill cannot spend your funds.** This is the most important security property of the system.

GhostBill operates in **view-only mode**. When a merchant registers, they provide their Monero primary address and **secret view key**. The view key allows GhostBill to detect incoming payments, but it **cannot create transactions or move funds**. The merchant's spend key never leaves their wallet.

Even in the worst-case scenario — a full server compromise with root access — an attacker cannot steal a single piconero. They could see transaction history and metadata, but moving funds is cryptographically impossible without the spend key.

**What GhostBill can do with a view key:**
- Detect incoming payments to subaddresses
- Read transaction amounts and confirmation counts
- Generate subaddresses for invoices

**What GhostBill cannot do:**
- Send or spend Monero
- Create transactions
- Access the spend key
- Move funds to any address

---

## Threat Model

GhostBill's threat model considers 9 distinct threat actors and their potential attack vectors:

### 1. Root Compromise (Server Access)

| Aspect | Detail |
|--------|--------|
| **Can see** | Transaction history, encrypted view keys, metadata |
| **Cannot do** | Steal funds (no spend key exists on server) |
| **Mitigation** | View keys encrypted with AES-256-GCM; master encryption key stored separately in `.env` (production: HashiCorp Vault); non-custodial architecture eliminates financial risk |

### 2. External Attacker — API Abuse

| Aspect | Detail |
|--------|--------|
| **Can see** | Public endpoints (health, price) |
| **Cannot do** | Access authenticated endpoints without valid API key |
| **Mitigation** | API keys hashed with bcrypt (cost ≥ 12); rate limiting across 4 tiers; Fail2Ban for brute-force protection; constant-time key comparison (`hmac.compare_digest()`) |

### 3. External Attacker — Webhook Spoofing

| Aspect | Detail |
|--------|--------|
| **Can see** | Nothing (requires knowing webhook URL) |
| **Cannot do** | Forge payment confirmations |
| **Mitigation** | HMAC-SHA256 signature on every delivery (`X-GhostBill-Signature`); timestamp validation; unique event IDs for deduplication |

### 4. External Attacker — Replay Attack

| Aspect | Detail |
|--------|--------|
| **Can see** | Previously intercepted webhook payloads |
| **Cannot do** | Re-trigger payment events |
| **Mitigation** | Idempotent `event_id` fields; nonce validation for auth; timestamp checking |

### 5. Network Snooper — Traffic Analysis

| Aspect | Detail |
|--------|--------|
| **Can see** | Encrypted traffic metadata |
| **Cannot do** | Decrypt content or correlate users |
| **Mitigation** | Tor Hidden Services for API + dashboard; all outgoing connections (webhooks, price feed) routed through Tor SOCKS5 proxy; 50–200ms timing jitter on all responses |

### 6. Malicious Merchant — Cross-Tenant Access

| Aspect | Detail |
|--------|--------|
| **Can see** | Only their own invoices and payments |
| **Cannot do** | Access other merchants' data |
| **Mitigation** | Row-level database isolation; every query filtered by `merchant_id`; API keys scoped to individual merchants |

### 7. Malicious Subscriber — Payment Correlation

| Aspect | Detail |
|--------|--------|
| **Can see** | Their own payment proof |
| **Cannot do** | Link payments to other subscribers |
| **Mitigation** | Unique subaddress generated per invoice; no address reuse; subaddress index not exposed to payers |

### 8. Blockchain Reorg

| Aspect | Detail |
|--------|--------|
| **Can see** | Reorganized chain state |
| **Cannot do** | Permanently confirm a reversed transaction |
| **Mitigation** | Payments tracked by `tx_hash`; transactions that disappear are marked `orphaned`; invoice status recalculated excluding orphaned payments; `payment.orphaned` webhook dispatched |

### 9. Rogue Employee / Insider

| Aspect | Detail |
|--------|--------|
| **Can see** | Nothing without proper credentials |
| **Cannot do** | Exfiltrate data undetected |
| **Mitigation** | Audit logging on all 14 critical event types; encrypted view keys (even DB access doesn't reveal plaintext); minimal access principle; log redaction prevents sensitive data in logs |

---

## Cryptography

GhostBill uses standard, well-audited cryptographic primitives. No custom cryptography is used anywhere in the codebase.

### Encryption at Rest

| Target | Algorithm | Details |
|--------|-----------|---------|
| Merchant view keys | AES-256-GCM | Unique 12-byte nonce per encryption (`os.urandom`); master key from `MASTER_ENCRYPTION_KEY` env var |
| API keys | bcrypt | Cost factor ≥ 12; only hash stored, plaintext shown once at creation |
| Database fields | PostgreSQL encrypted connection | TLS between application and database |

### Signatures & Authentication

| Target | Algorithm | Details |
|--------|-----------|---------|
| Webhook signatures | HMAC-SHA256 | Per-merchant `webhook_secret`; signature over raw JSON body |
| API key comparison | Constant-time | `hmac.compare_digest()` prevents timing attacks |
| Dashboard auth | Monero message signing | Nonce → sign with wallet → verify via wallet-rpc |

### Key Management

| Key | Storage | Rotation |
|-----|---------|----------|
| Master encryption key | `.env` file (production: Vault) | Manual; re-encrypt all view keys on rotation |
| API keys | bcrypt hash in PostgreSQL | Merchant creates new key, revokes old |
| Webhook secrets | Plaintext in PostgreSQL (per-merchant) | `POST /v1/merchants/me/webhook-secret` |
| wallet-rpc password | `.env` file | Manual; update Docker Compose |
| Session tokens (`gbs_`) | Redis with 24h TTL | Auto-expire; logout revokes immediately |

---

## Authentication

GhostBill supports two authentication methods:

### API Key Authentication (Primary)

Used for programmatic access. Keys are prefixed for easy identification:

- `gb_live_<hex32>` — production environment
- `gb_test_<hex32>` — test environment

Keys are looked up by prefix (first 8 chars stored in plaintext), then verified against the bcrypt hash. This avoids a full-table scan on every request.

### Monero Signature Authentication (Dashboard)

Used for the web dashboard. Passwordless flow:

1. Client requests a nonce for their Monero address (`POST /v1/auth/nonce`)
2. Nonce stored in Redis with 5-minute TTL, bound to the address
3. Merchant signs the nonce with `monero-wallet-cli sign`
4. Client submits address + nonce + signature (`POST /v1/auth/verify`)
5. Server verifies signature via wallet-rpc `verify` method
6. On success, server returns session token `gbs_<hex64>` with 24h TTL
7. Nonce is consumed regardless of result (single-use)

The auth middleware automatically detects the token type (`gb_live_`/`gb_test_` vs `gbs_`) and routes to the appropriate verification path.

---

## Rate Limiting

All endpoints are rate-limited using a Redis sliding window algorithm. Limits are enforced per API key hash (authenticated) or per IP (unauthenticated).

| Tier | Endpoints | Limit |
|------|-----------|-------|
| Strict | `POST /v1/merchants` | 5/hour |
| Write | `POST /v1/invoices`, `POST /v1/api-keys` | 60/min |
| Read | `GET` endpoints (authenticated) | 120/min |
| Public | `GET /health`, `GET /v1/price` | 300/min |

Rate limit status is communicated via response headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and `Retry-After` (on 429).

---

## Security Headers

Every API response includes the following security headers:

| Header | Value |
|--------|-------|
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | `accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=(), interest-cohort=()` |
| `Cache-Control` | `no-store, no-cache, must-revalidate, private` |
| `Pragma` | `no-cache` |

---

## Privacy & Metadata Minimization

GhostBill is built for privacy-conscious merchants and their customers.

**IP addresses are NEVER logged.** All IP information is stripped from request logs before they are written.

**Log redaction is active.** A regex-based filter automatically redacts sensitive patterns from all log output:
- API keys (`gb_live_...`, `gb_test_...`, `gbs_...`)
- Monero addresses (95-char strings starting with `4` or `8`)
- Transaction hashes (64-char hex strings)
- View keys

**No third-party dependencies that leak data:**
- No analytics scripts
- No tracking pixels
- No external CDN dependencies in the API
- No telemetry or crash reporting

**Timing jitter:** Every API response has a random 50–200ms delay added, preventing timing-based correlation attacks.

**Tor routing:** All outgoing connections (webhook deliveries, price feed queries) are routed through the Tor SOCKS5 proxy, preventing GhostBill's server IP from being exposed to merchant webhook endpoints or third-party services.

**Tor Hidden Services:** Both the API and dashboard are accessible via `.onion` addresses, allowing fully anonymous access without revealing the server's IP or the client's IP.

---

## Data Retention Policy

GhostBill follows a **privacy-by-default** approach to data retention. A background task automatically cleans up old data:

| Data | Retention | Rationale |
|------|-----------|-----------|
| Expired + unpaid invoices | 48 hours | No business value; privacy-by-default |
| Webhook delivery logs | 30 days | Debugging window; purge after |
| Audit log entries | 90 days | Compliance and investigation window |
| Payment records | Indefinite | Merchant needs proof of payment; immutable |
| Merchant accounts | Indefinite | Active until manually deleted |
| Session tokens (`gbs_`) | 24 hours | Auto-expire in Redis |
| Auth nonces | 5 minutes | Auto-expire in Redis |

The data retention task runs as a background process and never deletes confirmed payment records.

---

## Audit Logging

GhostBill logs 14 critical event types to the `audit_log` database table:

| # | Event | Description |
|---|-------|-------------|
| 1 | `merchant.registered` | New merchant created |
| 2 | `merchant.updated` | Merchant profile changed |
| 3 | `merchant.webhook_secret_rotated` | Webhook secret regenerated |
| 4 | `api_key.created` | New API key generated |
| 5 | `api_key.revoked` | API key deactivated |
| 6 | `invoice.created` | New invoice created |
| 7 | `invoice.cancelled` | Invoice manually cancelled |
| 8 | `invoice.expired` | Invoice expired |
| 9 | `invoice.status_changed` | Invoice status transition |
| 10 | `payment.detected` | Payment found in mempool |
| 11 | `payment.confirmed` | Payment confirmed on chain |
| 12 | `payment.orphaned` | Payment disappeared (reorg) |
| 13 | `auth.login` | Dashboard session created |
| 14 | `auth.logout` | Dashboard session revoked |

Audit logging is **asynchronous** — events are dispatched via `asyncio.create_task()` and never block the API response. Each entry records the event type, merchant ID, metadata, and timestamp.

---

## Infrastructure Hardening

### Server

| Measure | Configuration |
|---------|---------------|
| SSH | Key-only authentication; password auth disabled; non-standard port |
| Firewall (UFW) | Default deny; allow SSH + Tor only; ports 8013/3013 NOT exposed externally |
| Fail2Ban | Block IP after 3 failed SSH attempts; API brute-force protection |
| Auto-updates | `unattended-upgrades` for security patches |

### Monero Infrastructure

| Measure | Configuration |
|---------|---------------|
| monerod | `--restricted-rpc` flag (prevents remote shutdown/config changes) |
| wallet-rpc | RPC auth with 64-char hex password; bound to `127.0.0.1` or Docker network only |
| Wallet files | `chmod 700` on wallet data directory |
| Subaddress pool | `--subaddress-lookahead 5000:5000` (prevents address exhaustion) |
| Node connection | Tor SOCKS5 proxy for outbound p2p connections |

### Docker

| Measure | Configuration |
|---------|---------------|
| Network isolation | Internal Docker network; only backend exposes ports via `127.0.0.1` |
| No host networking | Containers use bridge network |
| Resource limits | Memory and CPU limits per container |
| Read-only filesystems | Where possible |
| No privileged mode | All containers run unprivileged |

---

## Security Audit Checklist

This checklist is verified before every release:

**Architecture:**
- API is stateless (no server-side sessions for API keys)
- wallet-rpc is not publicly accessible
- Database is on private network (Docker internal)
- Tor proxy enforced for all outgoing connections

**Cryptography:**
- View keys encrypted with AES-256-GCM, unique nonce per encryption
- Master encryption key stored externally (not in code/git)
- API keys hashed with bcrypt (cost ≥ 12)
- HMAC-SHA256 for webhook signatures with replay protection
- Constant-time comparison for all secret comparisons

**State machine:**
- No illegal status transitions possible
- Expiration does not override paid status
- Race conditions handled (blockchain timestamp authority)
- Reorg handling: payments marked orphaned, invoice recalculated

**API:**
- Rate limiting active on all tiers
- SQL injection safe (SQLAlchemy ORM, parameterized queries)
- Pagination limits enforced (max 100 per page)
- No mass enumeration possible
- No sensitive data in error responses

**Privacy:**
- Logs never link address + amount together
- No full view keys, API keys, or tx hashes in logs
- Merchant data isolation (row-level filtering)
- IP addresses never logged
- Timing jitter active on all responses

---

## Responsible Disclosure

If you discover a security vulnerability in GhostBill, please report it responsibly:

**Email:** contact@ghostbill.org (PGP key available on request)

**What to include:**
- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Your suggested fix (if any)

**Our commitment:**
- Acknowledge receipt within 24 hours
- Provide an initial assessment within 72 hours
- Work with you on a fix before public disclosure
- Credit you in the security advisory (unless you prefer anonymity)

**Please do NOT:**
- Publicly disclose the vulnerability before we have a fix
- Access or modify other users' data
- Perform denial-of-service attacks

We do not currently offer a bug bounty program, but we deeply appreciate responsible disclosure and will credit all valid reports.
