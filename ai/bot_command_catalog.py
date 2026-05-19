"""
Static reference of all Telegram bot commands for AI context (RAG + agent).

Keep in sync with `bot.TELEGRAM_BOT_COMMANDS` and `commands/basic.HELP_SECTION_BODIES`.
"""

BOT_COMMAND_CATALOG = """
# NAS Telegram bot — command reference

You help users with this bot. Prefer exact command names below. Destructive actions use
Telegram confirmations; tell users to run the command themselves when a confirmation UI is required.

## Monitoring
- `/status` — Full system overview (CPU, RAM, disk, temps, uptime)
- `/cpu` — CPU usage and load average
- `/ram` — Memory and swap
- `/disk` — Disk partitions and free space
- `/temps` — Temperature sensors
- `/network` — Network interfaces and traffic
- `/uptime` — System uptime
- `/health` — Health score and issues list
- `/smart` or `/drives` — SMART drive summary
- `/hdddetail` — HDD spin history and hdparm state

## Docker and storage
- `/docker` — Dashboard: disk summary, image/container counts, table
- `/containers` — List all containers with CPU/RAM when running
- `/dscan` — Deep Docker/storage scan
- `/dclean` — Safe cleanup (with confirmations)
- `/dprune` — Quick prune dangling images and build cache
- `/daggressive` — Aggressive cleanup (extra confirmations)
- `/dimages` — Docker images (unused/dangling/in use)
- `/dbigfiles` — Largest files under allowlisted paths
- `/dlogs` — Very large log files on scanned paths
- `/dhealth` — NAS + Docker health snapshot
- `/dstart <name>` — Start a container
- `/drestart <name>` — Restart (inline confirm)
- `/dstop <name>` — Stop (inline confirm)
- `/dtail <name> [lines]` — Container logs (default 50 lines, max 200)

## Files
- `/files` — Browse default documents folder
- `/ls [path]` — List directory (numbered entries)
- `/find` — Search filenames under allowed roots
- `/tree` — Directory tree
- `/storage` — Disk usage for configured paths
- `/download` — Download by number from `/ls` or ZIP range
- `/uploadfile` — Upload (often needs root session)
- `/cd` — Print or change working directory (root session for full paths)

## AI and documents
- `/ask` — RAG question over indexed documents
- `/chat` — Chat with tools (live Docker/system reads when needed)
- `/summarize` — Summarize a topic from documents
- `/explain` — Explain a term from documents
- `/analyze` — Deeper analysis (may use tools)
- `/think` — Reasoning-focused answer
- `/websearch` — Web search + summary
- `/index` — Rebuild document index
- `/clear` — Clear conversation history
- `/cancel` — Abort pending follow-up prompts

## Services and host
- `/services` — Systemd services list/status
- `/restart_service` — Restart one service
- `/reboot`, `/shutdown` — Host power (confirmations)
- `/updates`, `/omv_updates` — APT/OMV updates
- `/upgrade` — Run omv-upgrade (strong confirmation)
- `/rootlogin`, `/rootstatus`, `/rootlogout` — Short root session
- `/ssh` — One host shell command (root only)

## Notes
- `/restart`, `/stop`, `/logs` are legacy redirects to `/drestart`, `/dstop`, `/dtail`.
- Host-only scans and `HOST_EXEC_MODE` may limit some features when the bot runs outside the NAS.
""".strip()
