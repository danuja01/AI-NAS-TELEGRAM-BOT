# NAS Telegram AI Assistant

A comprehensive self-hosted Telegram AI assistant for managing your NAS server. Features system monitoring, Docker management, file operations, AI-powered document Q&A with RAG, automated alerts, and intelligent conversation history.

## Features

### 🖥 System Monitoring
- Real-time CPU, RAM, disk, and temperature monitoring
- SMART drive health tracking
- Network statistics with Tailscale IP detection
- System health scoring with automatic issue detection

### 🐳 Docker Management
- List and monitor all containers with resource usage
- Start, stop, and restart containers
- View container logs
- Automatic unhealthy container detection

### 📁 File System
- Secure file browsing with path restrictions
- File search across directories
- Directory tree visualization
- Storage usage analysis

### ⚙️ Service Management
- Control systemd services
- System reboot/shutdown with confirmations
- Service status monitoring

### 🤖 AI Assistant (RAG-Powered)
- **Document Q&A**: Ask questions about your documents using RAG
- **Conversation History**: Natural follow-up questions with context awareness (last 10 messages)
- **Internet Search**: Search the web with AI-powered summaries
- **Multiple AI Models**:
  - `gpt-4o-mini` (default) - Fast and efficient for most tasks
  - `o1-mini` (thinking) - Advanced reasoning for complex problems
  - `tinyllama` (local fallback) - Optional local processing

### 📊 Automated Alerts
- Low disk space warnings
- High CPU/memory usage alerts
- Temperature monitoring
- Docker container crashes
- SMART drive health issues

### 🔒 Security
- User whitelist authentication
- Rate limiting (10 commands/minute)
- Path validation and sanitization
- Confirmation dialogs for dangerous operations
- Complete audit logging

## Prerequisites

- **Python 3.10+**
- **Debian/Ubuntu Linux** (for NAS features)
- **OpenAI API key** (required for AI features)
- **Telegram Bot Token**
- **Optional**: Serper or Tavily API key (for web search)
- **Optional**: Ollama installed locally (for fallback)

### System Requirements

```bash
sudo apt update
sudo apt install -y smartmontools  # For SMART drive monitoring
```

## Installation

### 1. Clone and Setup

```bash
cd ~/
git clone <your-repo-url> nas-bot
cd nas-bot/BOT
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy the example env file and edit it:

```bash
cp .env.example .env
nano .env
```

**Required Configuration**:

```env
# Get from @BotFather on Telegram
TELEGRAM_TOKEN=your_telegram_bot_token

# Get from https://platform.openai.com/api-keys
OPENAI_API_KEY=your_openai_api_key

# Your Telegram user ID (get from @userinfobot)
ALLOWED_USER_IDS=123456789

# Path to your documents for RAG
DOCUMENT_PATH=/path/to/your/documents
ALLOWED_PATHS=/path/to/your/documents,/other/allowed/path
```

**Optional Configuration**:

```env
# For internet search (optional but recommended)
SERPER_API_KEY=your_serper_key  # Get from https://serper.dev
TAVILY_API_KEY=your_tavily_key  # Get from https://tavily.com

# For local AI fallback (optional)
OLLAMA_URL=http://localhost:11434/api/generate
```

### 5. Get Your Telegram User ID

1. Start a chat with [@userinfobot](https://t.me/userinfobot)
2. It will reply with your user ID
3. Add it to `ALLOWED_USER_IDS` in `.env`

### 6. First Run

```bash
python bot.py
```

## Usage

### Initial Setup

1. Start the bot: `/start`
2. Index your documents: `/index`
3. Test system monitoring: `/status`

### Monitoring Commands

```
/status      - Comprehensive system overview
/cpu         - CPU usage and load
/ram         - Memory statistics
/disk        - Disk usage
/temps       - Temperature sensors
/network     - Network statistics
/uptime      - System uptime
/health      - System health score
/smart       - Drive health (SMART data)
```

### Docker Commands

```
/docker              - List all containers
/restart <name>      - Restart a container
/stop <name>         - Stop a container
/start <name>        - Start a container
/logs <name> [lines] - View container logs
```

### File System Commands

```
/files          - Browse default document path
/ls <path>      - List directory contents
/search <name>  - Search for files
/tree [path]    - Show directory tree
/storage        - Storage usage summary
```

### AI Commands

```
/ask <question>    - Ask about your documents (RAG)
/chat <message>    - General AI chat
/summarize <topic> - Summarize documents
/explain <term>    - Explain from documents
/analyze <text>    - Deep analysis (o1-mini)
/think <question>  - Complex reasoning
/search <query>    - Internet search with AI summary
/clear             - Clear conversation history
```

### Service Commands

```
/services                - List system services
/restart_service <name>  - Restart a service
/reboot                  - Reboot system (requires confirmation)
/shutdown                - Shutdown system (requires confirmation)
```

## Conversation History Feature

The bot remembers your last 10 messages and command outputs, enabling natural follow-up questions:

**Example 1:**
```
You: /cpu
Bot: CPU Usage: 90%

You: /ask why is it so high?
Bot: [Retrieves "CPU: 90%" from history and provides contextual answer]
```

**Example 2:**
```
You: /docker
Bot: Lists: nginx (running), postgres (running), redis (stopped)

You: restart the last one
Bot: [Knows you mean redis from previous output]
     Restarting redis container...
```

Use `/clear` to start a fresh conversation.

## Deployment

### Run as Background Service

Create a systemd service file:

```bash
sudo nano /etc/systemd/system/nas-bot.service
```

```ini
[Unit]
Description=NAS Telegram AI Assistant
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/home/your_username/nas-bot/BOT
Environment="PATH=/home/your_username/nas-bot/BOT/venv/bin"
ExecStart=/home/your_username/nas-bot/BOT/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable nas-bot
sudo systemctl start nas-bot
sudo systemctl status nas-bot
```

View logs:

```bash
sudo journalctl -u nas-bot -f
```

### Or Use Screen/Tmux

```bash
screen -S nas-bot
cd ~/nas-bot/BOT
source venv/bin/activate
python bot.py

# Detach with Ctrl+A, D
# Reattach with: screen -r nas-bot
```

## Permissions

### Docker Access

Add your user to the docker group:

```bash
sudo usermod -aG docker $USER
# Logout and login again
```

### SMART Monitoring

Allow smartctl without sudo:

```bash
sudo visudo
# Add: your_username ALL=(ALL) NOPASSWD: /usr/sbin/smartctl
```

Or run the bot as root (not recommended for production).

## Troubleshooting

### Bot doesn't respond
- Check TELEGRAM_TOKEN is correct
- Verify ALLOWED_USER_IDS contains your user ID
- Check logs: `tail -f logs/bot.log`

### No documents found for RAG
- Verify DOCUMENT_PATH exists and contains supported files (PDF, DOCX, TXT, MD)
- Ensure ALLOWED_PATHS includes DOCUMENT_PATH
- Run `/index` to index documents

### Docker commands fail
- Ensure Docker is running: `sudo systemctl status docker`
- Check user has Docker permissions: `groups $USER`
- Test: `docker ps`

### SMART data unavailable
- Install smartmontools: `sudo apt install smartmontools`
- Check permissions: `sudo smartctl -a /dev/sda`
- Configure passwordless sudo for smartctl (see Permissions)

### AI responses fail
- Verify OPENAI_API_KEY is valid
- Check internet connection
- Review logs for specific errors

### High memory usage
- ChromaDB and embeddings use memory
- Consider limiting indexed documents
- Use a machine with at least 4GB RAM

## Architecture

```
BOT/
├── bot.py                 # Main entry point
├── config.py              # Configuration
├── .env                   # Environment variables
├── commands/              # Command handlers
│   ├── basic.py          # /start, /help
│   ├── monitoring.py     # System monitoring commands
│   ├── docker_cmds.py    # Docker management
│   ├── filesystem.py     # File operations
│   ├── ai_cmds.py        # AI/RAG commands
│   └── service.py        # Service management
├── services/             # Business logic
│   ├── system_monitor.py
│   ├── docker_service.py
│   ├── smart_monitor.py
│   ├── file_service.py
│   └── service_manager.py
├── ai/                   # AI components
│   ├── gpt_client.py
│   ├── rag_engine.py
│   ├── conversation_history.py
│   ├── search_engine.py
│   ├── document_loader.py
│   ├── embeddings.py
│   └── ollama_client.py
├── monitoring/           # Alerts
│   ├── health_checker.py
│   └── alerts.py
├── database/             # SQLite storage
│   ├── models.py
│   └── memory.py
├── utils/                # Utilities
│   ├── security.py
│   ├── formatters.py
│   └── logger.py
├── logs/                 # Log files
└── data/                 # Database and ChromaDB
```

## API Costs

Approximate OpenAI API costs (as of 2024):
- `gpt-4o-mini`: ~$0.15 per 1M input tokens, ~$0.60 per 1M output tokens
- `o1-mini`: ~$3 per 1M input tokens, ~$12 per 1M output tokens

Tips to minimize costs:
- Use `/clear` to reset conversation history
- Use Ollama for trivial tasks (if configured)
- Limit document indexing to relevant files only

## Security Best Practices

1. **Never commit `.env` file** - Contains sensitive tokens
2. **Use strong API keys** - Rotate regularly
3. **Limit ALLOWED_USER_IDS** - Only trusted users
4. **Restrict ALLOWED_PATHS** - Minimal file system access
5. **Review logs regularly** - Monitor for suspicious activity
6. **Keep dependencies updated** - `pip install --upgrade -r requirements.txt`

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- Check the troubleshooting section
- Review logs in `logs/bot.log`
- Open an issue on GitHub

## Acknowledgments

- Built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- AI powered by [OpenAI](https://openai.com/)
- RAG with [ChromaDB](https://www.trychroma.com/) and [sentence-transformers](https://www.sbert.net/)
- System monitoring with [psutil](https://github.com/giampaolo/psutil)
- Docker management with [Docker SDK](https://docker-py.readthedocs.io/)
