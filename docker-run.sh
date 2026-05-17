#!/bin/bash
# Quick Docker run script for NAS Telegram Bot

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🐳 NAS Telegram AI Assistant - Docker Deployment${NC}\n"

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}❌ Error: .env file not found!${NC}"
    echo "Please create a .env file with your configuration."
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Docker is not running!${NC}"
    echo "Please start Docker and try again."
    exit 1
fi

# Create necessary directories
echo -e "${YELLOW}📁 Creating data directories...${NC}"
mkdir -p data logs documents

# Stop and remove existing container
echo -e "${YELLOW}🛑 Stopping existing container...${NC}"
docker stop nas-telegram-bot 2>/dev/null || true
docker rm nas-telegram-bot 2>/dev/null || true

# Build the image
echo -e "${YELLOW}🔨 Building Docker image...${NC}"
docker build -t nas-telegram-bot:latest .

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Build failed!${NC}"
    exit 1
fi

# Run the container
echo -e "${YELLOW}🚀 Starting bot container...${NC}"
docker run -d \
    --name nas-telegram-bot \
    --restart unless-stopped \
    --env-file .env \
    -v "$(pwd)/data:/app/data" \
    -v "$(pwd)/logs:/app/logs" \
    -v "$(pwd)/documents:/app/documents:ro" \
    nas-telegram-bot:latest

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Bot started successfully!${NC}\n"
    echo "View logs with: docker logs -f nas-telegram-bot"
    echo "Stop bot with: docker stop nas-telegram-bot"
    echo ""
    docker ps --filter "name=nas-telegram-bot" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
else
    echo -e "${RED}❌ Failed to start bot!${NC}"
    exit 1
fi
