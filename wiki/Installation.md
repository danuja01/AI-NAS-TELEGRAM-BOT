# Installation Guide

Complete step-by-step guide for installing the NAS Telegram AI Assistant on bare metal (without Docker).

**Prefer Docker?** See the [[Docker Deployment|Docker-Deployment]] guide instead.

---

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Prerequisites](#prerequisites)
3. [Installation Steps](#installation-steps)
4. [Configuration](#configuration)
5. [First Run](#first-run)
6. [Permissions Setup](#permissions-setup)
7. [Running as a Service](#running-as-a-service)
8. [Common Issues](#common-issues)

---

## System Requirements

### Minimum Requirements
- **OS**: Linux (Debian 10+, Ubuntu 20.04+, or compatible)
- **Python**: 3.11 or higher
- **RAM**: 2GB minimum (4GB recommended)
- **Disk**: 10GB free space (20GB+ recommended for documents)
- **Network**: Internet connection for API access

### Tested On
- Ubuntu 22.04 LTS
- Debian 12 (Bookworm)
- Synology DSM 7.x
- QNAP QTS 5.x
- macOS 13+ (for testing only)

---

## Prerequisites

### 1. System Packages

Install required system packages:

```bash
# Debian/Ubuntu
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git smartmontools

# Verify Python version (should be 3.11+)
python3 --version
```

### 2. API Credentials

You'll need these before starting:

1. **Telegram Bot Token**
   - Open Telegram and message [@BotFather](https://t.me/BotFather)
   - Send `/newbot` and follow the prompts
   - Save the bot token (format: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

2. **Your Telegram User ID**
   - Message [@userinfobot](https://t.me/userinfobot)
   - It will reply with your user ID (format: `123456789`)
   - Save this number

3. **OpenAI API Key**
   - Go to [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
   - Create an account or sign in
   - Click "Create new secret key"
   - Save the key (starts with `sk-`)

4. **Optional: Web Search API Keys**
   - **Serper**: Sign up at [serper.dev](https://serper.dev) (2,500 free searches/month)
   - **Tavily**: Sign up at [tavily.com](https://tavily.com) (1,000 free searches/month)

---

## Installation Steps

### Step 1: Clone the Repository

```bash
# Navigate to your preferred directory
cd /opt  # or ~/apps or any directory you prefer

# Clone the repository
git clone <your-repo-url> nas-telegram-bot
cd nas-telegram-bot/BOT

# Or if you downloaded a ZIP file
unzip nas-telegram-bot.zip
cd nas-telegram-bot/BOT
```

### Step 2: Create Virtual Environment

Creating a virtual environment isolates the bot's dependencies:

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Your prompt should now show (venv) at the beginning
```

> **Note**: You'll need to activate this environment every time you run the bot or install packages.

### Step 3: Install Python Dependencies

```bash
# Make sure venv is activated (you should see (venv) in your prompt)
pip install --upgrade pip

# Install all required packages
pip install -r requirements.txt

# This will take a few minutes and install:
# - python-telegram-bot, openai, chromadb
# - langchain, sentence-transformers
# - psutil, docker, aiosqlite
# - And many more dependencies
```

### Step 4: Create Data Directories

```bash
# Create directories for data storage
mkdir -p data logs data/chroma_db documents

# Set permissions
chmod 755 data logs documents
```

**Directory Structure**:
- `data/` - SQLite database and ChromaDB vector store
- `logs/` - Application logs
- `documents/` - Place your documents here for RAG/AI Q&A

---

## Configuration

### Step 1: Create Environment File

```bash
# Copy the example configuration
cp .env.example .env

# Edit the file with your preferred editor
nano .env  # or vim, code, etc.
```

### Step 2: Configure Required Settings

Edit `.env` and set these **required** values:

```env
# Telegram Configuration (REQUIRED)
TELEGRAM_TOKEN=your_bot_token_from_botfather
ALLOWED_USER_IDS=your_user_id_from_userinfobot

# OpenAI API (REQUIRED)
OPENAI_API_KEY=sk-your_openai_api_key

# Document Path (REQUIRED)
DOCUMENT_PATH=/opt/nas-telegram-bot/BOT/documents
ALLOWED_PATHS=/opt/nas-telegram-bot/BOT/documents

# Root Access Password (REQUIRED for /ssh commands)
ROOT_PASSWORD=YourSecurePasswordHere123!
```

> **Security Warning**: Choose a strong `ROOT_PASSWORD` as this grants full system access!

### Step 3: Configure Optional Settings

Add these for enhanced features:

```env
# AI Models (default values work well)
DEFAULT_MODEL=gpt-5.4-nano
THINKING_MODEL=o3-mini
FALLBACK_MODEL=gpt-4o-mini

# Internet Search (optional but recommended)
SERPER_API_KEY=your_serper_key_here
TAVILY_API_KEY=your_tavily_key_here

# Database Paths (usually don't need to change these)
DATABASE_PATH=data/bot.db
CHROMA_PATH=data/chroma_db

# Logging
LOG_LEVEL=INFO
```

### Step 4: Add Your Documents

Place documents you want to query in the `documents/` folder:

```bash
# Example: Copy your files
cp ~/my-documents/*.pdf documents/
cp ~/my-notes/*.md documents/

# Supported formats: PDF, DOCX, TXT, MD
```

---

## First Run

### Test the Bot

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Run the bot
python bot.py
```

You should see output like:
```
2026-05-18 09:00:00 - INFO - NAS Telegram AI Assistant starting...
2026-05-18 09:00:01 - INFO - Bot started successfully
2026-05-18 09:00:01 - INFO - Authorized users: [123456789]
```

### First Commands

1. Open Telegram and find your bot
2. Send `/start` - You should get a welcome message
3. Send `/help` - See all available commands
4. Send `/status` - Check system status
5. Send `/index` - Index your documents (takes a few minutes)

If everything works, press `Ctrl+C` to stop the bot and continue with permissions setup.

---

## Permissions Setup

### Docker Access (for Docker Management)

If you want to manage Docker containers:

```bash
# Add your user to the docker group
sudo usermod -aG docker $USER

# Logout and login again for changes to take effect
# Or run:
newgrp docker

# Test Docker access
docker ps
```

### SMART Monitoring (for Drive Health)

If you want SMART drive health monitoring:

#### Option 1: Passwordless sudo (Recommended)

```bash
# Edit sudoers file
sudo visudo

# Add this line (replace 'yourusername' with your actual username):
yourusername ALL=(ALL) NOPASSWD: /usr/sbin/smartctl
```

#### Option 2: Run bot as root (Not Recommended)

```bash
# Only use this if you understand the security implications
sudo python bot.py
```

### Service Management (for /reboot, /shutdown)

```bash
# Allow passwordless sudo for shutdown/reboot
sudo visudo

# Add these lines (replace 'yourusername'):
yourusername ALL=(ALL) NOPASSWD: /sbin/reboot
yourusername ALL=(ALL) NOPASSWD: /sbin/shutdown
```

---

## Running as a Service

For production use, run the bot as a systemd service that auto-starts on boot.

### Create Service File

```bash
sudo nano /etc/systemd/system/nas-telegram-bot.service
```

Add this content (adjust paths for your installation):

```ini
[Unit]
Description=NAS Telegram AI Assistant
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=yourusername
Group=yourusername
WorkingDirectory=/opt/nas-telegram-bot/BOT
Environment="PATH=/opt/nas-telegram-bot/BOT/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/opt/nas-telegram-bot/BOT/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable nas-telegram-bot

# Start the service
sudo systemctl start nas-telegram-bot

# Check status
sudo systemctl status nas-telegram-bot
```

### Managing the Service

```bash
# View logs
sudo journalctl -u nas-telegram-bot -f

# Stop the bot
sudo systemctl stop nas-telegram-bot

# Restart the bot
sudo systemctl restart nas-telegram-bot

# Disable auto-start
sudo systemctl disable nas-telegram-bot
```

---

## Alternative: Screen or Tmux

If you prefer not to use systemd:

### Using Screen

```bash
# Install screen
sudo apt install screen

# Start a screen session
screen -S nas-bot

# Activate venv and run bot
cd /opt/nas-telegram-bot/BOT
source venv/bin/activate
python bot.py

# Detach from screen: Press Ctrl+A, then D
# Reattach: screen -r nas-bot
# Kill session: screen -X -S nas-bot quit
```

### Using Tmux

```bash
# Install tmux
sudo apt install tmux

# Start a tmux session
tmux new -s nas-bot

# Activate venv and run bot
cd /opt/nas-telegram-bot/BOT
source venv/bin/activate
python bot.py

# Detach: Press Ctrl+B, then D
# Reattach: tmux attach -t nas-bot
# Kill: tmux kill-session -t nas-bot
```

---

## Common Issues

### Bot doesn't start

**Error: `ModuleNotFoundError`**
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

**Error: `telegram.error.InvalidToken`**
- Check `TELEGRAM_TOKEN` in `.env`
- Make sure there are no extra spaces
- Verify token with @BotFather

### Bot starts but doesn't respond

**Issue: No response to messages**
- Check `ALLOWED_USER_IDS` in `.env`
- Make sure your user ID is correct (use @userinfobot)
- Check logs: `tail -f logs/bot.log`

### OpenAI API errors

**Error: `AuthenticationError`**
- Verify `OPENAI_API_KEY` in `.env`
- Check if key is valid at [platform.openai.com](https://platform.openai.com)
- Ensure you have credits in your OpenAI account

**Error: `Model not found`**
- Check if model names in `.env` are correct
- Try using `gpt-4o-mini` instead of `gpt-5.4-nano` if unavailable

### Docker commands fail

**Error: `Permission denied`**
```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Logout and login again
```

**Error: `Cannot connect to Docker daemon`**
```bash
# Start Docker service
sudo systemctl start docker

# Enable auto-start
sudo systemctl enable docker
```

### SMART data unavailable

**Error: `smartctl not found`**
```bash
# Install smartmontools
sudo apt install smartmontools
```

**Error: `Permission denied`**
- Set up passwordless sudo for smartctl (see Permissions Setup)
- Or run bot with sudo (not recommended)

### High memory usage

**Issue: Bot uses too much RAM**
- ChromaDB and embeddings are memory-intensive
- Limit document collection size
- Consider using a machine with 4GB+ RAM
- Use Docker with memory limits

### Database locked

**Error: `database is locked`**
```bash
# Stop the bot
sudo systemctl stop nas-telegram-bot

# Remove lock files
rm -f data/bot.db-shm data/bot.db-wal

# Restart
sudo systemctl start nas-telegram-bot
```

---

## Updating the Bot

To update to the latest version:

```bash
# Stop the bot
sudo systemctl stop nas-telegram-bot

# Navigate to bot directory
cd /opt/nas-telegram-bot

# Pull latest changes
git pull

# Activate venv
cd BOT
source venv/bin/activate

# Update dependencies
pip install --upgrade -r requirements.txt

# Restart the bot
sudo systemctl start nas-telegram-bot

# Check logs
sudo journalctl -u nas-telegram-bot -f
```

---

## Next Steps

- Review the [[Configuration Guide|Configuration-Guide]] for advanced settings
- Explore the [[Commands Reference|Commands-Reference]]
- Set up [[Security]] best practices
- Read [[Troubleshooting]] for more solutions

---

## Getting Help

- Check the [[FAQ]] for common questions
- Review the [[Troubleshooting]] guide
- Check application logs: `tail -f logs/bot.log`
- Report issues on GitHub

---

**Installation complete!** Start using your bot with `/start` in Telegram.
