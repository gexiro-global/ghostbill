#!/bin/bash
set -euo pipefail

# GhostBill Server Hardening Script
# Run once on VPS. Review each section before executing.
# Usage: bash server-hardening.sh

echo "=== GhostBill Server Hardening ==="

# ─── 1. SSH Hardening ────────────────────────────────────────────────────────

echo "[1/6] SSH hardening..."

# Disable password authentication (key-only)
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/^#\?MaxAuthTries.*/MaxAuthTries 3/' /etc/ssh/sshd_config
sed -i 's/^#\?X11Forwarding.*/X11Forwarding no/' /etc/ssh/sshd_config
sed -i 's/^#\?AllowAgentForwarding.*/AllowAgentForwarding no/' /etc/ssh/sshd_config

systemctl restart sshd
echo "  SSH: key-only auth, root via key only, max 3 attempts"

# ─── 2. UFW Firewall ─────────────────────────────────────────────────────────

echo "[2/6] UFW firewall..."

# Get current SSH port from sshd_config
SSH_PORT=$(grep -E "^Port " /etc/ssh/sshd_config | awk '{print $2}' || echo "22")
if [ -z "$SSH_PORT" ]; then
    SSH_PORT="22"
fi

ufw default deny incoming
ufw default allow outgoing

# Allow SSH on current port
ufw allow "${SSH_PORT}/tcp" comment 'SSH'

# Ports 8013, 3013 are NOT opened externally
# Access is via Tor hidden services only (Phase 3B)

# Allow Tor directory (needed for hidden services)
# ufw allow 9001/tcp comment 'Tor OR port'  # Only if running Tor relay

echo "y" | ufw enable
echo "  UFW: default deny, SSH on port ${SSH_PORT}"

# ─── 3. Fail2Ban ─────────────────────────────────────────────────────────────

echo "[3/6] Fail2Ban..."

apt-get install -y fail2ban -qq

cat > /etc/fail2ban/jail.local << 'JAILEOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
backend = systemd

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
JAILEOF

systemctl enable fail2ban
systemctl restart fail2ban
echo "  Fail2Ban: 3 attempts, 1h ban, 10min window"

# ─── 4. Automatic Security Updates ───────────────────────────────────────────

echo "[4/6] Unattended upgrades..."

apt-get install -y unattended-upgrades -qq
dpkg-reconfigure -plow unattended-upgrades

echo "  Unattended upgrades enabled"

# ─── 5. Wallet File Permissions ──────────────────────────────────────────────

echo "[5/6] Wallet permissions..."

WALLET_DIR="/root/ghostbill/wallet-data"
if [ -d "$WALLET_DIR" ]; then
    chmod 700 "$WALLET_DIR"
    chown -R root:root "$WALLET_DIR"
    # Restrict individual wallet files
    find "$WALLET_DIR" -type f -exec chmod 600 {} \;
    echo "  Wallet dir: 700, files: 600, owner: root"
else
    echo "  WARNING: $WALLET_DIR not found, skipping"
fi

# ─── 6. Kernel Hardening (sysctl) ────────────────────────────────────────────

echo "[6/6] Kernel hardening..."

cat > /etc/sysctl.d/99-ghostbill-hardening.conf << 'SYSEOF'
# Disable IP forwarding (not a router)
net.ipv4.ip_forward = 0
net.ipv6.conf.all.forwarding = 0

# Ignore ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0

# Ignore source-routed packets
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0

# Enable SYN flood protection
net.ipv4.tcp_syncookies = 1

# Log suspicious packets
net.ipv4.conf.all.log_martians = 1

# Disable ICMP broadcast responses
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Restrict dmesg access
kernel.dmesg_restrict = 1

# Restrict kernel pointer exposure
kernel.kptr_restrict = 2
SYSEOF

sysctl --system > /dev/null 2>&1
echo "  Kernel params hardened"

# ─── Summary ─────────────────────────────────────────────────────────────────

echo ""
echo "=== Server Hardening Complete ==="
echo ""
echo "Checklist:"
echo "  [x] SSH: key-only, max 3 attempts"
echo "  [x] UFW: default deny, SSH on port ${SSH_PORT}"
echo "  [x] Fail2Ban: 3 attempts -> 1h ban"
echo "  [x] Unattended security upgrades"
echo "  [x] Wallet files: restricted permissions"
echo "  [x] Kernel: hardened sysctl params"
echo ""
echo "VERIFY:"
echo "  ufw status verbose"
echo "  fail2ban-client status sshd"
echo "  sshd -T | grep -E 'passwordauth|pubkeyauth|permitroot'"
echo ""
echo "WARNING: Make sure your SSH key is working before disconnecting!"
