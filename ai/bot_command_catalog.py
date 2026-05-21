"""
Static reference of all Telegram bot commands for AI context (RAG + agent).

Keep in sync with `bot.TELEGRAM_BOT_COMMANDS` and `commands/basic.HELP_SECTION_BODIES`.
"""

BOT_COMMAND_CATALOG = """
# NAS Telegram bot — command reference

You help users with this NAS bot only (this server, storage, Docker here, OMV, homelab networking,
or NAS-relevant technical knowledge). Decline unrelated topics briefly. Prefer exact command names below.
Destructive actions use Telegram confirmations; tell users to run the command themselves when a confirmation UI is required.

## Monitoring
- `/status` — Full system overview (CPU, RAM, disk, temps, uptime); may append OpenMediaVault filesystem usage when RPC works
- `/cpu` — CPU usage and load average
- `/ram` — Memory and swap
- `/disk` — Disk partitions (live) plus OMV filesystem and physical disk panels when `omv-rpc` is available on the host
- `/temps` — Temperature sensors
- `/network` — Live interfaces: state, addresses, MTU/speed, counters, default route, optional Tailscale IPv4 (`tailscale ip -4` when `NETWORK_TAILSCALE_CLI=true`)
- `/netpublic` — Public IPv4 via HTTPS plus local outbound IP and default gateway (same sources as `/network` summary)
- `/netping <host>` — ICMP ping (fixed 4 probes); use IP or a simple hostname
- `/uptime` — System uptime
- `/health` — Health score and issues list
- `/smart` or `/drives` — SMART drive summary (smartctl) plus OMV SMART device overview when available
- `/hdddetail` — HDD spin history and hdparm state; OMV physical disk inventory header when RPC works

## Docker and storage
- `/docker` — **Dashboard only**: compact disk summary + container/image counts (not a deep scan and not for listing unused images in detail).
- `/containers` — List all containers with CPU/RAM when running
- `/dimages` — **Docker image inventory** with unused / dangling / in-use flags (use this when the user asks about **unused images** or reclaimable image space).
- `/dscan` — **Deep** Docker + storage scan (paths, large files, prune estimates); use when they want a full analysis, not just `/docker`.
- `/dclean` — Safe cleanup (with confirmations)
- `/dprune` — Quick prune dangling images and build cache
- `/daggressive` — Aggressive cleanup (extra confirmations)
- `/dbigfiles` — Largest files under allowlisted paths
- `/dlogs` — Very large log files on scanned paths
- `/dhealth` — NAS + Docker health snapshot
- `/dstart <name>` — Start a container
- `/drestart <name>` — Restart (inline confirm)
- `/dstop <name>` — Stop (inline confirm)
- In **/chat** and **/analyze**, the assistant may call tools that post the **same** restart/stop confirmation prompts (nothing runs until you tap Confirm).
- When `AGENT_HOST_READONLY_TOOL=true` in `.env`, the assistant may call **`nas_host_readonly_profile`**: a fixed enum of
  read-only host commands over SSH/nsenter (not arbitrary shell; **not** a substitute for `/ssh`).
- `/dtail <name> [lines]` — Container logs (default 50 lines, up to 2000)

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
- In a **private chat** with the bot, a normal text line (no `/`) is treated like **`/chat`**, unless the wording matches deep-analysis intent (then same as **`/analyze`**).
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
