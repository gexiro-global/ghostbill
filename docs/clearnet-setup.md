# Clearnet Deployment Guide

> **Default deployment is Tor-only.** This guide is for merchants who choose
> to expose their GhostBill instance on the clearnet (public internet).

## Privacy Warning

Running GhostBill on clearnet means a reverse proxy (e.g., Cloudflare) will
process your traffic metadata, including merchant IP address, API key timing,
invoice creation patterns, and customer access times. **For maximum privacy,
use Tor-only deployment.** Clearnet is a convenience option — the decision
and its privacy trade-offs are yours.

## Prerequisites

- GhostBill running (5 containers healthy via `docker compose ps`)
- A domain name with DNS you control
- A reverse proxy / CDN (Cloudflare recommended for DDoS protection)
- SSL certificate (Cloudflare Origin CA or Let's Encrypt)

## Architecture

```
Browser → Cloudflare (DDoS + TLS termination)
       → nginx (your server, ports 80/443)
          ├── yourdomain.com          → static landing / pay page
          ├── api.yourdomain.com      → FastAPI backend (:8000)
          └── dashboard.yourdomain.com → Next.js frontend (:3000)

Tor hidden services remain unchanged and independent.
```

## Step 1: SSL Certificate

### Option A: Cloudflare Origin CA (recommended with Cloudflare)

1. Cloudflare Dashboard → SSL/TLS → Origin Server → Create Certificate
2. Key type: RSA 2048, Hostnames: `yourdomain.com`, `*.yourdomain.com`
3. Save certificate as `origin.crt` and private key as `origin.key`
4. Set SSL mode to **Full (Strict)**

### Option B: Let's Encrypt (without Cloudflare)

```bash
apt install certbot
certbot certonly --standalone -d yourdomain.com -d api.yourdomain.com -d dashboard.yourdomain.com
```

## Step 2: DNS Records

Create A/AAAA records pointing to your server:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `@` | your.server.ip | ON (if using Cloudflare) |
| A | `api` | your.server.ip | ON |
| A | `dashboard` | your.server.ip | ON |

**Important:** Enable proxy (orange cloud) to hide your server IP.

## Step 3: Nginx Configuration

Copy the example config and customize:

```bash
mkdir -p nginx/certs nginx/conf
# Place your SSL certs in nginx/certs/
cp configs/nginx-clearnet-example.conf nginx/conf/ghostbill.conf
```

Edit `nginx/conf/ghostbill.conf`:
- Replace `yourdomain.com` with your actual domain
- Update Cloudflare IP ranges in the `geo` block (check https://www.cloudflare.com/ips/)
- Adjust rate limits as needed

## Step 4: Start Clearnet Services

Use the clearnet override file:

```bash
docker compose -f docker-compose.yml -f docker-compose.clearnet.yml up -d
```

This adds an nginx container to your existing stack without modifying
the base `docker-compose.yml`.

Verify:

```bash
docker compose -f docker-compose.yml -f docker-compose.clearnet.yml ps
```

Expected: 6 containers (5 existing + nginx), all healthy.

## Step 5: Firewall

Restrict ports 80/443 to Cloudflare IPs only:

```bash
# Download current Cloudflare IP ranges
curl -s https://www.cloudflare.com/ips-v4 > /tmp/cf-ipv4.txt
curl -s https://www.cloudflare.com/ips-v6 > /tmp/cf-ipv6.txt

# Add UFW rules
while IFS= read -r ip; do
  ufw allow from "$ip" to any port 80,443 proto tcp comment "Cloudflare"
done < /tmp/cf-ipv4.txt

while IFS= read -r ip; do
  ufw allow from "$ip" to any port 80,443 proto tcp comment "Cloudflare"
done < /tmp/cf-ipv6.txt
```

Verify direct IP access is blocked:

```bash
curl -s --connect-timeout 5 http://your.server.ip/ || echo "BLOCKED (correct)"
```

## Step 6: CORS Update

Add your clearnet domains to the CORS config in `backend/app/main.py`:

```python
origins = [
    # Existing Tor origins...
    "https://dashboard.yourdomain.com",
    "https://yourdomain.com",
]
```

Rebuild backend:

```bash
docker compose -f docker-compose.yml -f docker-compose.clearnet.yml up -d --build backend
```

## Step 7: Verify

```bash
# Landing page
curl -sI https://yourdomain.com | head -5

# API health
curl -s https://api.yourdomain.com/health | python3 -m json.tool

# Dashboard
curl -sI https://dashboard.yourdomain.com | head -5

# Tor still works
curl -x socks5h://127.0.0.1:9050 http://YOUR_ONION_ADDRESS/health

# Security headers
curl -sI https://api.yourdomain.com/health | grep -iE 'x-frame|strict-transport|x-content-type'

# Direct IP blocked
curl -s --connect-timeout 5 https://your.server.ip/ || echo "BLOCKED"
```

## Stopping Clearnet

To disable clearnet without affecting Tor:

```bash
docker compose -f docker-compose.yml -f docker-compose.clearnet.yml stop nginx
```

Or revert to Tor-only:

```bash
docker compose down
docker compose up -d  # base only, no clearnet override
```

## Cloudflare Recommended Settings

| Setting | Value |
|---------|-------|
| SSL mode | Full (Strict) |
| Always Use HTTPS | ON |
| Minimum TLS | 1.2 |
| HSTS | ON (6 months, include subdomains) |
| Bot Fight Mode | ON |
| Cache: api subdomain | Bypass |
| Cache: dashboard | Bypass |
| Cache: landing | 1 hour |

## Security Notes

- Nginx config drops connections from non-Cloudflare IPs (return 444)
- All API responses include security headers (HSTS, X-Frame-Options DENY, no-referrer)
- `access_log off` on API subdomain for privacy
- Rate limiting at nginx level (30r/s API, 10r/s general)
- Tor services are completely independent and unaffected by clearnet config
