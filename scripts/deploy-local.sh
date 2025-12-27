#!/bin/bash
# ============================================
# Local Manual Deploy Script
# Use this for manual deployment without CI/CD
# ============================================

set -e

SERVER_IP="5.161.112.248"
DEPLOY_PATH="/root/service_b/instagram-marketing"

echo "============================================"
echo "  Manual Deploy to Hetzner Server"
echo "  Target: ${SERVER_IP}"
echo "============================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "\n${YELLOW}[1/5] Building Docker image...${NC}"
cd "$PROJECT_DIR"
docker build -t instagram-marketing:latest .

echo -e "\n${YELLOW}[2/5] Saving Docker image...${NC}"
docker save instagram-marketing:latest | gzip > /tmp/image.tar.gz

echo -e "\n${YELLOW}[3/5] Uploading to server...${NC}"
scp /tmp/image.tar.gz "root@${SERVER_IP}:${DEPLOY_PATH}/"
scp docker-compose.yml "root@${SERVER_IP}:${DEPLOY_PATH}/"
scp .env.example "root@${SERVER_IP}:${DEPLOY_PATH}/"

echo -e "\n${YELLOW}[4/5] Deploying on server...${NC}"
ssh "root@${SERVER_IP}" "
  cd ${DEPLOY_PATH}

  # Load image
  gunzip -c image.tar.gz | docker load
  rm image.tar.gz

  # Create .env if not exists
  if [ ! -f .env ]; then
    cp .env.example .env
    echo 'Created .env - Please configure it!'
  fi

  # Deploy
  docker-compose down || true
  docker-compose up -d

  # Cleanup
  docker image prune -f

  # Status
  docker-compose ps
"

echo -e "\n${YELLOW}[5/5] Health check...${NC}"
sleep 5
ssh "root@${SERVER_IP}" "curl -s http://localhost:5000/health"

# Cleanup local
rm -f /tmp/image.tar.gz

echo -e "\n${GREEN}============================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "API URL: http://${SERVER_IP}:5000"
echo "Health: http://${SERVER_IP}:5000/health"
