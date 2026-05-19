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

Optional **AI host read evaluator**: set `AGENT_HOST_READONLY_EVALUATOR_MODE=true` (with `AGENT_HOST_READONLY_TOOL=true`) so `/ask` can use `nas_host_read_request` — a second JSON-only model call maps natural language to the same fixed `host_runner` profiles; execution still never runs arbitrary shell from the model.

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
1. Importing all modules: `python -c "import config; from commands import basic, monitoring, docker_cmds, filesystem, ai_cmds, service, root_cmds, operations"`
2. Running the bot with valid Telegram/OpenAI credentials

### Key gotchas

- `chromadb==0.4.22` requires `chroma-hnswlib` which needs `python3.12-dev` (for `Python.h`) and C++ build tools (`g++`) to compile. These are pre-installed in the VM.
- The `requirements.txt` pins `numpy<2.0` for ChromaDB compatibility.
- The bot uses `python-telegram-bot[job-queue]==20.7` which includes APScheduler integration for background health monitoring and alert scheduling.
- The `.env` file is gitignored. Each agent session should create one from `.env.example` with the required secrets.
