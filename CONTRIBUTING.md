# Contributing to GhostBill

Thank you for your interest in contributing to GhostBill. This document covers the process for submitting changes, code style expectations, and how to report security issues.

---

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/ghostbill.git`
3. Create a branch: `git checkout -b feature/your-feature-name`
4. Set up the development environment (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md))
5. Make your changes
6. Run tests: `python3 -m pytest tests/ -v`
7. Submit a pull request

---

## Development Setup

```bash
cp .env.example .env
# Fill in .env with test values
docker compose up -d postgres redis
docker compose run --rm backend alembic upgrade head
docker compose up -d
```

Run the test suite before submitting:

```bash
python3 -m pytest tests/ -v --tb=short
```

All 60 tests must pass.

---

## Code Style

**Python (Backend):**
- Python 3.10+
- Follow PEP 8
- Type hints on all function signatures
- Docstrings on public functions and classes
- Async/await for all I/O operations
- Variable and function names in English
- Comments in English

**TypeScript (Frontend):**
- Next.js 15 conventions
- Tailwind CSS for styling (no custom CSS files)
- Functional components with hooks
- TypeScript strict mode

**General:**
- No secrets in code — use `.env`
- No `print()` for debugging — use structured logging
- No `sed` or in-place file edits in scripts — generate complete files
- All amounts in atomic units (piconero) internally

---

## Pull Request Process

1. **One feature per PR.** Keep changes focused and reviewable.
2. **Write tests.** New features need tests. Bug fixes need regression tests.
3. **Update documentation.** If your change affects the API, update `docs/API.md`.
4. **Pass CI.** All tests must pass, no linting errors.
5. **Describe your changes.** PR description should explain what and why.

**PR title format:** `[area] Short description`

Examples:
- `[backend] Add invoice expiry grace period`
- `[frontend] Fix webhook log pagination`
- `[docs] Update wallet-rpc setup instructions`

---

## Commit Messages

Use clear, descriptive commit messages:

```
Add mempool detection retry on RPC timeout

wallet-rpc occasionally returns timeout on get_transfers.
Added 3-retry loop with 2s backoff before marking detection
cycle as failed. Prevents false payment.orphaned events
during temporary RPC hiccups.
```

---

## Reporting Security Issues

**Do NOT open a public issue for security vulnerabilities.**

Report via the official GhostBill website (https://ghostbill.org) with:
- Description of the vulnerability
- Steps to reproduce
- Potential impact

See [docs/SECURITY.md](docs/SECURITY.md#responsible-disclosure) for our full disclosure policy.

---

## What We're Looking For

**High priority:**
- Bug fixes in payment detection or invoice state machine
- Security improvements
- Test coverage improvements
- Documentation improvements

**Welcome contributions:**
- Plugin integrations (WooCommerce, WHMCS, etc.)
- Additional webhook verification examples (Go, Rust, PHP)
- Localization
- Performance optimizations

**Please discuss first:**
- New API endpoints
- Database schema changes
- Changes to the invoice state machine
- New dependencies

Open an issue to discuss before starting work on significant changes.

---

## License

By contributing to GhostBill, you agree that your contributions will be licensed under the [AGPL-3.0 License](LICENSE).
