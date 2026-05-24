**Official statement from the GhostBill maintainers**

Thanks for opening an issue. Please read this before sharing any sensitive information.

## Official channels

GhostBill is maintained only through:

- This GitHub repository: <https://github.com/gexiro-global/ghostbill>
- The official website: <https://ghostbill.org>

Any other channel claiming to represent GhostBill is **not** affiliated with the project. If someone contacts you outside these channels offering "support" or "help", treat it as a scam attempt.

## GhostBill maintainers will NEVER ask you to

- Share your Monero seed phrase or mnemonic
- Share your spend key (private key) — GhostBill is non-custodial; we never need it
- Send wallet files or wallet backups
- Share production secrets (`.env`, `MASTER_ENCRYPTION_KEY`, `SECRET_KEY`, API keys)
- Grant SSH or shell access to your server
- Share customer data, invoice contents, or webhook signing keys
- Send any Monero, fees, or deposits for support, "verification", "unlock", or any other reason
- Run commands or install software from a link sent by anyone claiming to be us outside of this repository

If anyone claiming to be a GhostBill maintainer asks you for any of the above, they are impersonating the project. Please close the conversation and report the account.

## What to include in your issue instead

- GhostBill version (`/health` endpoint output or `VERSION` file)
- Deployment mode (Docker Compose, Tor hidden service, clearnet reverse proxy)
- Steps to reproduce
- Relevant log lines with secrets and customer data **redacted**
- Expected vs actual behavior

Never paste `.env` contents, view keys, spend keys, wallet seeds, or anything that could deanonymize a payment.

## Security disclosures

For security issues that should not be public, please follow the disclosure process described in [SECURITY.md](../SECURITY.md) instead of opening a public issue.

— GhostBill maintainers
