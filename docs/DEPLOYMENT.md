# GhostBill Deployment Guide

Self-hosted deployment guide for GhostBill — a non-custodial Monero payment processor.

---

## Table of Contents

- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Step-by-Step Setup](#step-by-step-setup)
  - [1. monerod (Monero Node)](#1-monerod-monero-node)
  - [2. Environment Configuration](#2-environment-configuration)
  - [3. Docker Compose Stack](#3-docker-compose-stack)
  - [4. wallet-rpc](#4-wallet-rpc)
  - [5. Database Migrations](#5-database-migrations)
  - [6. Tor Hidden Services (Optional)](#6-tor-hidden-services-optional)
- [Verification](#verification)
- [Backups](#backups)
- [Monitoring](#monitoring)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)

---

## Requirements

**Hardware (minimum):**

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 60 GB (pruned node) | 100 GB |
| Network | Stable connection | Unmetered preferred |

**Software:**
- Linux (Ubuntu 22.04+ recommended)
- Docker 24+ and Docker Compose v2
- monerod (Monero CLI v0.18.x) — synced and running
- Tor (optional, for hidden services and outgoing proxy)

**Network ports (internal, NOT exposed to internet):**

| Service | Port | Binding |
|---------|------|---------|
| Backend (FastAPI) | 8013 | 127.0.0.1 |
| Frontend (Next.js) | 3013 | 127.0.0.1 |
| PostgreSQL | 5445 | 127.0.0.1 |
| Redis | 6391 | 127.0.0.1 |
| wallet-rpc | 18083 | 127.0.0.1 (or 0.0.0.0 with Digest auth for Docker) |
| monerod RPC | 31208 | 127.0.0.1 |
| Tor SOCKS5 | 9050 | 127.0.0.1 |

> ⚠️ **Ports 8013 and 3013 must NOT be exposed to the public internet.** Access is via Tor hidden services or a reverse proxy with TLS.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/ghostbill/ghostbill.git
cd ghostbill

# 2. Create .env from template
cp .env.example .env

# 3. Generate secrets on the server (NEVER in chat or clipboard)
openssl rand -hex 32  # → MASTER_ENCRYPTION_KEY
openssl rand -hex 32  # → WALLET_RPC_PASS
openssl rand -hex 32  # → WALLET_PASSWORD
openssl rand -hex 32  # → SECRET_KEY

# 4. Edit .env with your values
nano .env

# 5. Start infrastructure
docker compose up -d postgres redis

# 6. Run migrations
docker compose run --rm backend alembic upgrade head

# 7. Start all services
docker compose up -d

# 8. Verify
curl http://127.0.0.1:8013/health
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Internet / Tor                     │
│                                                       │
│  ┌──────────┐  ┌──────────┐                          │
│  │ Tor HS   │  │ Tor HS   │                          │
│  │ API      │  │Dashboard │                          │
│  └────┬─────┘  └────┬─────┘                          │
│       │              │                                │
├───────┼──────────────┼────────────────────────────────┤
│       │              │          Server (localhost)     │
│       ▼              ▼                                │
│  ┌─────────┐   ┌──────────┐                          │
│  │ Backend │   │ Frontend │                          │
│  │ :8013   │   │ :3013    │                          │
│  └────┬────┘   └──────────┘                          │
│       │                                               │
│  ┌────┼──────────────────────────┐                   │
│  │    ▼          ▼          ▼    │                   │
│  │ PostgreSQL  Redis   wallet-rpc│  Docker Network   │
│  │ :5445       :6391   :18083    │                   │
│  └───────────────────────┬───────┘                   │
│                          │                            │
│                     ┌────▼────┐                       │
│                     │ monerod │  Host network         │
│                     │ :31208  │                       │
│                     └────┬────┘                       │
│                          │                            │
│                     ┌────▼────┐                       │
│                     │   Tor   │  Outbound p2p         │
│                     │  :9050  │                       │
│                     └─────────┘                       │
└─────────────────────────────────────────────────────┘
```

---

## Step-by-Step Setup

### 1. monerod (Monero Node)

GhostBill requires a **fully synced** Monero node. We recommend running your own node for maximum privacy.

**Install monerod:**

```bash
# Download latest Monero CLI
wget https://downloads.getmonero.org/cli/monero-linux-x64-v0.18.4.5.tar.bz2
tar xjf monero-linux-x64-v0.18.4.5.tar.bz2
sudo cp monero-x86_64-linux-gnu-v0.18.4.5/monerod /usr/local/bin/
sudo cp monero-x86_64-linux-gnu-v0.18.4.5/monero-wallet-rpc /usr/local/bin/
```

**Create monerod config** (`/etc/monero/monerod.conf`):

```ini
# Network
data-dir=/var/lib/monero
log-file=/var/log/monero/monerod.log
log-level=0

# Pruned mode (saves ~60% disk)
prune-blockchain=1
sync-pruned-blocks=1

# RPC
rpc-bind-ip=127.0.0.1
rpc-bind-port=31208
rpc-login=YOUR_RPC_USER:YOUR_RPC_PASS
restricted-rpc=1
confirm-external-bind=0

# Privacy — route p2p through Tor
proxy=127.0.0.1:9050

# Performance
db-sync-mode=safe:sync
block-sync-size=10
```

**Start monerod:**

```bash
monerod --config-file /etc/monero/monerod.conf --detach
```

**Wait for full sync** (can take 12–48 hours on first run):

```bash
monerod --rpc-bind-port 31208 status
```

Verify sync is complete before proceeding:

```bash
curl -s -u USER:PASS --digest -X POST http://127.0.0.1:31208/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' | python3 -m json.tool
```

Look for `"synchronized": true`.

---

### 2. Environment Configuration

Copy the example environment file and generate secrets:

```bash
cp .env.example .env
```

**Generate all secrets on the server:**

```bash
# Master encryption key (AES-256-GCM for view keys)
echo "MASTER_ENCRYPTION_KEY=$(openssl rand -hex 32)"

# Backend secret key
echo "SECRET_KEY=$(openssl rand -hex 32)"

# wallet-rpc password
echo "WALLET_RPC_PASS=$(openssl rand -hex 32)"

# Wallet file password
echo "WALLET_PASSWORD=$(openssl rand -hex 32)"

# PostgreSQL password
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
```

> ⚠️ **Generate secrets on the server only.** Never generate or transmit secrets via chat, clipboard, or unencrypted channels.

Edit `.env` with the generated values. See `.env.example` for all configuration options with descriptions.

---

### 3. Docker Compose Stack

**Start infrastructure services first:**

```bash
docker compose up -d postgres redis
```

Wait for health checks to pass:

```bash
docker compose ps
```

Both `postgres` and `redis` should show `healthy`.

**Start application services:**

```bash
docker compose up -d backend frontend
```

Verify:

```bash
curl -s http://127.0.0.1:8013/health
# Expected: {"status":"healthy","app":"GhostBill","version":"0.1.0"}
```

---

### 4. wallet-rpc

wallet-rpc connects GhostBill to the Monero blockchain via your monerod node.

**Create a wallet** (if you don't have one):

```bash
mkdir -p /root/ghostbill/wallet-data && chmod 700 /root/ghostbill/wallet-data

monero-wallet-cli \
  --generate-new-wallet /root/ghostbill/wallet-data/ghostbill_wallet \
  --password "YOUR_WALLET_PASSWORD" \
  --mnemonic-language English
```

> ⚠️ **Write down the seed phrase immediately and store it offline.** This is your only way to recover funds if the wallet file is lost.

**Extract the view key** (needed for merchant registration):

```bash
monero-wallet-cli \
  --wallet-file /root/ghostbill/wallet-data/ghostbill_wallet \
  --password "YOUR_WALLET_PASSWORD"
```

In the wallet CLI, type `viewkey` and copy the **private view key** (64 hex chars).

**wallet-rpc runs as a Docker container** in the GhostBill stack. It's configured in `docker-compose.yml` with these critical flags:

```yaml
walletrpc:
  image: monero:latest
  network_mode: host
  command: >
    monero-wallet-rpc
      --wallet-file /wallet/ghostbill_wallet
      --password ${WALLET_PASSWORD}
      --rpc-bind-ip 0.0.0.0
      --rpc-bind-port 18083
      --rpc-login ghostbill:${WALLET_RPC_PASS}
      --daemon-host 127.0.0.1
      --daemon-port 31208
      --daemon-login ${MONEROD_RPC_USER}:${MONEROD_RPC_PASS}
      --confirm-external-bind
      --log-level 1
      --log-file /wallet/wallet-rpc.log
```

**Network note:** wallet-rpc uses `network_mode: host` because it needs to reach monerod on `127.0.0.1:31208`. The backend connects to wallet-rpc via the Docker bridge gateway IP (typically `172.23.0.1`). RPC Digest authentication protects the endpoint.

**Important UFW rule** (if using Docker bridge networking):

```bash
ufw allow from 172.23.0.0/16 to any port 18083 comment "wallet-rpc from Docker"
```

**Verify wallet-rpc:**

```bash
curl -s -u ghostbill:YOUR_RPC_PASS --digest -X POST http://127.0.0.1:18083/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_height"}' | python3 -m json.tool
```

**Test subaddress generation:**

```bash
curl -s -u ghostbill:YOUR_RPC_PASS --digest -X POST http://127.0.0.1:18083/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"0","method":"create_address","params":{"account_index":0,"label":"test"}}' \
  | python3 -m json.tool
```

Expected: a subaddress starting with `8` and an `address_index` integer.

---

### 5. Database Migrations

Run Alembic migrations to create the database schema:

```bash
docker compose run --rm backend alembic upgrade head
```

Verify the schema:

```bash
# Check tables (should be 11 + alembic_version = 12)
docker exec ghostbill_postgres psql -U ghostbill -d ghostbill -c "\dt"

# Check enums (should be 4)
docker exec ghostbill_postgres psql -U ghostbill -d ghostbill \
  -c "SELECT t.typname, e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid ORDER BY t.typname, e.enumsortorder;"
```

**Expected enums:**
- `invoice_status` (7 values): pending, paid, expired, partially_paid, overpaid, late_paid, cancelled
- `payment_status` (3 values): detected, confirmed, orphaned
- `subscription_status` (4 values): active, paused, cancelled, expired
- `webhook_status` (3 values): pending, delivered, failed

---

### 6. Tor Hidden Services (Optional)

Tor Hidden Services allow clients to access GhostBill without revealing the server's IP address.

**Install Tor:**

```bash
apt install tor
systemctl enable tor
```

**Add hidden services to `/etc/tor/torrc`:**

```
# GhostBill API
HiddenServiceDir /var/lib/tor/ghostbill_api/
HiddenServicePort 80 127.0.0.1:8013

# GhostBill Dashboard
HiddenServiceDir /var/lib/tor/ghostbill_dashboard/
HiddenServicePort 80 127.0.0.1:3013
```

**Restart Tor:**

```bash
systemctl restart tor
```

**Get your .onion addresses:**

```bash
cat /var/lib/tor/ghostbill_api/hostname
cat /var/lib/tor/ghostbill_dashboard/hostname
```

These addresses are permanent and can be shared with merchants and users.

**Outgoing Tor proxy:** GhostBill routes all outgoing connections (webhooks, price feed) through `socks5h://127.0.0.1:9050` by default when Tor is available. This prevents your server's IP from leaking to merchant webhook endpoints.

---

## Verification

Run these checks after deployment to ensure everything is working:

```bash
# 1. All containers healthy
docker compose ps

# 2. Backend responds
curl -s http://127.0.0.1:8013/health | python3 -m json.tool

# 3. Frontend responds
curl -s http://127.0.0.1:3013 -o /dev/null -w "HTTP: %{http_code}\n"

# 4. Database schema
docker exec ghostbill_postgres psql -U ghostbill -d ghostbill -c "\dt" | wc -l

# 5. wallet-rpc connected
curl -s -u ghostbill:$WALLET_RPC_PASS --digest -X POST http://127.0.0.1:18083/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_height"}' | python3 -m json.tool

# 6. monerod synced
curl -s -u $MONEROD_USER:$MONEROD_PASS --digest -X POST http://127.0.0.1:31208/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' | python3 -c "
import sys,json
d=json.load(sys.stdin)['result']
print(f'Height: {d[\"height\"]}, Synced: {d.get(\"synchronized\",\"?\")}')"

# 7. Redis
redis-cli -p 6391 ping

# 8. Tor (if configured)
cat /var/lib/tor/ghostbill_api/hostname 2>/dev/null
cat /var/lib/tor/ghostbill_dashboard/hostname 2>/dev/null

# 9. Security headers
curl -sI http://127.0.0.1:8013/health | grep -iE "security|strict|x-frame|x-content|referrer|permission"

# 10. Register a test merchant
curl -X POST http://127.0.0.1:8013/v1/merchants \
  -H "Content-Type: application/json" \
  -d '{"primary_address": "YOUR_ADDRESS", "view_key": "YOUR_VIEW_KEY", "name": "Test"}'
```

---

## Backups

### What to back up

| Data | Location | Priority | Frequency |
|------|----------|----------|-----------|
| Wallet files | `/root/ghostbill/wallet-data/` | **CRITICAL** | After any wallet change |
| Wallet seed phrase | Offline (paper/metal) | **CRITICAL** | Once (at creation) |
| PostgreSQL database | Docker volume | High | Daily |
| `.env` file | `/root/ghostbill/.env` | High | After any change |
| Tor keys | `/var/lib/tor/ghostbill_*/` | Medium | Once (preserves .onion addresses) |

### PostgreSQL backup

```bash
# Dump
docker exec ghostbill_postgres pg_dump -U ghostbill ghostbill | gzip > ghostbill_backup_$(date +%Y%m%d).sql.gz

# Encrypt
gpg -c ghostbill_backup_$(date +%Y%m%d).sql.gz

# Upload to offsite storage
rsync -avz ghostbill_backup_*.sql.gz.gpg user@backup-server:/backups/ghostbill/
```

### Wallet backup

```bash
# Stop wallet-rpc first
docker compose stop walletrpc

# Copy wallet files
cp -r /root/ghostbill/wallet-data/ /root/ghostbill-wallet-backup-$(date +%Y%m%d)/

# Restart
docker compose up -d walletrpc
```

> ⚠️ **The wallet seed phrase is the ultimate backup.** If you have the seed, you can always restore the wallet. Store it on paper or metal in a physically secure location. Never store it digitally.

### Automated daily backup script

```bash
#!/bin/bash
# /root/ghostbill/scripts/backup.sh

BACKUP_DIR="/root/ghostbill-backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# PostgreSQL
docker exec ghostbill_postgres pg_dump -U ghostbill ghostbill \
  | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"

# Encrypt
gpg --batch --yes -c --passphrase-file /root/.backup-passphrase \
  "$BACKUP_DIR/db_$DATE.sql.gz"
rm "$BACKUP_DIR/db_$DATE.sql.gz"

# Clean old backups (keep 30 days)
find "$BACKUP_DIR" -name "db_*.sql.gz.gpg" -mtime +30 -delete

echo "Backup complete: $BACKUP_DIR/db_$DATE.sql.gz.gpg"
```

Add to cron:

```bash
crontab -e
# Add: 0 3 * * * /root/ghostbill/scripts/backup.sh >> /var/log/ghostbill-backup.log 2>&1
```

### Restore

```bash
# Decrypt
gpg -d ghostbill_backup_20260213.sql.gz.gpg > ghostbill_backup.sql.gz

# Decompress
gunzip ghostbill_backup.sql.gz

# Restore (stop backend first)
docker compose stop backend
docker exec -i ghostbill_postgres psql -U ghostbill -d ghostbill < ghostbill_backup.sql
docker compose up -d backend
```

---

## Monitoring

### Health check endpoint

```bash
# Simple ping
curl -s http://127.0.0.1:8013/health

# Full response
# {"status":"healthy","app":"GhostBill","version":"0.1.0"}
```

### Docker container health

```bash
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

All containers should show `(healthy)`.

### Blockchain sync status

```bash
# wallet-rpc height (should match monerod)
curl -s -u ghostbill:$PASS --digest -X POST http://127.0.0.1:18083/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_height"}' | python3 -c "
import sys,json; print(f'wallet-rpc height: {json.load(sys.stdin)[\"result\"][\"height\"]}')"
```

### Log monitoring

```bash
# Backend logs
docker logs ghostbill_backend --tail 50 -f

# wallet-rpc logs
docker logs ghostbill_walletrpc --tail 50 -f

# All services
docker compose logs --tail 20 -f
```

### Disk usage

```bash
# Docker volumes
docker system df

# Monero blockchain
du -sh /var/lib/monero/

# PostgreSQL
docker exec ghostbill_postgres psql -U ghostbill -d ghostbill \
  -c "SELECT pg_size_pretty(pg_database_size('ghostbill'));"
```

### Simple monitoring script

```bash
#!/bin/bash
# /root/ghostbill/scripts/monitor.sh

echo "=== GhostBill Status ==="
echo ""

# Backend health
HEALTH=$(curl -s http://127.0.0.1:8013/health 2>/dev/null)
if echo "$HEALTH" | grep -q "healthy"; then
    echo "Backend:    ✓ healthy"
else
    echo "Backend:    ✗ DOWN"
fi

# Frontend
HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3013 2>/dev/null)
if [ "$HTTP" = "200" ] || [ "$HTTP" = "307" ]; then
    echo "Frontend:   ✓ HTTP $HTTP"
else
    echo "Frontend:   ✗ HTTP $HTTP"
fi

# PostgreSQL
PG=$(docker exec ghostbill_postgres pg_isready -U ghostbill 2>/dev/null)
if echo "$PG" | grep -q "accepting"; then
    echo "PostgreSQL: ✓ accepting connections"
else
    echo "PostgreSQL: ✗ DOWN"
fi

# Redis
REDIS=$(redis-cli -p 6391 ping 2>/dev/null)
if [ "$REDIS" = "PONG" ]; then
    echo "Redis:      ✓ PONG"
else
    echo "Redis:      ✗ DOWN"
fi

# Disk
DISK_USED=$(df -h / | awk 'NR==2{print $5}')
echo ""
echo "Disk usage: $DISK_USED"
```

---

## Updating

```bash
cd /root/ghostbill

# Pull latest code
git pull origin main

# Rebuild containers
docker compose build

# Run any new migrations
docker compose run --rm backend alembic upgrade head

# Restart with new images
docker compose up -d

# Verify
curl -s http://127.0.0.1:8013/health
```

For major updates, always back up the database first:

```bash
docker exec ghostbill_postgres pg_dump -U ghostbill ghostbill | gzip > pre-update-backup.sql.gz
```

---

## Troubleshooting

### Backend won't start

```bash
docker logs ghostbill_backend --tail 50
```

Common causes:
- PostgreSQL not ready yet — wait for health check
- Missing `.env` variables — check all required vars are set
- Port conflict — check `ss -tlnp | grep 8013`

### wallet-rpc can't connect to monerod

```bash
# Check monerod is running
ss -tlnp | grep 31208

# Check wallet-rpc logs
docker logs ghostbill_walletrpc --tail 20

# Test connection manually
curl -s -u USER:PASS --digest -X POST http://127.0.0.1:31208/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' | python3 -m json.tool
```

### Backend can't reach wallet-rpc

If backend is in Docker and wallet-rpc is on host network:

```bash
# Check WALLET_RPC_HOST in .env (should be Docker gateway, e.g. 172.23.0.1)
grep WALLET_RPC_HOST .env

# Find Docker gateway IP
docker network inspect ghostbill_net | grep Gateway

# Check UFW allows Docker → host
ufw status | grep 18083
```

### Invoice creation fails

```bash
# Test wallet-rpc subaddress creation
curl -s -u ghostbill:$PASS --digest -X POST http://127.0.0.1:18083/json_rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"0","method":"create_address","params":{"account_index":0}}' \
  | python3 -m json.tool
```

### Tor hidden service not working

```bash
# Check Tor is running
systemctl status tor

# Check hidden service directories exist
ls -la /var/lib/tor/ghostbill_api/
ls -la /var/lib/tor/ghostbill_dashboard/

# Check torrc syntax
tor --verify-config

# Restart Tor
systemctl restart tor
```

### Database connection issues

```bash
# Check PostgreSQL is running
docker exec ghostbill_postgres pg_isready -U ghostbill

# Check connection from backend container
docker exec ghostbill_backend python3 -c "
import asyncpg, asyncio
async def test():
    conn = await asyncpg.connect('postgresql://ghostbill:PASS@postgres:5432/ghostbill')
    print(await conn.fetchval('SELECT 1'))
    await conn.close()
asyncio.run(test())"
```

### Performance issues

```bash
# Check resource usage
docker stats --no-stream

# Check PostgreSQL slow queries
docker exec ghostbill_postgres psql -U ghostbill -d ghostbill \
  -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query
      FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC LIMIT 5;"
```
