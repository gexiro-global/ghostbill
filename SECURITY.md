# Security Policy

## Reporting a Vulnerability

Please do not open public GitHub issues for security vulnerabilities.

Use the official GhostBill website for current security contact and disclosure instructions:

https://ghostbill.org

Do not include private keys, wallet seeds, production secrets, customer data, or exploit payloads against third-party systems.

## Scope

In scope:

- GhostBill backend API (`backend/app/`)
- Database schema and migrations
- Authentication and authorization logic
- Webhook signature verification
- Payment detection, confirmation, settlement, and reorg logic
- Subscription lifecycle management

Out of scope:

- GhostBill landing page / website source
- Monero protocol vulnerabilities
- monero-wallet-rpc vulnerabilities
- Third-party dependency vulnerabilities
- Social engineering

## Security Audit History

GhostBill has undergone a 5-wave automated security audit covering ~11,200 lines of backend code across 67 files. 82 of 99 identified findings have been resolved.

| Wave | Focus | Findings Closed |
|------|-------|----------------|
| Wave 1 | Schema hardening (FK, CHECK, UNIQUE constraints) | 6 |
| Wave 2 | Auth, rate limiting, log redaction, config validation | 18 |
| Wave 3A | Payment settlement correctness (confirmed-only, reorg) | 12 |
| Wave 3B | Subscription semantics, transition guards | 10 |
| Wave 4 | Background tasks, webhook atomicity, crypto hardening | 22 |
| Wave 5 | Service-level test suite rebuild (59 tests) | 14 |

## Disclosure

We prefer coordinated disclosure for good-faith reports.
