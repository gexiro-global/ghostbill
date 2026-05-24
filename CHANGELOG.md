# Changelog

All notable changes to GhostBill are documented in this file.

## [1.3-rc1] - 2026-05-24

### Added

- CI/CD pipeline: GitHub Actions workflow, local CI runner (`scripts/ci-test.sh`)
- Test compose stack (`docker-compose.test.yml`) with isolated `ghostbill-ci` project
- Baseline migration with full Phase 0-4 DDL for clean install
- `.env.test.example` for CI with test-only values

### Changed

- Baseline migration rewritten as raw SQL (fixes SQLAlchemy enum creation conflicts)

## [1.3-beta-wave5] - 2026-05-24

### Added

- Wave 5 test suite: 59 service-level tests in `tests/wave5/`
- Service-level test infrastructure: NullPool engine, FK-safe cleanup, setup-only helpers
- Concurrent race tests via `asyncio.gather` with isolated engines
- Cross-merchant authorization negative tests
- Analytics semantic verification (confirmed-only, merchant isolation)
- pytest markers: `service`, `integration`, `slow`, `stress`

### Fixed

- CRIT-10: Payment tests now use `PaymentService.process_transfer()` instead of direct DB INSERT
- CRIT-11: Reorg tests use `PaymentService.handle_reorg()` instead of direct status UPDATE
- CRIT-12: Duplicate transaction idempotency verified at service level
- CRIT-13: Concurrent payment race conditions tested
- CRIT-14: Conftest separates setup helpers from behavior under test
- HIGH-24–30: Confirmation, webhook, subscription, auth, analytics coverage
- MED-36: SSE, wallet failure, pagination, input validation coverage
- LOW-19: pytest markers applied

## [1.3-beta-wave4] - 2026-05-23

### Fixed

- 22 findings: distributed Redis leases on all 6 background loops, atomic webhook claiming (SELECT FOR UPDATE SKIP LOCKED), confirmed-only settlement, retention FK ordering, HMAC replay protection (timestamp + delivery_id), AES-GCM AAD binding

## [1.3-beta-wave3b] - 2026-05-21

### Fixed

- 10 findings: subscription transition guards, grace period timing, prepay idempotency, billing anchor validation, public endpoint hardening

## [1.3-beta-wave3a] - 2026-05-19

### Fixed

- 12 findings: confirmed-only settlement (10 conf threshold), reorg reversal for paid invoices, late_paid requires full confirmed amount, cancelled invoice exception recording, overpaid transition, prepay guard cleanup, XMR precision validation

### Changed

- Settlement model: two-phase detection (mempool) + confirmation (10 blocks)
- TERMINAL_STATUSES reduced to `{cancelled}` only (paid is non-terminal for reorg)

## [1.3-beta-wave2] - 2026-05-15

### Fixed

- 18 findings: X-Forwarded-For rate limiter bypass, internal renewal auth, log redaction on child loggers, config validation, SQL echo disabled, auth timing equalization, audit session isolation, middleware ordering, cursor tenant isolation, license soft enforcement, nonce burn, auth commit, Redis fail mode, SSE classification, email/metadata validation

## [1.3-beta-wave1] - 2026-05-09

### Fixed

- 6 findings: 18 explicit FK ondelete, 12 CHECK constraints, 11 UNIQUE constraints, DLQ retry delivery plumbing

## [1.2.0-beta] - 2026-05-01

### Added

- License system: 4 tiers (Community/Starter/Growth/Enterprise), key generation, admin CRUD, public verification
- Dashboard license gating: LicenseGate component, useLicense hook, tier badge

## [1.1.0-beta] - 2026-04-27

### Added

- Pre-payment model: 1–36 periods upfront with configurable discounts
- Trial periods: 1–365 days with auto-activation
- Subscription pending changes (amount, interval, grace periods)
- Billing anchor for deterministic renewal dates
- Analytics dashboard (revenue, invoice stats, subscription metrics)
- SSE real-time events on payment pages
- Cursor-based pagination on all list endpoints
- Monero signature authentication for dashboard
- Admin panel for instance operators
- Dead Letter Queue with manual retry
- 22 webhook event types

## [1.0.0-beta] - 2026-02-12

### Added

- Core payment processing: invoice creation, subaddress generation, payment detection
- 7 invoice statuses, 3 payment statuses
- Basic subscription model with grace periods
- Webhook delivery with HMAC-SHA256 signatures and retry
- API key management
- Docker Compose deployment (postgres, redis, backend, wallet-rpc)
- Tor hidden service support
