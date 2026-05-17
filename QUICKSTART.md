# Quick Start Guide - NAS Telegram AI Assistant

## What Was Built

A complete, production-ready Telegram bot for NAS management with:

✅ **33 Python modules** across 6 main components
✅ **System Monitoring** - CPU, RAM, disk, temps, SMART health
✅ **Docker Management** - Full container control
✅ **File System** - Secure file operations
✅ **Service Management** - systemd services, reboot/shutdown
✅ **AI/RAG System** - Document Q&A with conversation history
✅ **Automated Alerts** - Proactive system monitoring
✅ **Security** - Auth, rate limiting, path validation

## Getting Started (5 Steps)

### 1. Install Dependencies

```bash
cd BOT
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure `.env`

Edit `BOT/.env` with your details:

```env
# REQUIRED
TELEGRAM_TOKEN=
OPENAI_API_KEY=
ALLOWED_USER_IDS=YOUR_TELEGRAM_USER_ID_HERE  # Get from @userinfobot

# IMPORTANT PATHS
DOCUMENT_PATH=/srv/dev-disk-by-uuid-9ac22f70-05c6-442f-993b-0d9ca1ae5988/loo/loch/IELTS/
ALLOWED_PATHS=/srv/dev-disk-by-uuid-9ac22f70-05c6-442f-993b-0d9ca1ae5988/loo/loch/IELTS/,/home

# OPTIONAL (for web search)
SERPER_API_KEY=
TAVILY_API_KEY=
```

**Get your Telegram User ID:**
1. Message @userinfobot on Telegram
2. Copy the ID it gives you
3. Paste into `ALLOWED_USER_IDS`

### 3. Test Run

```bash
python bot.py
```

You should see:
```
INFO - Logging initialized
INFO - Initializing database...
INFO - Starting health monitoring...
INFO - Bot is running...
```

### 4. Chat with Your Bot

Open Telegram and message your bot:

```
/start            # Welcome message
/status           # Test system monitoring
/docker           # Test Docker (if running)
/index            # Index your documents for AI
/ask what is IELTS?  # Test AI/RAG
```

### 5. Run as Service (Optional)

For production, run as a systemd service:

```bash
sudo nano /etc/systemd/system/nas-bot.service
```

```ini
[Unit]
Description=NAS Telegram AI Assistant
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/Desktop/Test/BOT
Environment="PATH=/home/YOUR_USERNAME/Desktop/Test/BOT/venv/bin"
ExecStart=/home/YOUR_USERNAME/Desktop/Test/BOT/venv/bin/python bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable nas-bot
sudo systemctl start nas-bot
sudo systemctl status nas-bot
```

## Key Features

### Conversation History (New!)

The bot remembers your last 10 messages:

```
You: /cpu
Bot: CPU: 90%

You: why is it high?
Bot: [Remembers the 90% from previous output and explains]
```

### AI Models Used

- **gpt-4o-mini** (default) - Fast, cost-effective
- **o1-mini** (thinking) - Complex reasoning (/analyze, /think)
- **tinyllama** (local) - Optional fallback for simple tasks

### Internet Search

```
/search latest Docker security tips
```

Uses Serper or Tavily API to search the web + AI summary.

### Security Features

- ✅ User whitelist (only authorized users)
- ✅ Rate limiting (10 commands/min)
- ✅ Path restrictions (can't access system files)
- ✅ Confirmation dialogs (reboot, shutdown, container ops)
- ✅ Complete audit logging

## Project Structure

```
BOT/
├── bot.py                    # Main entry point
├── config.py                 # Configuration
├── .env                      # Your credentials
├── requirements.txt          # Dependencies
├── README.md                 # Full documentation
│
├── commands/                 # 7 command handlers
│   ├── basic.py             # /start, /help
│   ├── monitoring.py        # System stats
│   ├── docker_cmds.py       # Docker control
│   ├── filesystem.py        # File operations
│   ├── ai_cmds.py           # AI/RAG commands
│   └── service.py           # System services
│
├── services/                 # 6 business logic services
│   ├── system_monitor.py    # psutil monitoring
│   ├── docker_service.py    # Docker SDK
│   ├── smart_monitor.py     # HDD health
│   ├── file_service.py      # Secure file ops
│   └── service_manager.py   # systemd control
│
├── ai/                       # 8 AI components
│   ├── gpt_client.py        # OpenAI integration
│   ├── rag_engine.py        # Main RAG logic
│   ├── conversation_history.py  # Context tracking
│   ├── search_engine.py     # Web search
│   ├── document_loader.py   # PDF, DOCX, TXT, MD
│   ├── embeddings.py        # sentence-transformers
│   └── ollama_client.py     # Local fallback
│
├── monitoring/               # Alert system
│   ├── alerts.py            # Threshold logic
│   └── health_checker.py    # Background monitoring
│
├── database/                 # SQLite storage
│   ├── models.py            # Schema
│   └── memory.py            # Conversation history
│
└── utils/                    # Utilities
    ├── security.py          # Auth, rate limiting
    ├── formatters.py        # Pretty Telegram messages
    └── logger.py            # Logging setup
```

## Troubleshooting

### Bot doesn't start
- Check Python version: `python3 --version` (need 3.10+)
- Install missing packages: `pip install -r requirements.txt`
- Check logs: `tail -f logs/bot.log`

### Bot doesn't respond
- Verify TELEGRAM_TOKEN is correct
- Check ALLOWED_USER_IDS has your user ID
- Message @userinfobot to get your correct user ID

### "No documents found"
- Check DOCUMENT_PATH exists: `ls /srv/dev-disk-by-uuid-.../`
- Verify documents are PDF, DOCX, TXT, or MD format
- Run `/index` command to index documents

### Docker commands fail
- Ensure Docker is running: `systemctl status docker`
- Add user to docker group: `sudo usermod -aG docker $USER`
- Logout and login again

### AI responses fail
- Verify OpenAI API key is valid at https://platform.openai.com/api-keys
- Check internet connection
- Try `/chat hello` first (simpler than /ask)

## Next Steps

1. ✅ Configure your user ID in `.env`
2. ✅ Run `python bot.py` to start
3. ✅ Message your bot: `/start`
4. ✅ Index documents: `/index`
5. ✅ Try AI: `/ask [your question]`
6. ✅ Set up systemd service for production

## Support

- 📚 Full docs: `BOT/README.md`
- 🐛 Check logs: `logs/bot.log`
- 💡 All commands: `/help` in Telegram

---

**Built with:** Python 3, python-telegram-bot, OpenAI GPT, ChromaDB, sentence-transformers, psutil, Docker SDK

**Total Lines of Code:** ~3,500+ lines across 33 modules

**Ready for production!** 🚀
