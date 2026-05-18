# NAS Telegram AI Assistant

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)
![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)

A comprehensive, self-hosted Telegram AI assistant for managing your NAS server. Features system monitoring, Docker management, secure file operations, AI-powered document Q&A with RAG, automated alerts, and intelligent conversation history.

---

## Quick Start

Get up and running in 3 steps:

1. **Get Your Credentials**
   - Create bot with [@BotFather](https://t.me/BotFather)
   - Get your user ID from [@userinfobot](https://t.me/userinfobot)
   - Get OpenAI API key from [platform.openai.com](https://platform.openai.com/api-keys)

2. **Deploy with Docker** (Recommended)
   ```bash
   git clone <your-repo-url>
   cd BOT
   cp .env.example .env
   # Edit .env with your credentials
   docker-compose up -d
   ```

3. **Start Using**
   - Open Telegram and message your bot
   - Type `/start` to begin
   - Type `/index` to index your documents
   - Type `/help` to see all commands

**Prefer manual installation?** See the [[Installation]] guide.

---

## Key Features

### System Monitoring
- Real-time CPU, RAM, disk usage
- Temperature sensors and health scoring
- SMART drive health tracking
- Network statistics with Tailscale detection
- Automated alerts for issues

### Docker Management
- List, start, stop, restart containers
- View container logs and resource usage
- Automatic unhealthy container detection

### File System Operations
- Secure file browsing with path restrictions
- Download files with numbered selection
- Upload files (root access)
- File search and directory tree visualization
- Storage usage analysis

### AI Assistant (RAG)
- Ask questions about your documents
- Natural conversation with 10-message context
- Internet search with AI summaries
- Multiple AI models (GPT-5.4-nano, O3-mini)
- Intelligent document indexing

### Root Access & SSH
- Temporary elevated access (30 minutes)
- Execute shell commands via bot
- Password-protected with audit logging
- Automatic session timeout

### Security
- User whitelist authentication
- Rate limiting (10 commands/minute)
- Path validation and sanitization
- Complete audit logging
- Confirmation for dangerous operations

---

## Documentation Navigation

### Getting Started
- **[[Installation]]** - Detailed setup for bare metal
- **[[Docker Deployment|Docker-Deployment]]** - Containerized deployment (recommended)
- **[[Configuration Guide|Configuration-Guide]]** - Complete `.env` reference
- **[[API Setup|API-Setup]]** - Get all required API keys

### Using the Bot
- **[[Commands Reference|Commands-Reference]]** - Complete command catalog
- **[[AI and RAG|AI-and-RAG]]** - Document Q&A and AI features
- **[[System Monitoring|System-Monitoring]]** - Monitoring capabilities
- **[[Docker Management|Docker-Management]]** - Container operations
- **[[File Management|File-Management]]** - File operations and security
- **[[Root Access and SSH|Root-Access-and-SSH]]** - Elevated access features

### Configuration & Security
- **[[Security]]** - Security model and best practices
- **[[Deployment Options|Deployment-Options]]** - Production deployment strategies

### Help & Support
- **[[Troubleshooting]]** - Common issues and solutions
- **[[FAQ]]** - Frequently asked questions
- **[[Architecture]]** - System design and components
- **[[Development and Contributing|Development-and-Contributing]]** - For contributors

---

## Screenshots

### System Monitoring
Monitor your NAS health in real-time:
- CPU, RAM, disk usage
- Temperature sensors
- Network statistics
- Health scoring

### Docker Management
Control containers from Telegram:
- List all containers with status
- Start/stop/restart operations
- View logs

### AI Document Q&A
Ask questions about your documents:
- Natural language queries
- Context-aware responses
- Internet search integration

### File Operations
Secure file management:
- Browse directories
- Download with numbered selection
- Upload files (root users)

---

## System Requirements

### Minimum
- Python 3.11+
- 2GB RAM
- 10GB disk space
- Linux (Debian/Ubuntu recommended)

### Recommended
- Python 3.11+
- 4GB RAM
- 20GB disk space
- Docker support
- Synology/QNAP NAS or dedicated server

### API Requirements
- **Required**: Telegram Bot Token (free)
- **Required**: OpenAI API key (paid)
- **Optional**: Serper or Tavily API for web search
- **Optional**: Ollama for local AI fallback

---

## Technology Stack

- **Bot Framework**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- **AI/LLM**: [OpenAI GPT](https://openai.com/) (GPT-5.4-nano, O3-mini)
- **RAG**: [ChromaDB](https://www.trychroma.com/) + [sentence-transformers](https://www.sbert.net/)
- **System Monitoring**: [psutil](https://github.com/giampaolo/psutil)
- **Docker**: [Docker SDK for Python](https://docker-py.readthedocs.io/)
- **Database**: SQLite with [aiosqlite](https://github.com/omnilib/aiosqlite)

---

## Quick Reference

### Most Used Commands
```
/status    - System overview
/cpu       - CPU usage
/docker    - List containers
/ls        - List files
/ask       - Ask AI about documents
/health    - System health score
/help      - Show all commands
```

### Root Access
```
/rootlogin <password>  - Enable root access (30min)
/ssh <command>         - Execute shell commands
/rootlogout            - Disable root access
```

### AI Features
```
/ask <question>        - Document Q&A with RAG
/websearch <query>     - Search internet with AI
/chat <message>        - General AI conversation
/index                 - Re-index documents
```

---

## Community & Support

- **Issues**: [Report bugs or request features](https://github.com/your-repo/issues)
- **Discussions**: [Ask questions and share ideas](https://github.com/your-repo/discussions)
- **Documentation**: You're reading it!

---

## License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## Next Steps

1. Follow the [[Installation]] or [[Docker Deployment|Docker-Deployment]] guide
2. Configure your [[API Setup|API-Setup]]
3. Explore the [[Commands Reference|Commands-Reference]]
4. Set up [[Security]] best practices

**Need help?** Check the [[Troubleshooting]] page or [[FAQ]].
