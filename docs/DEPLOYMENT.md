# GhostBill Deployment

GhostBill is currently published as an audited release candidate.

For safety, this public repository documents the CI/test path first. Production deployment requires careful handling of wallet files, Monero node configuration, secrets, backups, and network exposure.

## Verify the release candidate

```bash
git clone https://github.com/gexiro-global/ghostbill.git
cd ghostbill
cp .env.test.example .env.test
./scripts/ci-test.sh
```

## Production notes

- Do not reuse CI secrets in production
- Generate all secrets on the target server (`openssl rand -hex 32`)
- Keep spend keys off the GhostBill server (view-only wallet only)
- Back up wallet recovery material offline
- Verify all network exposure before accepting real payments
- Configure Tor hidden services or reverse proxy as needed

Detailed production deployment documentation will be published after the release-candidate hardening pass.
