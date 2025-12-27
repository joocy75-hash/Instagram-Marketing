#!/bin/bash
# ============================================
# Hetzner Server Initial Setup Script
# Server: deep-server (5.161.112.248)
# Group B: Instagram Marketing Service
# ============================================

set -e

echo "============================================"
echo "  Hetzner Server Initial Setup"
echo "  Group B: Instagram Marketing"
echo "============================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Please run as root${NC}"
  exit 1
fi

echo -e "\n${YELLOW}[1/7] System Update${NC}"
apt-get update && apt-get upgrade -y

echo -e "\n${YELLOW}[2/7] Install Docker${NC}"
if ! command -v docker &> /dev/null; then
  curl -fsSL https://get.docker.com -o get-docker.sh
  sh get-docker.sh
  rm get-docker.sh
  systemctl enable docker
  systemctl start docker
  echo -e "${GREEN}Docker installed successfully${NC}"
else
  echo -e "${GREEN}Docker already installed${NC}"
fi

echo -e "\n${YELLOW}[3/7] Install Docker Compose${NC}"
if ! command -v docker-compose &> /dev/null; then
  apt-get install -y docker-compose-plugin
  ln -sf /usr/libexec/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose || true
  echo -e "${GREEN}Docker Compose installed successfully${NC}"
else
  echo -e "${GREEN}Docker Compose already installed${NC}"
fi

echo -e "\n${YELLOW}[4/7] Setup 2GB Swap${NC}"
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo -e "${GREEN}2GB Swap created${NC}"
else
  echo -e "${GREEN}Swap already exists${NC}"
fi

echo -e "\n${YELLOW}[5/7] Configure Firewall (UFW)${NC}"
apt-get install -y ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 5000/tcp comment 'Instagram Marketing API'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
echo -e "${GREEN}Firewall configured${NC}"

echo -e "\n${YELLOW}[6/7] Install Fail2Ban${NC}"
apt-get install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban
echo -e "${GREEN}Fail2Ban installed${NC}"

echo -e "\n${YELLOW}[7/7] Create Directory Structure${NC}"
mkdir -p /root/service_a  # Freqtrade
mkdir -p /root/service_b/instagram-marketing/logs  # Instagram Marketing
mkdir -p /root/service_c  # AI Trading Platform

echo -e "${GREEN}Directory structure created:${NC}"
echo "  /root/service_a (Group A: Freqtrade)"
echo "  /root/service_b/instagram-marketing (Group B: Instagram Marketing)"
echo "  /root/service_c (Group C: AI Trading)"

# Set timezone
timedatectl set-timezone Asia/Seoul

echo -e "\n${GREEN}============================================${NC}"
echo -e "${GREEN}  Server Setup Complete!${NC}"
echo -e "${GREEN}============================================${NC}"

echo -e "\n${YELLOW}Next Steps:${NC}"
echo "1. Add your SSH public key to authorized_keys"
echo "2. Configure .env file at /root/service_b/instagram-marketing/.env"
echo "3. Push to GitHub main branch to trigger deployment"
echo ""
echo "Server IP: 5.161.112.248"
echo "API Port: 5000"
