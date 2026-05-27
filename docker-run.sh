#!/bin/bash
# Production-style deploy: same secure defaults as docker-compose.yml.
# For full NAS host access (privileged, docker.sock, disk mount):
#   docker compose -f docker-compose.yml -f docker-compose.nas-host.yml up -d --build

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🐳 NAS Telegram AI Assistant — Docker Compose${NC}\n"

if [ ! -f .env ]; then
    echo -e "${RED}❌ Error: .env file not found!${NC}"
    echo "Copy .env.example and set TELEGRAM_TOKEN, OPENAI_API_KEY, ALLOWED_USER_IDS."
    exit 1
fi

if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Docker is not running!${NC}"
    exit 1
fi

echo -e "${YELLOW}📁 Ensuring data directories exist…${NC}"
mkdir -p data logs documents

COMPOSE_FILES=(-f docker-compose.yml)
if [ "${NAS_HOST_MODE:-}" = "1" ] || [ "${NAS_HOST_MODE:-}" = "true" ]; then
    echo -e "${YELLOW}⚙️  NAS host overlay enabled (docker-compose.nas-host.yml)${NC}"
    COMPOSE_FILES+=(-f docker-compose.nas-host.yml)
fi

echo -e "${YELLOW}🚀 Building and starting…${NC}"
docker compose "${COMPOSE_FILES[@]}" up -d --build

echo -e "${GREEN}✅ Bot started.${NC}"
echo "Logs: docker compose ${COMPOSE_FILES[*]} logs -f nas-bot"
echo "NAS host mode: NAS_HOST_MODE=1 ./docker-run.sh"
