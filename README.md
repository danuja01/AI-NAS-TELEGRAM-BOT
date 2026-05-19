# NAS Telegram AI Assistant

A comprehensive self-hosted Telegram AI assistant for managing your NAS server. Features system monitoring, Docker management, secure file operations (browse, download, upload), AI-powered document Q&A with RAG, temporary root access with SSH commands, automated alerts, and intelligent conversation history.

## Documentation

**Full documentation is available on the [GitHub Wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki).**

| Topic | Wiki page |
|-------|-----------|
| Quick start & overview | [Home](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Home) |
| Bare metal install | [Installation](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Installation) |
| Docker deploy (recommended) | [Docker Deployment](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Docker-Deployment) |
| All `.env` options | [Configuration Guide](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Configuration-Guide) |
| API keys setup | [API Setup](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/API-Setup) |
| Every command | [Commands Reference](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Commands-Reference) |
| AI & RAG | [AI and RAG](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/AI-and-RAG) |
| Root access & `/ssh` | [Root Access and SSH](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Root-Access-and-SSH) |
| Troubleshooting | [Troubleshooting](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Troubleshooting) |
| FAQ | [FAQ](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/FAQ) |

**In-repo docs** (shorter guides):

- [`docs/DOCKER_DEPLOYMENT.md`](docs/DOCKER_DEPLOYMENT.md) — Docker quick reference
- [`docs/ROOT_ACCESS_GUIDE.md`](docs/ROOT_ACCESS_GUIDE.md) — Root login and SSH usage
- [`QUICKSTART.md`](QUICKSTART.md) — Minimal local test setup

---

## Quick Start (Docker)

```bash
git clone https://github.com/danuja01/AI-NAS-TELEGRAM-BOT.git
cd AI-NAS-TELEGRAM-BOT/BOT

cp .env.example .env
# Edit .env: TELEGRAM_TOKEN, OPENAI_API_KEY, ALLOWED_USER_IDS, ROOT_PASSWORD

mkdir -p data logs documents
docker-compose up -d
docker-compose logs -f
```

In Telegram: `/start` → `/index` → `/help`

See the [Docker Deployment wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Docker-Deployment) for volume mounts, updates, and NAS-specific paths.

## Operations: host updates, cron alerts, metrics

For OpenMediaVault / Debian **host** actions from the bot, the container should run with `privileged: true` and **`pid: host`** (see `docker-compose.yml`) so `nsenter` can reach the host init, **or** set `HOST_EXEC_MODE=ssh` and `HOST_SSH=user@nas-ip`.

| Env | Purpose |
|-----|---------|
| `HOST_EXEC_MODE` | `nsenter` (default), `ssh`, or `none` |
| `HOST_SSH` | e.g. `admin@192.168.1.5` when using SSH mode |
| `MAINTENANCE_ALLOWED_USER_IDS` | Who may run `/upgrade` (comma-separated); if empty, same as `ALLOWED_USER_IDS` |
| `MONITOR_SYSTEMD_UNITS` | Units for health checks + alerts (e.g. `docker,smbd,nginx`) |
| `HOST_READONLY_SYSTEMD_ANY_UNIT` | `false` (default): `journal_tail` / `systemctl_is_active` only for units in `MONITOR_SYSTEMD_UNITS`. Set `true` to allow **read-only** journal/status for any syntactically valid unit (SSH `ssh`/`sshd`, etc.). Still no shell writes; journals may expose secrets. |
| `CRON_NOTIFY_SECRET` | If set, starts an HTTP hook inside the container on `CRON_NOTIFY_BIND:CRON_NOTIFY_PORT` |
| `HEALTH_CHECK_INTERVAL`, `METRICS_SAMPLE_INTERVAL_MINUTES`, `DIGEST_INTERVAL_HOURS` | Monitoring scheduler |
| `OMV_RPC_USER` | User passed to `omv-rpc -u` (default `admin`) |
| `OMV_RPC_ENABLED` | `true`/`false` — disable all OMV RPC reads from the bot |

**Telegram commands:** `/updates` (apt refresh + upgradable list), `/omv_updates` (same + OMV note), `/upgrade` (confirm, then **`omv-upgrade`** on host; long-running).

**Storage analytics:** `/disk`, `/status`, `/smart`, and `/hdddetail` call read-only `omv-rpc` on the NAS (same RPC as the OMV UI) when `HOST_EXEC_MODE` is not `none`, so Telegram output can show OMV filesystem usage bars and physical disk inventory alongside live `psutil` / `smartctl` data.

**Cron on the NAS host — option A — script:** [`scripts/notify_telegram.sh`](scripts/notify_telegram.sh) calls the Telegram HTTP API (set `TELEGRAM_CHAT_ID` or rely on first `ALLOWED_USER_IDS` from `.env`):

```bash
0 3 * * * /path/to/BOT/scripts/notify_telegram.sh "nightly-backup" "ok" "Finished rsync"
```

**Option B — HTTP hook (requires `CRON_NOTIFY_SECRET`):** from the host:

```bash
docker exec nas-telegram-bot curl -sS -X POST http://127.0.0.1:18765/notify \
  -H 'Content-Type: application/json' \
  -d '{"secret":"YOUR_SECRET","job":"backup","status":"ok","message":"done"}'
```

---

## Features

### System Monitoring
- Real-time CPU, RAM, disk, temperature, and network stats; optional **OpenMediaVault** filesystem and disk panels via host `omv-rpc` when the bot runs with host access (`HOST_EXEC_MODE`)
- SMART drive health (`/smart`, `/drives`)
- System health scoring (`/health`)
- Tailscale IP detection
- Automated alerts (disk, CPU, memory, temperature, SMART, container crashes)

### Docker Management
- Dashboard + storage tools (`/docker`), compact list (`/containers`)
- Start, stop, restart containers
- View logs (`/logs`)
- Requires Docker socket access (mounted in `docker-compose.yml`)

### File System
- Secure browsing with path restrictions (`ALLOWED_PATHS`)
- Numbered file listings (`/ls`) for easy selection
- Download files by number (`/download`)
- Upload files with root access (`/uploadfile`)
- Search (`/find`), directory tree (`/tree`), storage analysis (`/storage`)
- Relative paths resolve under `DOCUMENT_PATH` (e.g. `/ls DANUJA`)

### Root Access & SSH
- Temporary elevated access for 30 minutes (`/rootlogin`)
- Full filesystem access when root session is active
- Execute shell commands via `/ssh` (logged, 60s timeout)
- Session status and early logout (`/rootstatus`, `/rootlogout`)

### AI Assistant (RAG)
- Document Q&A from your files (`/ask`) — PDF, DOCX, TXT, MD
- In **private** chats, a **normal text message** (no `/command`) runs the same pipeline as **`/chat`** so you can talk to the assistant without typing `/chat`. Phrases that ask for deep reasoning (e.g. “please think about…”, “analyze this…”, “think deeply…”, or a line starting with `think:` / `analyze:`) use the **`/analyze`** pipeline instead
- **`/chat`, `/analyze`, and `/ask`** can call **read-only tools** (temperature sensors, health score, disk mounts, network counters, SMART summary, systemd services, paths from `ALLOWED_PATHS`, Docker list/logs/unhealthy, plus a combined snapshot). **`/chat`** and **`/analyze`** can also trigger **Docker restart/stop** using the same inline Confirm/Cancel prompts as `/drestart` / `/dstop`. A built-in command catalog is always included in context
- Model replies are passed through **telegramify-markdown** so Markdown (including GFM tables) is converted to Telegram-safe **MarkdownV2** chunks instead of relying on legacy Markdown tables
- Conversation history (last 10 messages) for natural follow-ups
- Internet search with AI summary (`/websearch`)
- Models (configurable in `.env`):
  - `gpt-5.4-nano` — default, fast
  - `o3-mini` — thinking / complex tasks (`/analyze`, `/think`)
  - `gpt-4o-mini` — fallback
- Optional: Ollama for local fallback

### Service Management
- List and restart systemd services (bare metal; graceful skip in Docker)
- Reboot/shutdown with confirmation

### Security
- User whitelist (`ALLOWED_USER_IDS`)
- Rate limiting (10 commands/minute)
- Path validation and audit logging
- Password-protected root sessions

---

## Prerequisites

- **Python 3.11+** (bare metal) or **Docker** (recommended)
- **OpenAI API key** (required for AI)
- **Telegram bot token** ([@BotFather](https://t.me/BotFather))
- **Optional**: Serper or Tavily API key (web search)
- **Optional**: `smartmontools` (SMART monitoring; included in Docker image)

```bash
# Bare metal only
sudo apt install -y smartmontools
```

---

## Installation

### Option A: Docker (recommended)

```bash
cd BOT
cp .env.example .env
nano .env
docker-compose up -d
```

Details: [Docker Deployment wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Docker-Deployment) · [`docs/DOCKER_DEPLOYMENT.md`](docs/DOCKER_DEPLOYMENT.md)

### Option B: Bare metal

```bash
cd BOT
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python bot.py
```

Details: [Installation wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Installation)

### Required `.env` variables

```env
TELEGRAM_TOKEN=your_bot_token
OPENAI_API_KEY=sk-your_openai_key
ALLOWED_USER_IDS=your_telegram_user_id
DOCUMENT_PATH=/path/to/documents
ALLOWED_PATHS=/path/to/documents
ROOT_PASSWORD=your_secure_password
```

Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot). Full reference: [Configuration Guide](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Configuration-Guide).

---

## Command overview

Use `/help` in Telegram for the full list. Highlights:

| Category | Commands |
|----------|----------|
| Monitoring | `/status`, `/cpu`, `/ram`, `/disk`, `/temps`, `/network`, `/uptime`, `/health`, `/smart`, `/drives` |
| Docker | `/docker`, `/containers`, `/dstart`, `/drestart`, `/dstop`, `/dtail`, … |
| Files | `/files`, `/ls`, `/download`, `/uploadfile`, `/find`, `/tree`, `/storage` |
| AI | `/ask`, `/chat`, `/summarize`, `/explain`, `/analyze`, `/think`, `/websearch`, `/index`, `/clear` |
| Root | `/rootlogin`, `/rootstatus`, `/rootlogout`, `/ssh` |
| Services | `/services`, `/restart_service`, `/reboot`, `/shutdown` |

**Tips:**
- After `/ls`, use `/download 1` to fetch file #1 (cache lasts ~10 minutes)
- `/uploadfile` and `/ssh` require an active root session
- `/ssh ls` defaults to the documents folder in Docker (`/app/documents`)

Complete reference: [Commands Reference wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Commands-Reference)

---

## Conversation history

The bot remembers your last 10 messages and command outputs:

```
You: /cpu
Bot: CPU Usage: 90%

You: why is it so high?
Bot: [Uses prior context to explain]
```

Use `/clear` to reset context.

---

## Deployment

| Method | Guide |
|--------|--------|
| Docker Compose | [Wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Docker-Deployment) |
| systemd service | [Wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Deployment-Options) |
| Synology / QNAP | [Wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Deployment-Options) |

**Update (Docker):**
```bash
docker-compose down
git pull
docker-compose build --no-cache
docker-compose up -d
```

---

## Project structure

```
BOT/
├── bot.py                 # Entry point
├── config.py
├── docker-compose.yml
├── Dockerfile
├── commands/
│   ├── basic.py           # /start, /help
│   ├── monitoring.py
│   ├── docker_cmds.py
│   ├── filesystem.py      # /ls, /download, /uploadfile
│   ├── ai_cmds.py
│   ├── service.py
│   └── root_cmds.py       # /rootlogin, /ssh
├── services/
├── ai/                    # RAG, GPT, search
├── database/
├── monitoring/
├── utils/
│   ├── security.py
│   ├── root_session.py
│   └── file_cache.py
├── docs/
├── data/
└── logs/
```

Architecture details: [Architecture wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Architecture)

---

## Troubleshooting

| Issue | See |
|-------|-----|
| Bot won't start / no response | [Troubleshooting wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Troubleshooting) |
| Docker commands fail | Mount `/var/run/docker.sock` in `docker-compose.yml` |
| SMART not found | Rebuild Docker image (`smartmontools` in Dockerfile) |
| Path access denied | Use relative `/ls DANUJA` or `/rootlogin` |
| Telegram conflict | Only one bot instance running |

Logs: `tail -f logs/bot.log` or `docker-compose logs -f`

---

## API costs

Approximate OpenAI usage (varies by model and volume):

- Light (≈10 queries/day): ~$5–10/month
- Medium (≈50/day): ~$20–40/month

Use `/clear`, prefer `gpt-5.4-nano` for routine tasks, and set billing limits on your OpenAI account.

---

## Security

1. Never commit `.env`
2. Use a strong `ROOT_PASSWORD`
3. Limit `ALLOWED_USER_IDS` to trusted users
4. Restrict `ALLOWED_PATHS` to what you need
5. Review logs for root/SSH activity

Full guide: [Security wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Security)

---

## Contributing

Contributions welcome! See [Development and Contributing](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki/Development-and-Contributing).

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

---

## License

MIT License — see LICENSE file for details.

---

## Support

- **[GitHub Wiki](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/wiki)** — primary documentation
- **[Issues](https://github.com/danuja01/AI-NAS-TELEGRAM-BOT/issues)** — bugs and feature requests
- Logs: `logs/bot.log` or `docker-compose logs -f`

---

## Acknowledgments

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [OpenAI](https://openai.com/)
- [ChromaDB](https://www.trychroma.com/) & [sentence-transformers](https://www.sbert.net/)
- [psutil](https://github.com/giampaolo/psutil)
- [Docker SDK for Python](https://docker-py.readthedocs.io/)
