# Docker Deployment Guide

## Quick Start

### Option 1: Using docker-compose (Recommended)

```bash
# 1. Make sure .env is configured
cp .env.example .env
# Edit .env with your actual values

# 2. Create directories
mkdir -p data logs documents

# 3. Start the bot
docker-compose up -d

# 4. View logs
docker-compose logs -f

# 5. Stop the bot
docker-compose down
```

### Option 2: Using the helper script

```bash
# 1. Configure .env file
cp .env.example .env
# Edit .env with your values

# 2. Run the script
./docker-run.sh

# This will:
# - Build the Docker image
# - Create necessary directories
# - Start the container
# - Show status
```

### Option 3: Manual Docker commands

```bash
# Build the image
docker build -t nas-telegram-bot:latest .

# Run the container
docker run -d \
  --name nas-telegram-bot \
  --restart unless-stopped \
  --env-file .env \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/logs:/app/logs" \
  -v "$(pwd)/documents:/app/documents:ro" \
  nas-telegram-bot:latest
```

## Directory Structure

```
BOT/
├── Dockerfile              # Docker image definition
├── docker-compose.yml      # Docker Compose configuration
├── docker-run.sh          # Helper script for deployment
├── .dockerignore          # Files to exclude from build
├── data/                  # Persistent data (mounted volume)
│   ├── bot.db            # SQLite database
│   └── chroma_db/        # Vector database
├── logs/                  # Application logs (mounted volume)
│   └── bot.log
└── documents/             # Your documents for RAG (mounted volume)
```

## Environment Variables

All configuration is done via `.env` file or environment variables:

```env
# Required
TELEGRAM_TOKEN=your_token_here
OPENAI_API_KEY=your_key_here
ALLOWED_USER_IDS=123456789

# AI Models
DEFAULT_MODEL=gpt-5.4-nano
THINKING_MODEL=o3
FALLBACK_MODEL=gpt-5.4-mini

# Optional: Internet Search
SERPER_API_KEY=
TAVILY_API_KEY=your_key_here

# Optional: Root Access
ROOT_PASSWORD=your_secure_password

# Paths (automatically configured in Docker)
DOCUMENT_PATH=/app/documents
ALLOWED_PATHS=/app/documents,/app/data
DATABASE_PATH=/app/data/bot.db
CHROMA_PATH=/app/data/chroma_db
```

## Common Docker Commands

### View logs
```bash
# Follow logs in real-time
docker logs -f nas-telegram-bot

# View last 100 lines
docker logs --tail 100 nas-telegram-bot

# With docker-compose
docker-compose logs -f
```

### Stop/Start/Restart
```bash
# Stop
docker stop nas-telegram-bot

# Start
docker start nas-telegram-bot

# Restart
docker restart nas-telegram-bot

# With docker-compose
docker-compose stop
docker-compose start
docker-compose restart
```

### Update the bot
```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Or with docker-run.sh
./docker-run.sh
```

### Shell access (for debugging)
```bash
# Enter container shell
docker exec -it nas-telegram-bot bash

# Run Python commands
docker exec -it nas-telegram-bot python -c "print('Hello')"

# With docker-compose
docker-compose exec nas-bot bash
```

### Clean up
```bash
# Remove container
docker stop nas-telegram-bot
docker rm nas-telegram-bot

# Remove image
docker rmi nas-telegram-bot:latest

# With docker-compose (removes containers)
docker-compose down

# Remove everything including volumes
docker-compose down -v
```

## Volume Mounts

Three important volumes are mounted:

1. **`./data` → `/app/data`**
   - SQLite database
   - ChromaDB vector store
   - Persistent across container restarts

2. **`./logs` → `/app/logs`**
   - Application logs
   - Easy to access from host

3. **`./documents` → `/app/documents`** (read-only)
   - Your documents for RAG
   - Place PDFs, DOCX, etc. here
   - Run `/index` command to index them

## Resource Limits

The `docker-compose.yml` includes resource limits:
- **CPU**: Max 2 cores, Reserved 0.5 cores
- **Memory**: Max 4GB, Reserved 1GB

Adjust these in `docker-compose.yml` based on your system.

## Health Checks

The Dockerfile includes a health check that verifies the database file exists.

Check container health:
```bash
docker ps
# Look for "healthy" in STATUS column

# Detailed health status
docker inspect --format='{{json .State.Health}}' nas-telegram-bot | jq
```

## Troubleshooting

### Bot not starting
```bash
# Check logs
docker logs nas-telegram-bot

# Common issues:
# 1. Missing .env file
# 2. Invalid API keys
# 3. Permission issues with volumes
```

### Permission errors
```bash
# Fix permissions on host
chmod -R 755 data logs documents

# Or run container with specific user
docker run --user $(id -u):$(id -g) ...
```

### Out of memory
```bash
# Increase memory limit in docker-compose.yml
# Or check system resources
docker stats nas-telegram-bot
```

### Database locked
```bash
# Stop container
docker-compose down

# Remove database lock files
rm -f data/bot.db-shm data/bot.db-wal

# Restart
docker-compose up -d
```

## Production Deployment

### On your NAS:

1. **Enable Docker** in your NAS interface
2. **Upload files** via SSH or web interface
3. **Configure .env** with production values
4. **Update paths** in `.env`:
   ```env
   DOCUMENT_PATH=/volume1/documents
   ALLOWED_PATHS=/volume1/documents,/volume1/data
   ```
5. **Deploy**:
   ```bash
   docker-compose up -d
   ```

### Security Best Practices:

1. ✅ Use strong `ROOT_PASSWORD`
2. ✅ Limit `ALLOWED_USER_IDS` to trusted users only
3. ✅ Keep API keys in `.env`, never commit to git
4. ✅ Use read-only mounts for documents (`:ro`)
5. ✅ Regularly update the image: `docker-compose pull && docker-compose up -d`
6. ✅ Monitor logs: `docker-compose logs -f`

## Monitoring

### Check bot status
```bash
# Container status
docker ps | grep nas-telegram-bot

# Resource usage
docker stats nas-telegram-bot

# Disk usage
docker system df
```

### Log rotation
Logs are automatically rotated (max 10MB per file, 3 files kept) as configured in `docker-compose.yml`.

## Backup

```bash
# Backup data
tar -czf backup-$(date +%Y%m%d).tar.gz data/

# Backup logs
tar -czf logs-$(date +%Y%m%d).tar.gz logs/

# Restore
tar -xzf backup-20260517.tar.gz
```

## Support

If you encounter issues:
1. Check logs: `docker logs nas-telegram-bot`
2. Verify .env configuration
3. Ensure Docker is running
4. Check system resources
5. Review this guide for common solutions
