# GhostBill Upgrade Guide

**Applies to:** v1.3-rc3 and later.
**Audience:** self-hosted operators and merchants upgrading their GhostBill deployment.
**Scope:** safe upgrade and rollback procedures for Docker Compose and source-checkout deployments.

This guide is conservative on purpose. Always test an upgrade on a staging environment before touching production. Read the relevant [`CHANGELOG.md`](../CHANGELOG.md) entry before starting.

For sensitive disclosures, follow [`SECURITY.md`](./SECURITY.md). For runtime troubleshooting, see [`TROUBLESHOOTING.md`](./TROUBLESHOOTING.md).

All examples use placeholders. Replace before running.

---

## Table of contents

1. [Upgrade principles](#1-upgrade-principles)
2. [Pre-upgrade checklist](#2-pre-upgrade-checklist)
3. [Standard Docker Compose upgrade flow](#3-standard-docker-compose-upgrade-flow)
4. [Source-checkout upgrade flow](#4-source-checkout-upgrade-flow)
5. [Database migrations](#5-database-migrations)
6. [Configuration changes](#6-configuration-changes)
7. [Wallet-rpc and Monero daemon safety](#7-wallet-rpc-and-monero-daemon-safety)
8. [Webhook upgrade safety](#8-webhook-upgrade-safety)
9. [Post-upgrade verification](#9-post-upgrade-verification)
10. [Rollback procedure](#10-rollback-procedure)
11. [Version-specific notes](#11-version-specific-notes)
12. [Common upgrade failures](#12-common-upgrade-failures)
13. [Sensitive data rules during upgrades](#13-sensitive-data-rules-during-upgrades)
14. [Upgrade issue checklist](#14-upgrade-issue-checklist)

---

## 1. Upgrade principles

* **Back up before any upgrade.** Database backup is non-negotiable; `.env` backup is too, kept in a secrets manager, not in repo or chat.
* **Test on staging first** when the changelog mentions schema, security, or background-task changes.
* **Read the CHANGELOG entry** for the target tag.
* **Never expose wallet-rpc publicly** during or after an upgrade.
* **Confirm Monero daemon sync** before and after.
* **Run migrations** if the production compose does not auto-apply them (the default production compose in this repo does NOT auto-migrate — only the CI test compose does).
* **Keep secrets out of upgrade logs and tickets.** Wallet seeds, spend keys, `.env`, API keys, and webhook secrets never belong in a paste.

---

## 2. Pre-upgrade checklist

Before touching production:

```bash
# Current commit and tag
cd /opt/ghostbill
git log --oneline -1
git describe --tags --always

# Running version (must match git tag)
curl -s https://your-ghostbill.example/health | jq '.version'

# Container state
docker compose ps

# Database backup (compressed, encrypted is even better)
docker exec ghostbill_postgres pg_dump -U ghostbill ghostbill \
  | gzip > /opt/ghostbill-backups/db_pre-upgrade_$(date +%Y%m%d_%H%M).sql.gz

# Detection state
curl -s https://your-ghostbill.example/health | jq '.detection'

# Webhook backlog / DLQ (operator key required)
curl -s https://your-ghostbill.example/v1/webhooks/dead-letters \
  -H "Authorization: Bearer gb_live_xxx..." | jq '.data | length'
```

If `blocks_behind` is large and growing, fix daemon sync **before** the upgrade. If the DLQ is non-empty, decide whether to drain it before or after.

Keep a copy of the current `.env` outside the server (encrypted backup of secrets), not by emailing it to yourself.

---

## 3. Standard Docker Compose upgrade flow

This is the typical flow when the deployment lives in `docker-compose.yml` and you've checked out the GhostBill source on the host.

```bash
cd /opt/ghostbill

# 1. Make sure working tree is clean
git status --short

# 2. Fetch and inspect the target tag
git fetch --all --tags
git log --oneline -10

# 3. Read CHANGELOG for the target tag BEFORE checkout
git show v1.3-rc3:CHANGELOG.md | head -40

# 4. Checkout (or merge main) to the target tag
git checkout v1.3-rc3
# OR for the moving main branch on a staging host:
# git pull origin main

# 5. Review env diff against the deployed .env
diff .env.example .env || true

# 6. Rebuild backend image if Dockerfile or pyproject.toml changed
docker compose build backend

# 7. Apply migrations BEFORE restarting workloads if migrations changed
docker compose run --rm backend alembic upgrade head

# 8. Recreate containers
docker compose up -d

# 9. Wait for healthchecks
sleep 30
docker compose ps

# 10. Verify
curl -s https://your-ghostbill.example/health | jq .
```

**Notes:**

* `docker compose up -d` recreates containers from the image. Anything you `docker cp`-ed into a running container is lost; rebuild and bake changes into the image instead.
* `docker compose restart` does NOT re-read `.env`. Use `docker compose up -d` after env changes.
* The production `docker-compose.yml` does not auto-apply migrations. Step 7 is the only thing that does. Skipping it leads to runtime errors and possible data corruption.
* The CI test compose (`docker-compose.test.yml`) auto-applies migrations at startup; do not assume production behaves the same.

---

## 4. Source-checkout upgrade flow

For operators running from source (e.g. on a Tor hidden-service VPS):

```bash
cd /opt/ghostbill

# Make sure working tree is clean before changing branches/tags
git status --short

# Backup config
cp .env /opt/ghostbill-backups/env_pre-upgrade_$(date +%Y%m%d_%H%M)

# Checkout the target tag/commit
git fetch --all --tags
git checkout v1.3-rc3

# Optional: run the local CI gate on a staging clone
bash scripts/ci-test.sh

# Apply migrations before restarting
docker compose run --rm backend alembic upgrade head

# Restart per your deployment policy
docker compose up -d

# Health
curl -s https://your-ghostbill.example/health | jq .
```

The local CI runner is `scripts/ci-test.sh`. It uses an isolated Docker Compose project (`ghostbill-ci`) so it will not collide with production. Treat its result as a smoke test, not as a production guarantee.

---

## 5. Database migrations

GhostBill uses Alembic. Migration scripts live in `backend/migrations/versions/`.

```bash
# Show current applied head inside the backend container
docker exec ghostbill_backend alembic current

# Apply pending migrations (operator only, after a backup)
docker compose run --rm backend alembic upgrade head

# List migration history
docker exec ghostbill_backend alembic history --verbose
```

**Important:**

* **Always back up the database before running migrations.** Some migrations may be irreversible or only partially reversible.
* **Do not skip versions** by checking out a far-future tag without running the intermediate migrations — Alembic will refuse, but if you bypass it, you get inconsistent schema.
* **Rollback caveat:** `git checkout <older-tag>` does NOT rewind the database. Downgrading schema requires either an Alembic downgrade (where supported) or restoring from the backup taken in § 2.

If a migration fails mid-way:

1. Capture the error (sanitized).
2. Do **not** run further migrations.
3. Restore the database backup taken in § 2.
4. Open a sanitized issue with the migration revision ID and the error excerpt.

---

## 6. Configuration changes

Review your `.env` against `.env.example` after every upgrade. Common fields that may change between releases:

* `APP_VERSION` — must match the deployed code. The repo includes `scripts/bump-version.sh` for keeping `VERSION`, `pyproject.toml`, `config.py`, `.env.example`, and `.env` aligned.
* `REDIS_PASSWORD` and `REDIS_URL` — if Redis authentication is enabled in the compose file, your `.env` must include the password in `REDIS_URL`: `redis://:<password>@<host>:<port>/0`.
* `WALLET_RPC_HOST` — the address backend uses to reach `wallet-rpc`. Must remain reachable only from inside the Docker network, never from the public internet.
* `CONFIRMATION_THRESHOLD` — default `10`. Changing this changes when invoices transition to `paid`.
* `RATE_LIMIT_*` — per-IP and per-merchant request quotas.
* `MASTER_ENCRYPTION_KEY` — do **not** rotate without a documented re-encryption plan; rotating in place will make existing encrypted view keys unreadable.
* `SECRET_KEY` — used for session signing; rotating it invalidates active dashboard sessions.
* `WEBHOOK_SIGNING_KEY` and per-merchant `webhook_secret` — do not rotate during a routine upgrade unless you intend to break existing verifications on the merchant side.

Never copy `.env` into a chat message, ticket, or screenshot, even when redacted. Diff structure only:

```bash
comm -23 <(cut -d= -f1 .env.example | sort -u) <(cut -d= -f1 .env | sort -u)
```

(This shows env keys present in `.env.example` but missing from `.env`.)

---

## 7. Wallet-rpc and Monero daemon safety

* **wallet-rpc must never be reachable from the public internet.** Bind it to the Docker bridge gateway or otherwise restrict it. Do not expose port `18083` in any compose file.
* **Do not rotate the merchant Monero wallet** during a routine app upgrade. View keys live encrypted in the database; rotating the wallet or `MASTER_ENCRYPTION_KEY` requires a migration plan, not a redeploy.
* **Verify daemon sync before and after.** Both the public `/health` and the operator `/v1/admin/health` expose `detection.blocks_behind`. It should be `0` (or near) in steady state.
* **Wallet files are not part of an image upgrade.** They live in the wallet-rpc volume. Treat them like cold storage: back up the wallet seed offline; never paste it anywhere.

If the upgrade changes wallet-rpc networking (as v1.3-rc3 did), confirm after restart that:

1. `wallet-rpc` container is healthy (`docker compose ps`).
2. Logs show successful daemon connection (`docker compose logs --tail 100 walletrpc | grep -Ei 'daemon|connect|refresh'`).
3. New invoices receive subaddresses (test on a `gb_test_` key).

---

## 8. Webhook upgrade safety

Webhook deliveries can be interrupted by container restarts. Plan accordingly:

* **Drain or accept duplicates.** Webhook retries continue after restart. Merchant endpoints must be idempotent on `X-GhostBill-Delivery-Id` regardless of upgrade timing.
* **Inspect the DLQ before and after** to spot endpoints that failed during the upgrade window.
* **Do not rotate `webhook_secret`** unless you intend to invalidate verifications on the merchant side.
* **Signature format and headers should remain stable across patch upgrades.** Verify by replaying a stored delivery against your verifier post-upgrade. See [`WEBHOOKS.md`](./WEBHOOKS.md) for the verification helper.

Check pending deliveries:

```bash
curl -s 'https://your-ghostbill.example/v1/webhooks?limit=50' \
  -H "Authorization: Bearer gb_live_xxx..." | jq '.data | length'
```

Check DLQ:

```bash
curl -s https://your-ghostbill.example/v1/webhooks/dead-letters \
  -H "Authorization: Bearer gb_live_xxx..." | jq '.data | length'
```

---

## 9. Post-upgrade verification

After `docker compose up -d` returns:

```bash
# Containers healthy
docker compose ps

# Public health
curl -s https://your-ghostbill.example/health | jq .

# Operator health
curl -s https://your-ghostbill.example/v1/admin/health \
  -H "Authorization: Bearer gb_live_xxx..." | jq '{database, redis, wallet_rpc, detection}'

# API auth works
curl -s https://your-ghostbill.example/v1/merchants/me \
  -H "Authorization: Bearer gb_live_xxx..." | jq '.id, .environment'

# Sanitized recent backend logs
docker compose logs --tail 100 backend
```

Follow up with a controlled smoke test on a `gb_test_` key: create an invoice, observe it return a subaddress, and confirm no errors in backend logs.

Do not run smoke tests on `gb_live_` against real customer subaddresses just to verify an upgrade.

---

## 10. Rollback procedure

The safe rollback path:

1. **Halt customer-facing traffic** at the reverse proxy or by disabling the relevant merchants (operator action) so no new invoices land in an inconsistent state.
2. **Stop the backend container.**

   ```bash
   docker compose stop backend
   ```
3. **Restore code** to the previous tag.

   ```bash
   git checkout <previous-tag>
   ```
4. **Restore the database** from the backup taken in § 2 if any migrations ran:

   ```bash
   gunzip -c /opt/ghostbill-backups/db_pre-upgrade_<timestamp>.sql.gz \
     | docker exec -i ghostbill_postgres psql -U ghostbill -d ghostbill
   ```

   Restore is destructive. Confirm you have the right backup before running it.
5. **Restore `.env`** if you changed config during the upgrade.
6. **Rebuild and bring the stack up** at the previous tag.

   ```bash
   docker compose build backend
   docker compose up -d
   ```
7. **Verify health** (§ 9) before re-enabling traffic.
8. **Reconcile** payments and webhooks for the upgrade window. Replay any webhooks that landed against the new schema but need to be re-applied against the rolled-back schema.

The repo does not provide a one-command rollback; treat rollback as an explicit operator procedure.

---

## 11. Version-specific notes

### v1.3-rc3

From [`CHANGELOG.md`](../CHANGELOG.md), v1.3-rc3 includes:

* **wallet-rpc network binding hardened.** wallet-rpc no longer accepts connections from arbitrary external interfaces. Confirm after upgrade that `WALLET_RPC_HOST` in `.env` matches the backend's view of wallet-rpc (typically the Docker bridge gateway address used in your `docker-compose.yml`).
* **Strict AES-GCM AAD validation.** The previous silent fallback to decryption without AAD was removed. An explicit migration-only helper exists for legacy data; normal decrypt paths are strict.
* **Redis authentication.** If you enable `--requirepass` for Redis, your `.env` `REDIS_URL` must include the password (`redis://:<password>@<host>:<port>/0`).
* **Backend runs as a non-root user.** No action required unless you mount volumes that the previous root-owned process wrote to; in that case adjust ownership.
* **bcrypt 72-byte guard for API keys.** A runtime check rejects keys longer than the bcrypt limit. Default key generation stays within the limit.
* **Subscription hook failures are now logged as errors and recorded to the audit log.** No action required.
* **SSH hardening script is more distro-portable.** No action required.
* **Version alignment across config files.** Run `scripts/bump-version.sh` only if you fork and bump.

**Pre-upgrade actions for v1.3-rc3 specifically:**

1. Generate `REDIS_PASSWORD` with `openssl rand -hex 32` and update both `REDIS_PASSWORD` and `REDIS_URL` in `.env`.
2. Confirm `WALLET_RPC_HOST` in `.env` matches the configured binding in `docker-compose.yml`.
3. After upgrade, re-run `bash scripts/ci-test.sh` on staging to confirm the new env layer.

If you previously kept an `.env.test` from before v1.3-rc3, delete it so the CI script regenerates from the updated `.env.test.example`:

```bash
rm -f .env.test
bash scripts/ci-test.sh
```

### Future versions

When a new version is published:

* The CHANGELOG entry describes what changed.
* Re-read § 2 through § 9.
* Add any new env keys from `.env.example` into your `.env`.
* Run migrations.

---

## 12. Common upgrade failures

| Symptom | Likely cause | Safe check | Recovery |
|---|---|---|---|
| Backend container unhealthy after `up -d` | Missing required env, pending migration, or broken `REDIS_URL` | `docker compose logs --tail 200 backend` | Set env, run migrations, fix `REDIS_URL` |
| `Production requires SECRET_KEY and MASTER_ENCRYPTION_KEY` on startup | Required env missing in production mode | `grep -E 'SECRET_KEY|MASTER_ENCRYPTION_KEY' .env` | Generate with `openssl rand -hex 32`, set in `.env`, restart |
| Backend startup fails with `redis.exceptions.AuthenticationError: Authentication required` | `REDIS_URL` lacks password but Redis enforces one | `grep REDIS_URL .env` | Update `REDIS_URL` to include the password |
| wallet-rpc container unhealthy | wallet-rpc cannot reach `monerod` or refused to bind | `docker compose logs --tail 200 walletrpc` | Fix `--daemon-host` or `--rpc-bind-ip` per your network setup |
| `blocks_behind` grows over time | Detection loop failing or daemon stalled | `/v1/admin/health` detection block, `monerod` logs | Restart wallet-rpc, fix monerod sync, then restart backend |
| `401 Unauthorized` after upgrade | API key environment mismatch or rotated key | `GET /v1/merchants/me` with the same key on the previous tag | Use the correct env key; rotate via `POST /v1/api-keys` if needed |
| Webhook signature failures on merchant side | Merchant verifier reads parsed JSON instead of raw body | Reproduce against a stored delivery body | Always verify against raw bytes; use `compare_digest` |
| Duplicate webhook events post-restart | Normal retry behavior | `X-GhostBill-Delivery-Id` in logs | Deduplicate on delivery ID |
| `alembic upgrade head` errors | Conflicting schema state, missing dependency | `alembic current`, error output | Restore DB from § 2 backup, open sanitized issue |
| `/health` `version` shows old version | Stale container, `.env` `APP_VERSION` not updated, or build skipped | `git log -1`, `grep APP_VERSION .env` | `docker compose build backend && docker compose up -d` |
| pytest cache permission warning during CI | Non-root container cannot write to `/app/.pytest_cache` | n/a | Non-blocking; tests still pass. Tracked as a separate cosmetic backlog item. |

---

## 13. Sensitive data rules during upgrades

During upgrades, the temptation to paste "just this one log" is highest. Don't.

Never paste:

* `.env` contents (any of `SECRET_KEY`, `MASTER_ENCRYPTION_KEY`, `WEBHOOK_SIGNING_KEY`, `REDIS_PASSWORD`, `POSTGRES_PASSWORD`, `WALLET_RPC_PASS`, `WALLET_PASSWORD`, `MONEROD_RPC_*`).
* Monero seed phrases or mnemonics.
* Spend keys (private keys).
* Wallet files or wallet backups.
* Merchant API keys (`gb_live_*`, `gb_test_*`).
* Per-merchant webhook secrets.
* Production logs containing `Authorization`, `X-GhostBill-Signature`, customer email, or wallet addresses.
* Screenshots that expose any of the above.

GhostBill maintainers will never request any of these to diagnose an upgrade problem. See § 14 for what to share instead.

---

## 14. Upgrade issue checklist

Before opening an issue at <https://github.com/gexiro-global/ghostbill/issues>, gather:

* Previous and target GhostBill version/tag/commit.
* Deployment method (`docker-compose.yml`, source checkout, Tor hidden service, clearnet reverse proxy).
* Sanitized `docker compose ps` output.
* Sanitized `/health` JSON.
* The exact step that failed and the sanitized error message.
* Migration command output if migrations were involved (revision IDs, not stack traces with payloads).
* `detection.blocks_behind` value if detection-related.
* `X-GhostBill-Delivery-Id` of any specific webhook involved (delivery IDs are safe to share).
* What changed in your environment since the last working version.

Do not request or expect email-based support. The repository auto-replies to every new issue with the project's official statement and anti-scam reminder.

For security issues that must not be public, follow [`SECURITY.md`](./SECURITY.md) instead of opening a public issue.
