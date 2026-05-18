# FAQ

Frequently Asked Questions about the NAS Telegram AI Assistant.

---

## General Questions

### What is this bot?

A self-hosted Telegram bot for managing your NAS, featuring:
- System monitoring (CPU, RAM, disk, temps)
- Docker container management
- File operations (browse, download, upload)
- AI-powered document Q&A (RAG)
- Root access for advanced operations
- Automated health alerts

### Do I need a NAS to use this?

No! It works on any Linux system:
- Synology/QNAP NAS
- Raspberry Pi
- Home server
- Cloud VPS
- Even your desktop/laptop for testing

### Is it free?

The bot software is free and open source (MIT license), but you'll need:
- **Free**: Telegram account, bot token
- **Paid**: OpenAI API (~$5-50/month depending on usage)
- **Optional**: Web search API (free tiers available)

---

## Setup Questions

### How long does setup take?

- **With Docker**: 10-15 minutes
- **Bare metal**: 20-30 minutes
- **First-time users**: Add 15 minutes for API keys

### What are the system requirements?

**Minimum**:
- 2GB RAM
- 10GB disk space
- Python 3.11+ (bare metal) or Docker
- Internet connection

**Recommended**:
- 4GB+ RAM
- 20GB+ disk
- Linux-based system

### Can I run this on Windows?

Not recommended, but possible via:
- WSL2 (Windows Subsystem for Linux)
- Docker Desktop
- Cloud VPS instead

Better to use Linux, macOS, or NAS.

---

## Usage Questions

### Can multiple users use the bot?

Yes! Add multiple Telegram user IDs:
```env
ALLOWED_USER_IDS=123456789,987654321,555444333
```

Each user has independent sessions and logging.

### Does it work offline?

Partially:
- **Works**: System monitoring, Docker management, file operations
- **Requires internet**: All AI features (use OpenAI API)
- **Optional offline**: Install Ollama for local AI fallback

### How much does OpenAI cost?

Typical usage:
- **Light** (10 queries/day): $5-10/month
- **Medium** (50 queries/day): $20-40/month
- **Heavy** (200 queries/day): $80-150/month

Monitor at [platform.openai.com/usage](https://platform.openai.com/usage)

### Can I use different AI models?

Yes! Configure in `.env`:
```env
DEFAULT_MODEL=gpt-5.4-nano     # Fast, cheap
THINKING_MODEL=o3-mini         # Advanced reasoning
FALLBACK_MODEL=gpt-4o-mini     # Backup
```

Or use Ollama for local models (free).

---

## Features Questions

### What document formats are supported?

For AI/RAG features:
- PDF
- DOCX (Microsoft Word)
- TXT (plain text)
- MD (Markdown)

### How does the RAG feature work?

1. You run `/index` to process documents
2. Bot creates searchable embeddings
3. When you `/ask` a question, it:
   - Searches your documents
   - Sends relevant content to AI
   - Returns answer with citations

See [[AI and RAG|AI-and-RAG]] for details.

### Can I download files from my NAS?

Yes! 
```
/ls DANUJA        # List files with numbers
/download 1       # Download file #1
```

Max file size: 50MB (Telegram limitation)

### Can I upload files to my NAS?

Yes, with root access:
```
/rootlogin <password>
/uploadfile DANUJA
[Send file in Telegram]
```

### What's "root access"?

Temporary elevated permissions (30 minutes) that allow:
- Access to all file system paths
- Execute shell commands via `/ssh`
- Upload files anywhere

Protected by password and fully logged.

---

## Security Questions

### Is it secure?

Yes, with multiple security layers:
- User whitelist (only authorized users)
- Rate limiting (10 commands/minute)
- Path restrictions (configurable)
- Password-protected root access
- Complete audit logging
- No data sent to third parties (except OpenAI API)

### Should I worry about Telegram security?

Telegram bots use HTTPS and are reasonably secure. Keep your bot token secret!

For extra security:
- Use strong `ROOT_PASSWORD`
- Limit `ALLOWED_USER_IDS`
- Review logs regularly
- Don't share bot token

### What data is logged?

Everything:
- All commands
- User IDs
- Root access attempts
- SSH commands
- Errors

Logs stored locally in `logs/bot.log` and `data/bot.db`.

### Can others access my bot?

Only if:
- They're in `ALLOWED_USER_IDS`, OR
- Your bot token is compromised (keep it secret!)

Unauthorized users are silently ignored.

---

## Technical Questions

### Can I customize the bot?

Yes! It's open source. See [[Development and Contributing|Development-and-Contributing]].

Common customizations:
- Add new commands
- Change AI models
- Adjust alert thresholds
- Modify output formatting

### Can I run multiple bots?

Yes, but:
- Each needs unique bot token
- Use different data directories
- Don't run multiple instances of same bot (conflicts)

### Does it support plugins?

Not yet, but you can:
- Add custom commands
- Integrate external tools
- Modify services layer

### What's the difference between Docker and bare metal?

**Docker**:
- ✅ Easier setup
- ✅ Isolated environment
- ✅ Easy updates
- ❌ Slight overhead

**Bare metal**:
- ✅ Direct hardware access
- ✅ Lower resource usage
- ❌ More setup steps
- ❌ Dependency management

Choose Docker unless you have specific reasons not to.

---

## Troubleshooting Questions

### Bot doesn't respond to me

**Check**:
1. Is your user ID in `ALLOWED_USER_IDS`?
   - Get ID from @userinfobot
2. Is bot running?
   - `docker ps` or `systemctl status`
3. Check logs:
   - `docker logs nas-telegram-bot`

### AI commands fail

**Common causes**:
1. Invalid OpenAI API key
2. No credits in OpenAI account
3. Documents not indexed (`/index` first)
4. OpenAI service down (check status.openai.com)

### Commands are slow

**Possible reasons**:
- High system load
- Large document collection
- Slow internet connection
- Using O3-mini model (slower but smarter)

**Solutions**:
- Use faster models (gpt-5.4-nano)
- Reduce indexed documents
- Check system resources

### Where are the logs?

- **Docker**: `docker logs nas-telegram-bot`
- **Bare metal**: `logs/bot.log`
- **Systemd**: `journalctl -u nas-telegram-bot -f`

---

## Comparison Questions

### How is this different from Home Assistant?

**This bot**:
- Telegram-based (use from anywhere)
- AI-powered document Q&A
- Simpler setup for basic NAS management
- Command-line style interface

**Home Assistant**:
- Web-based dashboard
- Home automation focus
- More complex setup
- Broader device support

They can complement each other!

### Do I need Docker knowledge?

Not required! Basic usage:
```bash
docker-compose up -d    # Start
docker-compose down     # Stop
docker-compose logs -f  # View logs
```

That's 90% of what you need.

---

## Future Questions

### Will you add feature X?

Maybe! 
- Check [GitHub Issues](https://github.com/your-repo/issues)
- Request features in Discussions
- Or contribute yourself (open source!)

### Will there be a web interface?

Not currently planned, but:
- Bot works great on mobile
- Could be community contribution
- [[Architecture]] allows for it

### Can I use this commercially?

Yes! MIT license allows commercial use.

But:
- Keep OpenAI API costs in mind
- Add proper error handling
- Consider support requirements

---

## Cost Questions

### Total cost to run?

**One-time**: $0 (free software)

**Monthly**:
- OpenAI API: $5-50 (usage-based)
- Serper/Tavily: $0-50 (optional, free tier available)
- Server: $0 (if using existing NAS) or $5-20/month (VPS)

**Total**: ~$5-120/month depending on usage and infrastructure

### Can I reduce costs?

Yes:
1. Use `/clear` to reduce context
2. Use cheaper models (gpt-5.4-nano)
3. Limit document collection
4. Use Ollama for local AI (free)
5. Set OpenAI usage limits

---

## Getting Help

### Where can I get support?

1. Check this wiki (you're reading it!)
2. Read [[Troubleshooting]]
3. Search [GitHub Issues](https://github.com/your-repo/issues)
4. Ask in [Discussions](https://github.com/your-repo/discussions)
5. Create new issue with details

### How do I report bugs?

[GitHub Issues](https://github.com/your-repo/issues) with:
- Clear description
- Steps to reproduce
- Error messages
- Logs (remove sensitive data!)
- Your setup (Docker/bare metal, OS, etc.)

### Can I contribute?

Yes! See [[Development and Contributing|Development-and-Contributing]].

All contributions welcome:
- Bug fixes
- New features
- Documentation
- Testing
- Translations

---

**Still have questions?** Ask in [GitHub Discussions](https://github.com/your-repo/discussions)!
