# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in GhostBill, please report it responsibly.

**Report via:** [ghostbill.org/security](https://ghostbill.org/security)

Please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

Do **not** open a public GitHub issue for security vulnerabilities.

## Response Timeline

We aim to:

- Acknowledge your report within 48 hours
- Provide an initial assessment within 7 days
- Release a fix within 30 days for confirmed vulnerabilities

## Scope

The following are in scope:

- GhostBill backend API (`backend/app/`)
- Database schema and migrations
- Authentication and authorization logic
- Webhook signature verification
- Encryption (AES-256-GCM for view keys)
- Payment processing logic (detection, confirmation, settlement)
- Subscription lifecycle management

The following are out of scope:

- Monero protocol vulnerabilities (report to the Monero project)
- monero-wallet-rpc vulnerabilities (report to the Monero project)
- Issues in third-party dependencies (report upstream)
- Landing page (ghostbill.org)
- Social engineering attacks

## Security Audit History

GhostBill has undergone a 5-wave automated security audit (Codex) covering ~11,200 lines of backend code across 67 files. 82 of 99 identified findings have been resolved.

| Wave | Focus | Findings Closed |
|------|-------|----------------|
| Wave 1 | Schema hardening (FK, CHECK, UNIQUE constraints) | 6 |
| Wave 2 | Auth, rate limiting, log redaction, config validation | 18 |
| Wave 3A | Payment settlement correctness (confirmed-only, reorg) | 12 |
| Wave 3B | Subscription semantics, transition guards | 10 |
| Wave 4 | Background tasks, webhook atomicity, crypto hardening | 22 |
| Wave 5 | Service-level test suite rebuild (59 tests) | 14 |

## Disclosure Policy

We follow coordinated disclosure. We will credit reporters (unless they prefer anonymity) and will not take legal action against good-faith security researchers.
