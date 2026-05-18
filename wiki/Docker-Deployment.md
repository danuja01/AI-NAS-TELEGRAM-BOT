# Docker Deployment Guide

Deploy the NAS Telegram AI Assistant using Docker for easier management and portability.

**Prefer bare metal installation?** See the [[Installation]] guide instead.

---

## Table of Contents

1. [Why Docker?](#why-docker)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Deployment Methods](#deployment-methods)
5. [Configuration](#configuration)
6. [Managing the Container](#managing-the-container)
7. [Volumes and Data](#volumes-and-data)
8. [Resource Limits](#resource-limits)
9. [Updating](#updating)
10. [Troubleshooting](#troubleshooting)

---

## Why Docker?

Benefits of Docker deployment:

- **Easy Setup**: No Python dependencies to install
- **Isolation**: Bot runs in its own environment
- **Portability**: Works on any system with Docker
- **Resource Control**: Set CPU and memory limits
- **Auto-Restart**: Container restarts automatically on failure
- **Clean Uninstall**: Remove everything with one command
- **Consistency**: Same environment in dev and production

---

## Prerequisites

### 1. Install Docker

#### Linux (Debian/Ubuntu)
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group
sudo usermod -aG docker $USER

# Logout and login again
newgrp docker

# Verify installation
docker --version
docker ps
```

#### Synology NAS
1. Open Package Center
2. Search for "Docker"
3. Click Install
4. Open Docker app

#### QNAP NAS
1. Open App Center
2. Search for "Container Station"
3. Click Install

### 2. Install Docker Compose

```bash
# Install docker-compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# Make it executable
sudo chmod +x /usr/local/bin/docker-compose

# Verify
docker-compose --version
```

### 3. Get API Credentials

Before deploying, obtain:
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Your Telegram User ID (from [@userinfobot](https://t.me/userinfobot))
- OpenAI API Key (from [platform.openai.com](https://platform.openai.com/api-keys))

See the [[API Setup|API-Setup]] guide for detailed instructions.

---

## Quick Start

The fastest way to get running:

```bash
# 1. Clone repository
git clone <your-repo-url>
cd nas-telegram-bot/BOT

# 2. Create and configure .env file
cp .env.example .env
nano .env  # Add your API keys and credentials

# 3. Create directories
mkdir -p data logs documents

# 4. Start the bot
docker-compose up -d

# 5. View logs
docker-compose logs -f

# 6. Test in Telegram
# Message your bot with /start
```

That's it! Your bot is now running.

---

## Deployment Methods

Choose your preferred deployment method:

### Method 1: Docker Compose (Recommended)

Best for most users, includes automatic restart and proper configuration.

```bash
# Start in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

**Configuration file**: `docker-compose.yml` (already included)

### Method 2: Helper Script

Use the included script for automated setup:

```bash
# Make script executable
chmod +x docker-run.sh

# Run it
./docker-run.sh

# The script will:
# - Check for .env file
# - Create necessary directories
# - Build the Docker image
# - Start the container
# - Show status
```

### Method 3: Manual Docker Commands

For advanced users or custom setups:

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
  -v "$(pwd)/documents:/app/documents" \
  -v "/var/run/docker.sock:/var/run/docker.sock" \
  nas-telegram-bot:latest

# View logs
docker logs -f nas-telegram-bot
```

---

## Configuration

### Environment Variables

All configuration is done via the `.env` file:

```env
# ===== REQUIRED =====
TELEGRAM_TOKEN=your_bot_token_here
OPENAI_API_KEY=sk-your_openai_key
ALLOWED_USER_IDS=123456789,987654321

# ===== AI MODELS =====
DEFAULT_MODEL=gpt-5.4-nano
THINKING_MODEL=o3-mini
FALLBACK_MODEL=gpt-4o-mini

# ===== OPTIONAL =====
# Internet Search
SERPER_API_KEY=your_serper_key
TAVILY_API_KEY=your_tavily_key

# Root Access
ROOT_PASSWORD=YourSecurePassword123!

# ===== PATHS (auto-configured in Docker) =====
DOCUMENT_PATH=/app/documents
ALLOWED_PATHS=/app/documents,/app/data
DATABASE_PATH=/app/data/bot.db
CHROMA_PATH=/app/data/chroma_db
```

See the [[Configuration Guide|Configuration-Guide]] for complete reference.

### Example .env Files

The repository includes example configurations:
- `.env.example` - General example with all options
- `.env.docker.example` - Docker-specific example

---

## Managing the Container

### Basic Commands

#### With Docker Compose

```bash
# Start the bot
docker-compose up -d

# Stop the bot
docker-compose stop

# Restart the bot
docker-compose restart

# View logs (follow mode)
docker-compose logs -f

# View last 100 lines
docker-compose logs --tail=100

# Stop and remove container
docker-compose down

# Stop and remove everything including volumes
docker-compose down -v
```

#### With Docker

```bash
# Start
docker start nas-telegram-bot

# Stop
docker stop nas-telegram-bot

# Restart
docker restart nas-telegram-bot

# Logs
docker logs -f nas-telegram-bot

# Last 100 lines
docker logs --tail=100 nas-telegram-bot

# Remove container
docker rm nas-telegram-bot

# Remove image
docker rmi nas-telegram-bot:latest
```

### Shell Access

Sometimes you need to access the container:

```bash
# Open bash shell inside container
docker exec -it nas-telegram-bot bash

# Run a command directly
docker exec nas-telegram-bot python -c "print('Hello')"

# Check Python version
docker exec nas-telegram-bot python --version

# With docker-compose
docker-compose exec nas-bot bash
```

### Health Check

The container includes health checks:

```bash
# Check container health
docker ps

# Detailed health status
docker inspect --format='{{json .State.Health}}' nas-telegram-bot | jq

# Health check script
docker exec nas-telegram-bot cat /proc/1/status
```

---

## Volumes and Data

### Volume Mounts

Three volumes are mounted from host to container:

#### 1. Data Volume (`./data` → `/app/data`)
**Purpose**: Persistent storage for databases

**Contains**:
- `bot.db` - SQLite database (conversations, commands, alerts)
- `chroma_db/` - Vector database for RAG

**Important**: This data persists even if you delete the container

```bash
# Backup data
tar -czf backup-data-$(date +%Y%m%d).tar.gz data/

# Restore
tar -xzf backup-data-20260518.tar.gz
```

#### 2. Logs Volume (`./logs` → `/app/logs`)
**Purpose**: Application logs

**Contains**:
- `bot.log` - Main application log (rotated automatically)

**View logs**:
```bash
# From host
tail -f logs/bot.log

# Or use docker logs
docker logs -f nas-telegram-bot
```

#### 3. Documents Volume (`./documents` → `/app/documents`)
**Purpose**: Your documents for RAG/AI Q&A

**Supported formats**: PDF, DOCX, TXT, MD

**Usage**:
```bash
# Add documents
cp ~/my-docs/*.pdf documents/

# After adding documents, re-index
# Message bot: /index
```

**Note**: Now read-write to support file uploads via `/uploadfile` command

#### 4. Docker Socket (`/var/run/docker.sock`)
**Purpose**: Docker management from bot

**Allows**: `/docker` commands to work

**Security note**: This grants container access to Docker daemon

---

## Resource Limits

### Default Limits (docker-compose.yml)

```yaml
resources:
  limits:
    cpus: '2.0'      # Max 2 CPU cores
    memory: 4G       # Max 4GB RAM
  reservations:
    cpus: '0.5'      # Reserve 0.5 cores
    memory: 1G       # Reserve 1GB RAM
```

### Adjusting Limits

Edit `docker-compose.yml` to change limits:

```yaml
resources:
  limits:
    cpus: '4.0'      # More CPU for faster processing
    memory: 8G       # More RAM for larger document collections
```

### Monitoring Resource Usage

```bash
# Real-time stats
docker stats nas-telegram-bot

# With docker-compose
docker-compose stats
```

---

## Updating

### Update to Latest Version

```bash
# Stop the bot
docker-compose down

# Pull latest code
git pull origin main

# Rebuild image (with no-cache for clean build)
docker-compose build --no-cache

# Start updated bot
docker-compose up -d

# Check logs
docker-compose logs -f
```

### Update Strategy

1. **Minor updates** (bug fixes):
   ```bash
   docker-compose pull && docker-compose up -d
   ```

2. **Major updates** (new features):
   ```bash
   git pull
   docker-compose build --no-cache
   docker-compose down
   docker-compose up -d
   ```

3. **Configuration changes**:
   ```bash
   # Edit .env
   nano .env
   
   # Restart to apply changes
   docker-compose restart
   ```

---

## Troubleshooting

### Bot Not Starting

#### Check Logs
```bash
# Docker compose logs
docker-compose logs

# Last 50 lines
docker-compose logs --tail=50

# Follow in real-time
docker-compose logs -f
```

#### Common Issues

**Missing .env file**
```bash
# Copy example and configure
cp .env.example .env
nano .env
```

**Invalid API keys**
- Verify `TELEGRAM_TOKEN` in `.env`
- Check `OPENAI_API_KEY` is correct
- Ensure no extra spaces or quotes

**Port conflicts**
- Bot doesn't expose ports by default
- Check if another bot instance is running

### Permission Errors

**Volume permission issues**
```bash
# Fix permissions on host
chmod -R 755 data logs documents

# Or run with specific user
docker run --user $(id -u):$(id -g) ...
```

**Docker socket permission**
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Logout and login
newgrp docker
```

### Out of Memory

**Increase memory limit**

Edit `docker-compose.yml`:
```yaml
resources:
  limits:
    memory: 8G  # Increase from 4G
```

**Monitor usage**:
```bash
docker stats nas-telegram-bot
```

### Database Locked

**Error**: `database is locked`

**Solution**:
```bash
# Stop container
docker-compose down

# Remove lock files
rm -f data/bot.db-shm data/bot.db-wal

# Restart
docker-compose up -d
```

### Docker Commands Not Working

**Error**: `Failed to connect to Docker: Not supported URL scheme http+docker`

**Cause**: Docker socket not mounted

**Solution**: Verify `docker-compose.yml` includes:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

### SMART Commands Not Working

**Error**: `smartctl not found`

**Cause**: `smartmontools` not installed in container

**Solution**: The latest Dockerfile includes smartmontools. Rebuild:
```bash
docker-compose build --no-cache
docker-compose up -d
```

### Telegram Conflict Error

**Error**: `terminated by other getUpdates request`

**Cause**: Another bot instance is running

**Solution**:
```bash
# Find all running instances
docker ps -a | grep telegram

# Stop all
docker stop nas-telegram-bot

# Or check local processes
ps aux | grep bot.py
kill <pid>
```

### Container Keeps Restarting

**Check why**:
```bash
# View exit code
docker inspect nas-telegram-bot --format='{{.State.ExitCode}}'

# View logs
docker logs --tail=50 nas-telegram-bot
```

**Common causes**:
- Invalid configuration in `.env`
- Missing API keys
- Database corruption
- Out of memory

---

## Production Deployment

### On Synology NAS

1. **Enable SSH** (Control Panel → Terminal & SNMP)
2. **Upload files** via File Station or SSH
3. **Configure .env**:
   ```env
   DOCUMENT_PATH=/volume1/documents
   ALLOWED_PATHS=/volume1/documents,/volume1/data
   ```
4. **Deploy**:
   ```bash
   cd /volume1/docker/nas-telegram-bot
   docker-compose up -d
   ```

### On QNAP NAS

1. Install Container Station
2. Create folder: `/share/Container/nas-telegram-bot`
3. Upload files
4. Configure `.env` with QNAP paths
5. Run via Container Station or CLI

### Security Best Practices

1. ✅ Use strong `ROOT_PASSWORD`
2. ✅ Limit `ALLOWED_USER_IDS` to trusted users
3. ✅ Keep API keys in `.env`, never commit
4. ✅ Use read-write mounts only where needed
5. ✅ Regularly update: `docker-compose pull && docker-compose up -d`
6. ✅ Monitor logs: `docker-compose logs -f`
7. ✅ Enable Docker socket only if needed
8. ✅ Set appropriate resource limits
9. ✅ Regular backups of `data/` directory
10. ✅ Review bot logs for suspicious activity

---

## Backup and Restore

### Backup

```bash
# Backup everything
tar -czf bot-backup-$(date +%Y%m%d).tar.gz data/ logs/ .env

# Backup just data
tar -czf data-backup-$(date +%Y%m%d).tar.gz data/

# Copy to safe location
cp bot-backup-*.tar.gz /path/to/backup/location/
```

### Restore

```bash
# Stop bot
docker-compose down

# Extract backup
tar -xzf bot-backup-20260518.tar.gz

# Start bot
docker-compose up -d
```

### Automated Backups

Create a cron job:

```bash
# Edit crontab
crontab -e

# Add daily backup at 3 AM
0 3 * * * cd /path/to/BOT && tar -czf backup-$(date +\%Y\%m\%d).tar.gz data/ && find . -name "backup-*.tar.gz" -mtime +7 -delete
```

---

## Next Steps

- Review the [[Configuration Guide|Configuration-Guide]] for all options
- Explore the [[Commands Reference|Commands-Reference]]
- Set up [[Security]] best practices
- Check [[Troubleshooting]] for more solutions

---

**Docker deployment complete!** Message your bot with `/start` to begin.
