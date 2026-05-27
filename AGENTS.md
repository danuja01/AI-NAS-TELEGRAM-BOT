# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This is a single-process Python Telegram bot (`bot.py`) for NAS management. It uses embedded SQLite (via `aiosqlite`) and ChromaDB for storage — no external database services are needed.

### Running the bot

```bash
cd /workspace
source venv/bin/activate
python bot.py
```

The bot requires two environment variables to start: `TELEGRAM_TOKEN` and `OPENAI_API_KEY`. Without valid values, the bot will load all modules and register handlers but fail at Telegram API validation. See `.env.example` for all configuration options.

Set `HOST_EXEC_MODE=none` in `.env` to disable NAS host commands (nsenter/SSH) when running outside a real NAS environment.

Read-only **OpenMediaVault** storage views use host `omv-rpc` when host exec is enabled (`OMV_RPC_USER`, `OMV_RPC_ENABLED` in `.env`).

With `AGENT_HOST_READONLY_TOOL=true`, the AI may call **`nas_host_readonly_profile`**: a fixed enum of host commands (SSH/nsenter), not arbitrary shell.

**Docker exited alerts** default to `MONITOR_DOCKER_ALERT_MODE=unexpected_exit` (no spam for containers you already stopped). Add names to `MONITOR_DOCKER_IGNORE` if needed.

**Autonomous troubleshooting** (`AUTOTROUBLESHOOT_ENABLED=true`): after threshold health alerts are delivered, the bot gathers read-only evidence (metrics, disks, Docker, SMART, optional journal tails) and sends a Telegram **advisory** AI report (hypotheses, verification steps, possible actions with risks). It does not reboot, prune, upgrade, or restart anything automatically. Uses OpenAI API credits; default off.

Recent `/chat`, `/analyze`, and `/ask` runs include **recent bot messages** in context: slash-command output (e.g. `/smart`) and **automated health/digest alerts** are saved to the conversation DB so follow-up questions like “is this alarming?” can refer to them.

### Dependencies

- Python 3.12 with `python3.12-venv` and `python3.12-dev` (needed to build `chroma-hnswlib` C++ extension)
- Virtual environment at `/workspace/venv`
- Install: `source venv/bin/activate && pip install -r requirements.txt`

### Linting

No project-level linting config exists. Use flake8 for basic checks:

```bash
source venv/bin/activate
flake8 --max-line-length=120 --select=E9,F63,F7,F82 --exclude=venv,data,logs,documents .
```

### Testing

No automated test suite exists in the repository. Verification is done by:
1. Importing all modules: `python -c "import config; from commands import basic, monitoring, docker_cmds, filesystem, ai_cmds, service, operations"`
2. Running the bot with valid Telegram/OpenAI credentials

### Memory (RAM)

Default Docker/compose settings target **~300–600 MB** steady RSS (monitoring-only) instead of **~1.2 GB**:

- **`EMBEDDING_PROVIDER=openai`** (default): RAG uses OpenAI embeddings API — no PyTorch/sentence-transformers in the image.
- **`AUTO_INDEX_ON_START=false`** (default in compose): avoids loading embeddings + full corpus on every container boot.
- **`EMBEDDING_PROVIDER=local`**: install `requirements-local-embeddings.txt` and run `/index` with `AUTO_INDEX_FORCE_REINDEX=true` after switching providers.

### Key gotchas

- `chromadb==0.4.22` requires `chroma-hnswlib` which needs `python3.12-dev` (for `Python.h`) and C++ build tools (`g++`) to compile. These are pre-installed in the VM.
- The `requirements.txt` pins `numpy<2.0` for ChromaDB compatibility.
- The bot uses `python-telegram-bot[job-queue]==20.7` which includes APScheduler integration for background health monitoring and alert scheduling.
- The `.env` file is gitignored. Each agent session should create one from `.env.example` with the required secrets.
