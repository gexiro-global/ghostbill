# GhostBill — Beta Outreach Templates

Email and Matrix message templates for reaching target merchants during the beta launch phase.

---

## Target Merchants (Priority Order)

| # | Merchant | Status | Signal | Approach |
|---|----------|--------|--------|----------|
| 1 | IVPN | Temporarily disabled XMR (sync issues, 2026) | Direct pain point — their XMR is broken | "We solve the exact problem you have" |
| 2 | FlokiNET | Accepts XMR, privacy hosting | Natural fit, privacy-aligned | "Built for merchants like you" |
| 3 | OrangeWebsite | Accepts XMR, anonymous hosting | Privacy-first brand alignment | "Upgrade your XMR stack" |
| 4 | AirVPN | No XMR, community requests to add | Onboarding opportunity | "Your users are asking for this" |
| 5 | BuyVM | Limited XMR, hashrate concerns | Technical merchant, needs reliability | "Reliable Monero for technical teams" |

---

## Email Templates

### Template 1: IVPN (Pain Point — Disabled XMR)

**Subject:** Solving your Monero payment sync issues — open source, non-custodial

**Body:**

Hi IVPN team,

I noticed you temporarily disabled Monero payments due to sync issues. We've been building GhostBill — an open-source, non-custodial Monero payment processor — specifically to solve this problem.

**Why it's different:**
- Built for Monero from day one (not a Bitcoin plugin with XMR bolted on)
- Mempool detection — payments show up in seconds, not minutes
- 7 invoice states with automatic transitions (including partial/overpayment handling)
- Tor-native — .onion endpoints, outgoing proxy, zero IP logging

**Non-custodial:** GhostBill uses only your view key. Your spend key never touches our server. Even a full server compromise can't move funds.

**Open source:** AGPL-3.0, self-hostable, fully auditable.

We're running a private beta with 3–5 privacy-focused merchants. Would you be interested in testing it? Happy to do a technical walkthrough or just share the API docs.

API reference: [link]
GitHub: [link]

Best,
[name]
GhostBill

---

### Template 2: FlokiNET / OrangeWebsite (Privacy Alignment)

**Subject:** GhostBill — Monero billing built for privacy hosting

**Body:**

Hi [FlokiNET / OrangeWebsite] team,

We're building GhostBill — an open-source Monero payment processor designed for privacy-first businesses like yours.

**What makes it relevant for you:**
- Non-custodial (view key only — can't spend your funds)
- Tor-native (.onion API + dashboard, all outgoing traffic through Tor)
- No IP logging, no analytics, no tracking — anywhere in the stack
- HMAC-signed webhooks for reliable payment automation
- Self-hostable (Docker Compose, 5 containers, ~15 min setup)

We know you already accept Monero. GhostBill can improve your existing flow with real-time mempool detection, automatic invoice lifecycle management, and webhook-driven fulfillment.

We're inviting a handful of privacy hosting providers to our private beta. Interested in trying it out?

API docs: [link]
Self-host guide: [link]

Best,
[name]

---

### Template 3: AirVPN (Onboarding — No XMR Yet)

**Subject:** Your users want Monero — GhostBill makes it easy

**Body:**

Hi AirVPN team,

We've seen multiple community requests for Monero payment support on your platform. We built GhostBill to make adding XMR as straightforward as possible.

**For your dev team:**
- REST API with 21 endpoints — create an invoice in 1 HTTP call
- Webhook automation — get notified on payment, confirmation, expiry
- Unique subaddress per invoice — no address reuse
- Python and JS verification examples included

**For your users:**
- Pay with Monero directly (no intermediary, no custodian)
- Works with any Monero wallet (Cake Wallet, Feather, CLI)

**For your ops team:**
- Self-hosted (Docker Compose, your server, your control)
- Non-custodial (view key only — can't move funds)
- Open source (AGPL-3.0, fully auditable)

We're running a private beta. Would your team be interested in a quick integration test?

Quick start: [link]
API reference: [link]

Best,
[name]

---

### Template 4: BuyVM (Technical Reliability)

**Subject:** Reliable Monero payments for hosting — GhostBill (open source)

**Body:**

Hi BuyVM team,

We know you've had concerns about Monero payment reliability, particularly around hashrate attacks and confirmation issues. GhostBill is built to handle these edge cases properly.

**Reliability features:**
- Mempool detection with confirmation tracking (configurable threshold, default 10)
- Blockchain reorg handling — payments automatically marked as orphaned if they disappear
- 7 invoice states: partial payment, overpayment, and late payment are all handled automatically
- Webhook retries: 7 attempts over 38 hours with HMAC signatures

**Security:**
- Non-custodial (view key only)
- AES-256-GCM encrypted keys at rest
- Rate limiting, audit logging, timing jitter
- Self-hosted — runs on your infrastructure

Open source (AGPL-3.0), Docker Compose setup, full API docs.

Interested in testing? Happy to walk through the architecture.

Best,
[name]

---

## Matrix Message Templates

### Matrix — Monero Community Rooms

**For:** #monero, #monero-community, #monero-merchants

```
🔔 Introducing GhostBill — open source Monero payment processor

We've been building a non-custodial, Tor-native billing system for Monero merchants. Now in private beta.

What it does:
• View-key only (can't spend your funds)
• Real-time mempool detection
• 8 webhook events with HMAC signatures
• 7 invoice states (partial, overpaid, late handled automatically)
• .onion API + dashboard
• Self-hosted (Docker Compose, AGPL-3.0)

Looking for 3–5 merchants to test during beta. If you run a business that accepts (or wants to accept) XMR, we'd love your feedback.

GitHub: [link]
API docs: [link]
Self-host guide: [link]

Happy to answer questions here or via DM.
```

### Matrix — Privacy Community Rooms

**For:** #privacy, #tor, #cypherpunk-related rooms

```
For those running privacy-focused services that accept Monero:

GhostBill is a new open-source (AGPL-3.0) payment processor built specifically for XMR. Non-custodial, Tor-native, no IP logging, no analytics.

Key difference from BTCPay: GhostBill is Monero-first, not a Bitcoin processor with an XMR plugin. Mempool detection, 7 invoice states, HMAC webhooks, timing jitter.

Self-hosted with Docker Compose. 5 containers, ~15 min to set up.

Private beta — looking for feedback from merchants.
GitHub: [link]
```

---

## Reddit Post Templates

### r/Monero — Launch Post

**Title:** GhostBill — open source, non-custodial Monero payment processor [beta]

**Body:**

We've been building GhostBill for the past few months and it's now in private beta. It's an open-source (AGPL-3.0) payment processor built from scratch for Monero.

**Why we built it:**
- BTCPay's Monero plugin has reliability issues (sync problems, limited states)
- MoneroPay and AcceptXMR are libraries, not full billing platforms
- CoinPayments and similar services are custodial
- No existing solution offers Tor-native architecture with webhook automation

**What GhostBill does:**
- Non-custodial: view key only, spend key never on server
- Real-time mempool detection (pool: true)
- 7 invoice states with automatic transitions
- 8 webhook events with HMAC-SHA256 signatures and 7 retries
- Tor hidden services for API + dashboard
- All outgoing connections through Tor
- Monero signature authentication (passwordless dashboard login)
- Self-hosted: Docker Compose, 5 containers
- 21 API endpoints, full CLI tool
- 60/60 tests passing

**Stack:** FastAPI + PostgreSQL + Redis + monero-wallet-rpc + Next.js

Looking for feedback from merchants and developers. Self-host guide and API docs are on GitHub.

[GitHub link]

Happy to answer any questions.

---

## Follow-Up Template (7 days after initial contact)

**Subject:** Re: GhostBill — following up

**Body:**

Hi [name],

Just following up on my message about GhostBill. We've continued testing and all 60 tests are passing consistently.

If it would be helpful, I'm happy to:
- Share a live demo (API + dashboard)
- Walk through the self-hosting setup (takes ~15 min)
- Answer technical questions about the architecture

No pressure either way — just wanted to make sure it didn't get lost in the inbox.

Best,
[name]

---

## Notes

**Tone:** Technical, direct, no marketing fluff. These are technical teams — they respect specifics.

**Timing:** Send initial outreach Tuesday–Thursday, 10:00–14:00 UTC.

**Follow-up:** Once after 7 days. If no response, respect it — don't spam.

**Tracking:** Log all outreach in a simple spreadsheet: merchant, date sent, channel, response, status.
